"""Compile and execute local durable dataset graphs."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pandas as pd
import pyarrow as pa
from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._attempt_budget import _attempt_budget_scope
from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._observability import _analytics_correlation, _failure_category
from cfb_data._tabular import _arrow_table_from_models, _models_from_arrow_table
from cfb_data.analytics._sources import EndpointOperation, endpoint_operation
from cfb_data.analytics.artifacts import (
    ArtifactDescriptor,
    ArtifactRef,
    LocalArtifactStore,
    RunDescriptor,
)
from cfb_data.analytics.contracts import (
    AnalyticsDefinition,
    CheckpointMode,
    CoverageState,
    DatasetCatalog,
    DatasetDefinition,
    DatasetPlan,
    DefinitionNode,
    ExecutionPolicy,
    LiteralBinding,
    ParameterBinding,
    PlannedStep,
    QualityResult,
    RecordTransform,
    RecoverySourcePolicy,
    SourceCoverage,
    SourceNode,
    TableContract,
    TransformBackend,
    TransformNode,
    TransformRegistry,
    WorkflowDefinition,
    WorkflowPlan,
    canonical_json,
    parameter_fingerprint,
)
from cfb_data.analytics.observability import (
    AnalyticsArtifactEvent,
    AnalyticsOutcome,
    AnalyticsRunEvent,
    AnalyticsStepEvent,
    AnalyticsValidationEvent,
    ArtifactAction,
    RunPhase,
    StepPhase,
    _AnalyticsDispatcher,
)
from cfb_data.cache._coordinator import CacheCoordinator, CacheModeScope
from cfb_data.cache.config import CacheMode
from cfb_data.errors import (
    CFBDAnalyticsError,
    CFBDArtifactError,
    CFBDDefinitionError,
    CFBDRunError,
)

_ENGINE_VERSION = 1


@dataclass(frozen=True, slots=True)
class DatasetRun[FrameT]:
    """Return a materialized dataset and immutable execution evidence."""

    run_id: str
    definition_id: str
    frame: FrameT
    artifact: ArtifactRef
    reused_steps: tuple[str, ...]
    quality: tuple[QualityResult, ...]
    coverage: tuple[SourceCoverage, ...]
    parent_run_id: str | None


@dataclass(frozen=True, slots=True)
class _WorkflowExecution[FrameT]:
    """Carry one generic workflow execution to the public resource wrapper."""

    run_id: str
    definition_id: str
    frames: Mapping[str, FrameT]
    artifacts: Mapping[str, ArtifactRef]
    reused_steps: tuple[str, ...]
    quality: Mapping[str, tuple[QualityResult, ...]]
    coverage: Mapping[str, tuple[SourceCoverage, ...]]
    parent_run_id: str | None


@dataclass(frozen=True, slots=True)
class _StepValue:
    rows: tuple[BaseModel, ...]
    row_model: type[BaseModel]
    table: pa.Table
    content_digest: str
    artifact: ArtifactRef | None
    quality: tuple[QualityResult, ...]
    coverage: tuple[SourceCoverage, ...]
    reused: bool


@dataclass(frozen=True, slots=True)
class _SourceResult:
    """Retain one validated endpoint result within a bounded execution scope."""

    rows: tuple[BaseModel, ...]
    fetched_at: datetime


@dataclass(slots=True)
class _ExecutionResources:
    """Share bounded scheduling and source deduplication across child graphs."""

    retrieval_semaphore: asyncio.Semaphore
    compute_semaphore: asyncio.Semaphore
    source_lock: asyncio.Lock
    source_results: dict[str, _SourceResult]
    source_locks: dict[str, asyncio.Lock]
    retrieval_concurrency: int
    compute_concurrency: int


_CURRENT_EXECUTION_RESOURCES: ContextVar[_ExecutionResources | None] = ContextVar(
    "cfb_data_analytics_execution_resources", default=None
)


@contextmanager
def _execution_resources_scope(
    policy: ExecutionPolicy,
) -> Iterator[_ExecutionResources]:
    """Install one shared scheduler for a dataset or composite workflow."""
    existing = _CURRENT_EXECUTION_RESOURCES.get()
    if existing is not None:
        if (
            existing.retrieval_concurrency != policy.retrieval_concurrency
            or existing.compute_concurrency != policy.compute_concurrency
        ):
            raise CFBDAnalyticsError(
                "Nested analytics runs must use their workflow concurrency policy"
            )
        yield existing
        return
    resources = _ExecutionResources(
        retrieval_semaphore=asyncio.Semaphore(policy.retrieval_concurrency),
        compute_semaphore=asyncio.Semaphore(policy.compute_concurrency),
        source_lock=asyncio.Lock(),
        source_results={},
        source_locks={},
        retrieval_concurrency=policy.retrieval_concurrency,
        compute_concurrency=policy.compute_concurrency,
    )
    token = _CURRENT_EXECUTION_RESOURCES.set(resources)
    try:
        yield resources
    finally:
        _CURRENT_EXECUTION_RESOURCES.reset(token)


class _StepFailure(Exception):
    def __init__(self, step_id: str, cause: BaseException) -> None:
        self.step_id = step_id
        self.cause = cause
        super().__init__(step_id)


class _AnalyticsEngine[FrameT]:
    """Own one client-scoped compiler, scheduler, and lazy artifact store."""

    def __init__(
        self,
        *,
        executor: _EndpointExecutor,
        adapter: _DataFrameAdapter[FrameT],
        dataframe_backend: str,
        cache_coordinator: CacheCoordinator,
        source_scope: str,
        store: LocalArtifactStore,
        catalog: DatasetCatalog,
        transforms: TransformRegistry,
        policy: ExecutionPolicy,
        observer: Callable[[object], None] | None,
        max_attempts_per_request: int,
    ) -> None:
        self._executor = executor
        self._adapter = adapter
        self._dataframe_backend = dataframe_backend
        self._cache_coordinator = cache_coordinator
        self._source_scope = source_scope
        self._store = store
        self._catalog = catalog
        self._transforms = transforms
        self._policy = policy
        self._dispatcher = _AnalyticsDispatcher(observer)
        self._max_attempts_per_request = max_attempts_per_request
        self._open_lock = asyncio.Lock()
        self._opened = False
        self._local_flights: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        """Close the store only when analytics opened it lazily."""
        async with self._open_lock:
            if self._opened:
                await self._store.close()
                self._opened = False

    @property
    def artifact_store_path(self) -> Path:
        """Return the configured store root without opening it."""
        return self._store.path

    @property
    def max_attempts_per_request(self) -> int:
        """Return the transport retry ceiling used for conservative planning."""
        return self._max_attempts_per_request

    async def prune_artifacts(self, *, dry_run: bool) -> tuple[str, ...]:
        """List or prune unreferenced artifacts through the owned store."""
        await self._ensure_open()
        return await self._store.prune(dry_run=dry_run)

    async def cleanup_orphans(self, *, older_than: timedelta) -> int:
        """Remove only stale, uncommitted staging directories."""
        await self._ensure_open()
        return await self._store.cleanup_orphans(older_than=older_than)

    async def list_artifacts(self, *, limit: int) -> tuple[ArtifactDescriptor, ...]:
        """List safe artifact descriptors through the owned store."""
        await self._ensure_open()
        return await self._store.list_artifacts(limit=limit)

    async def inspect_artifact(self, artifact_id: str) -> ArtifactDescriptor:
        """Inspect one opaque artifact descriptor through the owned store."""
        await self._ensure_open()
        return await self._store.inspect_artifact(artifact_id)

    async def pin_artifact(self, artifact_id: str, *, pinned: bool) -> None:
        """Set explicit retention state for one opaque artifact."""
        await self._ensure_open()
        await self._store.pin(artifact_id, pinned=pinned)

    async def list_runs(
        self, *, definition_id: str | None, limit: int
    ) -> tuple[RunDescriptor, ...]:
        """List safe immutable run descriptors through the owned store."""
        await self._ensure_open()
        return await self._store.list_runs(
            definition_id=definition_id,
            limit=limit,
        )

    async def inspect_run(self, run_id: str) -> RunDescriptor:
        """Inspect one immutable run descriptor through the owned store."""
        await self._ensure_open()
        return await self._store.inspect_run(run_id)

    async def begin_workflow_run(
        self,
        *,
        definition_id: str,
        definition_revision: int,
        parameter_digest: str,
        resume_from: str | None,
        step_count: int,
    ) -> tuple[str, str | None, float]:
        """Create and observe one durable composite workflow run."""
        await self._ensure_open()
        parent_run_id = resume_from
        if parent_run_id is None:
            parent_run_id = await self._store.latest_failed_run(
                definition_id=definition_id,
                parameter_fingerprint=parameter_digest,
            )
        run_id = uuid.uuid4().hex
        await self._store.begin_run(
            run_id=run_id,
            definition_id=definition_id,
            definition_revision=definition_revision,
            parameter_fingerprint=parameter_digest,
            parent_run_id=parent_run_id,
        )
        started_at = self._dispatcher.now()
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id=run_id,
                definition_id=definition_id,
                phase=RunPhase.started,
                outcome=None,
                step_count=step_count,
                duration_seconds=None,
            )
        )
        return run_id, parent_run_id, started_at

    async def complete_workflow_run(
        self,
        *,
        run_id: str,
        definition_id: str,
        artifacts: Mapping[str, Sequence[ArtifactRef]],
        step_count: int,
        started_at: float,
    ) -> None:
        """Commit workflow output lineage and mark the composite run successful."""
        for output_name, refs in artifacts.items():
            for index, artifact in enumerate(refs):
                fingerprint = hashlib.sha256(
                    canonical_json(
                        {
                            "workflow": definition_id,
                            "output": output_name,
                            "ordinal": index,
                            "artifact": artifact.descriptor.content_digest,
                        }
                    )
                ).hexdigest()
                await self._store.record_reuse(
                    run_id=run_id,
                    step_id=f"{output_name}_{index:05d}",
                    fingerprint=fingerprint,
                    artifact_id=artifact.descriptor.artifact_id,
                )
        await self._store.finish_run(run_id, status="success")
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id=run_id,
                definition_id=definition_id,
                phase=RunPhase.finished,
                outcome=AnalyticsOutcome.success,
                step_count=step_count,
                duration_seconds=self._dispatcher.elapsed(started_at),
            )
        )

    async def fail_workflow_run(
        self,
        *,
        run_id: str,
        definition_id: str,
        step_id: str,
        category: str,
        cancelled: bool,
        step_count: int,
        started_at: float,
    ) -> None:
        """Mark a composite workflow run terminal without publishing outputs."""
        await self._store.finish_run(
            run_id,
            status="cancelled" if cancelled else "error",
            failure_step_id=step_id,
            failure_category=category,
        )
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id=run_id,
                definition_id=definition_id,
                phase=RunPhase.finished,
                outcome=(
                    AnalyticsOutcome.cancelled if cancelled else AnalyticsOutcome.error
                ),
                step_count=step_count,
                duration_seconds=self._dispatcher.elapsed(started_at),
                failure_category=category,
            )
        )

    async def materialize_artifacts(
        self,
        contract: TableContract[BaseModel],
        artifacts: Sequence[ArtifactRef],
    ) -> FrameT:
        """Combine compatible partition artifacts into one validated frame."""
        return await asyncio.to_thread(
            self._materialize_artifacts_sync, contract, artifacts
        )

    def _materialize_artifacts_sync(
        self,
        contract: TableContract[BaseModel],
        artifacts: Sequence[ArtifactRef],
    ) -> FrameT:
        """Load and materialize artifacts outside the event-loop thread."""
        rows: list[BaseModel] = []
        adapter = _list_adapter(contract.row_model)
        for artifact in artifacts:
            table = artifact.load_table()
            rows.extend(
                _models_from_arrow_table(
                    row_model=contract.row_model,
                    response_adapter=adapter,
                    table=table,
                )
            )
        _, table, _ = _validate_table(contract, rows)
        return self._adapter.from_table(
            endpoint=contract.id,
            row_model=contract.row_model,
            table=table,
        )

    async def plan_dataset(
        self,
        definition: str | DatasetDefinition[BaseModel, BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
    ) -> DatasetPlan:
        """Compile and describe a dataset without API or artifact writes."""
        resolved = self._dataset_definition(definition)
        validated = _validate_parameters(resolved.parameter_model, params)
        selected_policy = policy or self._policy
        steps = self._compile(resolved, validated, selected_policy)
        source_count = len(self._source_request_keys(resolved, validated))
        return DatasetPlan(
            definition_id=resolved.id,
            definition_revision=resolved.revision,
            parameter_fingerprint=parameter_fingerprint(validated),
            steps=steps,
            logical_source_requests=source_count,
            worst_case_http_attempts=source_count * self._max_attempts_per_request,
        )

    def source_request_keys(
        self,
        definition: str | DatasetDefinition[BaseModel, BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
    ) -> frozenset[str]:
        """Return exact value-free source identities for workflow planning."""
        resolved = self._dataset_definition(definition)
        validated = _validate_parameters(resolved.parameter_model, params)
        return self._source_request_keys(resolved, validated)

    async def plan_workflow(
        self,
        definition: str | WorkflowDefinition[BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
    ) -> WorkflowPlan:
        """Compile and describe a workflow without API or artifact writes."""
        resolved = self._workflow_definition(definition)
        validated = _validate_parameters(resolved.parameter_model, params)
        selected_policy = policy or self._policy
        steps = self._compile(resolved, validated, selected_policy)
        source_count = len(self._source_request_keys(resolved, validated))
        return WorkflowPlan(
            definition_id=resolved.id,
            definition_revision=resolved.revision,
            parameter_fingerprint=parameter_fingerprint(validated),
            steps=steps,
            outputs=tuple(resolved.outputs),
            logical_source_requests=source_count,
            worst_case_http_attempts=source_count * self._max_attempts_per_request,
        )

    async def run_workflow_definition(
        self,
        definition: str | WorkflowDefinition[BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
    ) -> _WorkflowExecution[FrameT]:
        """Execute one finite user workflow through the durable graph engine."""
        await self._ensure_open()
        resolved = self._workflow_definition(definition)
        validated = _validate_parameters(resolved.parameter_model, params)
        selected_policy = policy or self._policy
        self._compile(resolved, validated, selected_policy)
        parameter_digest = parameter_fingerprint(validated)
        parent_run_id = resume_from
        if parent_run_id is None:
            parent_run_id = await self._store.latest_failed_run(
                definition_id=resolved.id,
                parameter_fingerprint=parameter_digest,
            )
        run_id = uuid.uuid4().hex
        await self._store.begin_run(
            run_id=run_id,
            definition_id=resolved.id,
            definition_revision=resolved.revision,
            parameter_fingerprint=parameter_digest,
            parent_run_id=parent_run_id,
        )
        started_at = self._dispatcher.now()
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id=run_id,
                definition_id=resolved.id,
                phase=RunPhase.started,
                outcome=None,
                step_count=len(resolved.nodes),
                duration_seconds=None,
            )
        )
        try:
            with (
                _attempt_budget_scope(selected_policy.max_http_attempts),
                _execution_resources_scope(selected_policy) as resources,
            ):
                values = await self._execute_graph(
                    run_id=run_id,
                    definition=resolved,
                    parameters=validated,
                    policy=selected_policy,
                    parent_run_id=parent_run_id,
                    output_nodes=frozenset(resolved.outputs.values()),
                    resources=resources,
                )
            frames: dict[str, FrameT] = {}
            artifacts: dict[str, ArtifactRef] = {}
            quality: dict[str, tuple[QualityResult, ...]] = {}
            coverage: dict[str, tuple[SourceCoverage, ...]] = {}
            for name, node_id in resolved.outputs.items():
                node = next(item for item in resolved.nodes if item.id == node_id)
                value = values[node_id]
                if value.artifact is None:
                    raise CFBDArtifactError("Workflow output was not persisted")
                frames[name] = await asyncio.to_thread(
                    self._adapter.from_table,
                    endpoint=f"{resolved.id}.{name}",
                    row_model=node.output.row_model,
                    table=value.table,
                )
                artifacts[name] = value.artifact
                quality[name] = value.quality
                coverage[name] = value.coverage
            await self._store.finish_run(run_id, status="success")
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.success,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                )
            )
            return _WorkflowExecution(
                run_id=run_id,
                definition_id=resolved.id,
                frames=MappingProxyType(frames),
                artifacts=MappingProxyType(artifacts),
                reused_steps=tuple(
                    node.id for node in resolved.nodes if values[node.id].reused
                ),
                quality=MappingProxyType(quality),
                coverage=MappingProxyType(coverage),
                parent_run_id=parent_run_id,
            )
        except asyncio.CancelledError:
            await self._store.finish_run(run_id, status="cancelled")
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.cancelled,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category="cancelled",
                )
            )
            raise
        except _StepFailure as failure:
            category = _failure_category(failure.cause)
            await self._store.finish_run(
                run_id,
                status="error",
                failure_step_id=failure.step_id,
                failure_category=category,
            )
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.error,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category=category,
                )
            )
            raise CFBDRunError(
                run_id=run_id,
                step_id=failure.step_id,
                category=category,
            ) from failure.cause
        except Exception as exc:
            category = _failure_category(exc)
            await self._store.finish_run(
                run_id,
                status="error",
                failure_step_id="runner",
                failure_category=category,
            )
            raise CFBDRunError(
                run_id=run_id,
                step_id="runner",
                category=category,
            ) from exc

    async def run_dataset(
        self,
        definition: str | DatasetDefinition[BaseModel, BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
    ) -> DatasetRun[FrameT]:
        """Execute one validated dataset graph and return its selected frame."""
        await self._ensure_open()
        resolved = self._dataset_definition(definition)
        validated = _validate_parameters(resolved.parameter_model, params)
        selected_policy = policy or self._policy
        self._compile(resolved, validated, selected_policy)
        parameter_digest = parameter_fingerprint(validated)
        parent_run_id = resume_from
        if parent_run_id is None:
            parent_run_id = await self._store.latest_failed_run(
                definition_id=resolved.id,
                parameter_fingerprint=parameter_digest,
            )
        run_id = uuid.uuid4().hex
        await self._store.begin_run(
            run_id=run_id,
            definition_id=resolved.id,
            definition_revision=resolved.revision,
            parameter_fingerprint=parameter_digest,
            parent_run_id=parent_run_id,
        )
        started_at = self._dispatcher.now()
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id=run_id,
                definition_id=resolved.id,
                phase=RunPhase.started,
                outcome=None,
                step_count=len(resolved.nodes),
                duration_seconds=None,
            )
        )
        try:
            with (
                _attempt_budget_scope(selected_policy.max_http_attempts),
                _execution_resources_scope(selected_policy) as resources,
            ):
                values = await self._execute_graph(
                    run_id=run_id,
                    definition=resolved,
                    parameters=validated,
                    policy=selected_policy,
                    parent_run_id=parent_run_id,
                    output_nodes=frozenset((resolved.output_node,)),
                    resources=resources,
                )
            result = values[resolved.output_node]
            artifact = result.artifact
            if artifact is None:
                raise CFBDArtifactError("Dataset output was not persisted")
            frame = await asyncio.to_thread(
                self._adapter.from_table,
                endpoint=resolved.id,
                row_model=resolved.output.row_model,
                table=result.table,
            )
            await self._store.finish_run(run_id, status="success")
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.success,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                )
            )
            return DatasetRun(
                run_id=run_id,
                definition_id=resolved.id,
                frame=frame,
                artifact=artifact,
                reused_steps=tuple(
                    node.id for node in resolved.nodes if values[node.id].reused
                ),
                quality=result.quality,
                coverage=result.coverage,
                parent_run_id=parent_run_id,
            )
        except asyncio.CancelledError as exc:
            await self._store.finish_run(run_id, status="cancelled")
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.cancelled,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category="cancelled",
                )
            )
            raise exc
        except _StepFailure as failure:
            category = _failure_category(failure.cause)
            await self._store.finish_run(
                run_id,
                status="error",
                failure_step_id=failure.step_id,
                failure_category=category,
            )
            self._dispatcher.emit(
                AnalyticsRunEvent(
                    run_id=run_id,
                    definition_id=resolved.id,
                    phase=RunPhase.finished,
                    outcome=AnalyticsOutcome.error,
                    step_count=len(resolved.nodes),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category=category,
                )
            )
            raise CFBDRunError(
                run_id=run_id, step_id=failure.step_id, category=category
            ) from failure.cause
        except Exception as exc:
            category = _failure_category(exc)
            await self._store.finish_run(
                run_id,
                status="error",
                failure_step_id="runner",
                failure_category=category,
            )
            raise CFBDRunError(
                run_id=run_id, step_id="runner", category=category
            ) from exc

    async def _execute_graph(
        self,
        *,
        run_id: str,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        parameters: BaseModel,
        policy: ExecutionPolicy,
        parent_run_id: str | None,
        output_nodes: frozenset[str],
        resources: _ExecutionResources,
    ) -> dict[str, _StepValue]:
        by_id = {node.id: node for node in definition.nodes}
        pending = set(by_id)
        values: dict[str, _StepValue] = {}
        forced = _forced_with_descendants(definition.nodes, policy.force_steps)
        while pending:
            ready = sorted(
                node_id
                for node_id in pending
                if _dependencies(by_id[node_id]).issubset(values)
            )
            if not ready:
                raise CFBDDefinitionError("Compiled graph cannot make progress")
            tasks: dict[str, asyncio.Task[_StepValue]] = {}
            try:
                async with asyncio.TaskGroup() as group:
                    for node_id in ready:
                        node = by_id[node_id]
                        tasks[node_id] = group.create_task(
                            self._execute_node(
                                run_id=run_id,
                                definition=definition,
                                node=node,
                                parameters=parameters,
                                dependencies={
                                    dependency: values[dependency]
                                    for dependency in _dependencies(node)
                                },
                                policy=policy,
                                parent_run_id=parent_run_id,
                                is_output=node_id in output_nodes,
                                forced=node_id in forced,
                                resources=resources,
                            )
                        )
            except* _StepFailure as failures:
                failure = _first_step_failure(failures)
                raise failure from failure.cause
            for node_id in ready:
                values[node_id] = tasks[node_id].result()
                pending.remove(node_id)
        return values

    async def _execute_node(
        self,
        *,
        run_id: str,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        node: DefinitionNode,
        parameters: BaseModel,
        dependencies: Mapping[str, _StepValue],
        policy: ExecutionPolicy,
        parent_run_id: str | None,
        is_output: bool,
        forced: bool,
        resources: _ExecutionResources,
    ) -> _StepValue:
        started_at = self._dispatcher.now()
        self._dispatcher.emit(
            AnalyticsStepEvent(
                run_id=run_id,
                step_id=node.id,
                operation_id=node.operation_id,
                phase=StepPhase.started,
                outcome=None,
                row_count=None,
                duration_seconds=None,
            )
        )
        try:
            if isinstance(node, SourceNode):
                value = await self._execute_source(
                    run_id=run_id,
                    definition=definition,
                    node=node,
                    parameters=parameters,
                    policy=policy,
                    parent_run_id=parent_run_id,
                    is_output=is_output,
                    forced=forced,
                    resources=resources,
                )
            else:
                value = await self._execute_transform(
                    run_id=run_id,
                    definition=definition,
                    node=node,
                    parameters=parameters,
                    dependencies=dependencies,
                    policy=policy,
                    parent_run_id=parent_run_id,
                    is_output=is_output,
                    forced=forced,
                    resources=resources,
                )
            self._dispatcher.emit(
                AnalyticsStepEvent(
                    run_id=run_id,
                    step_id=node.id,
                    operation_id=node.operation_id,
                    phase=(StepPhase.reused if value.reused else StepPhase.finished),
                    outcome=AnalyticsOutcome.success,
                    row_count=len(value.rows),
                    duration_seconds=self._dispatcher.elapsed(started_at),
                )
            )
            return value
        except asyncio.CancelledError:
            self._dispatcher.emit(
                AnalyticsStepEvent(
                    run_id=run_id,
                    step_id=node.id,
                    operation_id=node.operation_id,
                    phase=StepPhase.finished,
                    outcome=AnalyticsOutcome.cancelled,
                    row_count=None,
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category="cancelled",
                )
            )
            raise
        except Exception as exc:
            self._dispatcher.emit(
                AnalyticsStepEvent(
                    run_id=run_id,
                    step_id=node.id,
                    operation_id=node.operation_id,
                    phase=StepPhase.finished,
                    outcome=AnalyticsOutcome.error,
                    row_count=None,
                    duration_seconds=self._dispatcher.elapsed(started_at),
                    failure_category=_failure_category(exc),
                )
            )
            raise _StepFailure(node.id, exc) from exc

    async def _execute_source(
        self,
        *,
        run_id: str,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        node: SourceNode,
        parameters: BaseModel,
        policy: ExecutionPolicy,
        parent_run_id: str | None,
        is_output: bool,
        forced: bool,
        resources: _ExecutionResources,
    ) -> _StepValue:
        operation = endpoint_operation(node.operation_id)
        request = _bound_source_request(node, operation, parameters)
        fingerprint = _source_fingerprint(
            node=node,
            request=request,
            request_contract=operation.request_contract_digest,
            source_scope=self._source_scope,
        )
        if (
            not forced
            and parent_run_id is not None
            and policy.checkpoint is not CheckpointMode.off
            and policy.source_policy is RecoverySourcePolicy.preserve_snapshot
        ):
            recovered = await self._store.run_artifact(
                run_id=parent_run_id,
                step_id=node.id,
                fingerprint=fingerprint,
                contract=node.output,
            )
            if recovered is not None:
                await self._store.record_reuse(
                    run_id=run_id,
                    step_id=node.id,
                    fingerprint=fingerprint,
                    artifact_id=recovered.descriptor.artifact_id,
                )
                return await asyncio.to_thread(
                    _value_from_artifact, recovered, node.output, reused=True
                )

        cache_scope = (
            self._cache_coordinator.mode_scope(CacheMode.refresh)
            if policy.source_policy is RecoverySourcePolicy.refresh
            else None
        )
        source_result = await self._deduplicated_source_fetch(
            resources=resources,
            fingerprint=fingerprint,
            run_id=run_id,
            step_id=node.id,
            operation=operation,
            request=request,
            cache_scope=cache_scope,
        )
        validated, table, quality = await asyncio.to_thread(
            _validate_table, node.output, source_result.rows
        )
        source_validated_at = datetime.now(UTC)
        coverage = (
            SourceCoverage(
                source_id=operation.id,
                state=CoverageState.present if validated else CoverageState.empty,
                row_count=len(validated),
            ),
        )
        return await self._persist_or_keep(
            run_id=run_id,
            definition=definition,
            node=node,
            fingerprint=fingerprint,
            rows=validated,
            table=table,
            quality=quality,
            coverage=coverage,
            upstream_digests=(),
            source_fetched_at=source_result.fetched_at,
            source_validated_at=source_validated_at,
            checkpoint=policy.checkpoint,
            is_output=is_output,
        )

    async def _deduplicated_source_fetch(
        self,
        *,
        resources: _ExecutionResources,
        fingerprint: str,
        run_id: str,
        step_id: str,
        operation: EndpointOperation[BaseModel, BaseModel],
        request: BaseModel,
        cache_scope: CacheModeScope | None,
    ) -> _SourceResult:
        """Fetch one exact source request once per dataset/workflow scope."""
        async with resources.source_lock:
            cached = resources.source_results.get(fingerprint)
            if cached is not None:
                return cached
            source_lock = resources.source_locks.setdefault(fingerprint, asyncio.Lock())
        async with source_lock:
            async with resources.source_lock:
                cached = resources.source_results.get(fingerprint)
                if cached is not None:
                    return cached
            async with resources.retrieval_semaphore:
                with _analytics_correlation(run_id, step_id):
                    if cache_scope is None:
                        rows = await operation.fetch(self._executor, request)
                    else:
                        with cache_scope:
                            rows = await operation.fetch(self._executor, request)
            result = _SourceResult(tuple(rows), datetime.now(UTC))
            async with resources.source_lock:
                resources.source_results[fingerprint] = result
            return result

    async def _execute_transform(
        self,
        *,
        run_id: str,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        node: TransformNode,
        parameters: BaseModel,
        dependencies: Mapping[str, _StepValue],
        policy: ExecutionPolicy,
        parent_run_id: str | None,
        is_output: bool,
        forced: bool,
        resources: _ExecutionResources,
    ) -> _StepValue:
        transform = self._transforms[node.operation_id]
        upstream_digests = tuple(
            dependencies[name].content_digest for name in node.inputs
        )
        fingerprint = _transform_fingerprint(
            node=node,
            parameters=parameters,
            upstream_digests=upstream_digests,
            backend=(
                self._dataframe_backend
                if transform.backend is not TransformBackend.portable
                else None
            ),
        )
        if (
            not forced
            and parent_run_id is not None
            and policy.checkpoint is not CheckpointMode.off
        ):
            recovered = await self._store.run_artifact(
                run_id=parent_run_id,
                step_id=node.id,
                fingerprint=fingerprint,
                contract=node.output,
            )
            if recovered is not None:
                await self._store.record_reuse(
                    run_id=run_id,
                    step_id=node.id,
                    fingerprint=fingerprint,
                    artifact_id=recovered.descriptor.artifact_id,
                )
                return await asyncio.to_thread(
                    _value_from_artifact, recovered, node.output, reused=True
                )

        if (
            not forced
            and transform.deterministic
            and policy.checkpoint is not CheckpointMode.off
        ):
            compatible = await self._store.compatible_artifact(
                fingerprint=fingerprint,
                contract=node.output,
            )
            if compatible is not None:
                await self._store.record_reuse(
                    run_id=run_id,
                    step_id=node.id,
                    fingerprint=fingerprint,
                    artifact_id=compatible.descriptor.artifact_id,
                )
                return await asyncio.to_thread(
                    _value_from_artifact, compatible, node.output, reused=True
                )

        local_lock = self._local_flights.setdefault(fingerprint, asyncio.Lock())
        async with local_lock:
            owner = f"{run_id}:{node.id}:{uuid.uuid4().hex}"
            acquired = await self._store.acquire_lease(
                fingerprint=fingerprint, owner=owner
            )
            if not acquired:
                for _ in range(300):
                    await asyncio.sleep(0.1)
                    compatible = await self._store.compatible_artifact(
                        fingerprint=fingerprint,
                        contract=node.output,
                    )
                    if compatible is not None:
                        await self._store.record_reuse(
                            run_id=run_id,
                            step_id=node.id,
                            fingerprint=fingerprint,
                            artifact_id=compatible.descriptor.artifact_id,
                        )
                        return await asyncio.to_thread(
                            _value_from_artifact,
                            compatible,
                            node.output,
                            reused=True,
                        )
                acquired = await self._store.acquire_lease(
                    fingerprint=fingerprint, owner=owner
                )
                if not acquired:
                    raise CFBDArtifactError(
                        "Timed out waiting for analytics step lease"
                    )
            try:
                input_rows = {name: dependencies[name].rows for name in node.inputs}
                async with resources.compute_semaphore:
                    if transform.backend is TransformBackend.portable:
                        callable_ = cast(RecordTransform, transform.callable)
                        produced = await asyncio.to_thread(
                            callable_, input_rows, parameters, node.config
                        )
                    else:
                        produced = await asyncio.to_thread(
                            self._run_frame_transform,
                            transform.callable,
                            transform.backend,
                            dependencies,
                            parameters,
                            node,
                        )
                    validated, table, quality = await asyncio.to_thread(
                        _validate_table, node.output, produced
                    )
                coverage = _merge_coverage(dependencies.values())
                return await self._persist_or_keep(
                    run_id=run_id,
                    definition=definition,
                    node=node,
                    fingerprint=fingerprint,
                    rows=validated,
                    table=table,
                    quality=quality,
                    coverage=coverage,
                    upstream_digests=upstream_digests,
                    source_fetched_at=None,
                    source_validated_at=None,
                    checkpoint=policy.checkpoint,
                    is_output=is_output,
                )
            finally:
                await self._store.release_lease(fingerprint=fingerprint, owner=owner)

    def _run_frame_transform(
        self,
        callable_: object,
        backend: TransformBackend,
        inputs: Mapping[str, _StepValue],
        parameters: BaseModel,
        node: TransformNode,
    ) -> Sequence[BaseModel]:
        frames: dict[str, object] = {}
        for name, value in inputs.items():
            frames[name] = self._adapter.from_models(
                endpoint=node.operation_id,
                row_model=value.row_model,
                models=value.rows,
            )
        if not callable(callable_):
            raise CFBDDefinitionError("Registered transform callable is invalid")
        result = callable_(MappingProxyType(frames), parameters, node.config)
        records: object
        if backend is TransformBackend.pandas:
            if not isinstance(result, pd.DataFrame):
                raise CFBDAnalyticsError("Pandas transform did not return a DataFrame")
            records = result.to_dict(orient="records")
        else:
            try:
                import polars as pl
            except ModuleNotFoundError as exc:
                raise CFBDAnalyticsError(
                    "Polars transform backend is unavailable"
                ) from exc
            if not isinstance(result, pl.DataFrame):
                raise CFBDAnalyticsError("Polars transform did not return a DataFrame")
            records = result.to_dicts()
        return _validate_model_sequence(node.output.row_model, records)

    async def _persist_or_keep(
        self,
        *,
        run_id: str,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        node: DefinitionNode,
        fingerprint: str,
        rows: tuple[BaseModel, ...],
        table: pa.Table,
        quality: tuple[QualityResult, ...],
        coverage: tuple[SourceCoverage, ...],
        upstream_digests: tuple[str, ...],
        source_fetched_at: datetime | None,
        source_validated_at: datetime | None,
        checkpoint: CheckpointMode,
        is_output: bool,
    ) -> _StepValue:
        persist = checkpoint is CheckpointMode.all or is_output
        if checkpoint is CheckpointMode.outputs_only and is_output:
            persist = True
        digest = await asyncio.to_thread(_table_digest, node.output, rows)
        artifact: ArtifactRef | None = None
        if persist:
            stored_fingerprint = (
                fingerprint
                if checkpoint is not CheckpointMode.off
                else hashlib.sha256(
                    canonical_json(["uncheckpointed", run_id, node.id, fingerprint])
                ).hexdigest()
            )
            artifact = await self._store.write_table(
                run_id=run_id,
                step_id=node.id,
                fingerprint=stored_fingerprint,
                definition_id=definition.id,
                definition_revision=definition.revision,
                contract=node.output,
                table=table,
                upstream_digests=upstream_digests,
                source_fetched_at=source_fetched_at,
                source_validated_at=source_validated_at,
                quality=quality,
                coverage=coverage,
            )
            digest = artifact.descriptor.content_digest
            self._dispatcher.emit(
                AnalyticsArtifactEvent(
                    run_id=run_id,
                    step_id=node.id,
                    action=ArtifactAction.committed,
                    kind="table",
                    row_count=len(rows),
                    byte_count=artifact.descriptor.byte_count,
                )
            )
        self._dispatcher.emit(
            AnalyticsValidationEvent(
                run_id=run_id,
                step_id=node.id,
                contract_id=node.output.id,
                passed=True,
                row_count=len(rows),
                failed_checks=0,
            )
        )
        return _StepValue(
            rows=rows,
            row_model=node.output.row_model,
            table=table,
            content_digest=digest,
            artifact=artifact,
            quality=quality,
            coverage=coverage,
            reused=False,
        )

    def _compile(
        self,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        parameters: BaseModel,
        policy: ExecutionPolicy,
    ) -> tuple[PlannedStep, ...]:
        if len(definition.nodes) > policy.max_expanded_nodes:
            raise CFBDDefinitionError("Definition exceeds the expanded-node limit")
        source_fingerprints: set[str] = set()
        planned: list[PlannedStep] = []
        parameter_names = set(parameters.__class__.model_fields)
        for node in _topological_nodes(definition.nodes):
            if isinstance(node, SourceNode):
                operation = endpoint_operation(node.operation_id)
                if operation.revision != node.operation_revision:
                    raise CFBDDefinitionError(
                        "Source operation revision is incompatible"
                    )
                if (
                    operation.output.id != node.output.id
                    or operation.output.schema_digest != node.output.schema_digest
                ):
                    raise CFBDDefinitionError("Source output contract is incompatible")
                for binding in node.bindings.values():
                    if (
                        isinstance(binding, ParameterBinding)
                        and binding.parameter not in parameter_names
                    ):
                        raise CFBDDefinitionError(
                            f"Unknown source parameter binding: {binding.parameter}"
                        )
                request = _bound_source_request(node, operation, parameters)
                source_fingerprints.add(
                    _source_fingerprint(
                        node=node,
                        request=request,
                        request_contract=operation.request_contract_digest,
                        source_scope=self._source_scope,
                    )
                )
                kind = "source"
            else:
                try:
                    transform = self._transforms[node.operation_id]
                except KeyError as exc:
                    raise CFBDDefinitionError(
                        f"Unknown transform operation: {node.operation_id}"
                    ) from exc
                if transform.revision != node.operation_revision:
                    raise CFBDDefinitionError("Transform revision is incompatible")
                if (
                    transform.backend is TransformBackend.pandas
                    and self._dataframe_backend != "pandas"
                ) or (
                    transform.backend is TransformBackend.polars
                    and self._dataframe_backend != "polars"
                ):
                    raise CFBDDefinitionError(
                        "Transform is unavailable for the selected DataFrame backend"
                    )
                kind = "transform"
            planned.append(
                PlannedStep(
                    id=node.id,
                    kind=kind,
                    dependencies=tuple(sorted(_dependencies(node))),
                    operation_id=node.operation_id,
                    checkpoint_candidate=True,
                )
            )
        worst_case = len(source_fingerprints) * self._max_attempts_per_request
        if worst_case > policy.max_http_attempts:
            raise CFBDDefinitionError(
                "Planned worst-case HTTP attempts exceed the execution budget"
            )
        self._dispatcher.emit(
            AnalyticsRunEvent(
                run_id="plan",
                definition_id=definition.id,
                phase=RunPhase.planned,
                outcome=None,
                step_count=len(planned),
                duration_seconds=None,
            )
        )
        return tuple(planned)

    def _source_request_keys(
        self,
        definition: DatasetDefinition[BaseModel, BaseModel]
        | WorkflowDefinition[BaseModel],
        parameters: BaseModel,
    ) -> frozenset[str]:
        keys: set[str] = set()
        for node in definition.nodes:
            if not isinstance(node, SourceNode):
                continue
            operation = endpoint_operation(node.operation_id)
            request = _bound_source_request(node, operation, parameters)
            keys.add(
                _source_fingerprint(
                    node=node,
                    request=request,
                    request_contract=operation.request_contract_digest,
                    source_scope=self._source_scope,
                )
            )
        return frozenset(keys)

    async def _ensure_open(self) -> None:
        async with self._open_lock:
            if not self._opened:
                await self._store.open()
                self._opened = True

    def _dataset_definition(
        self, definition: str | DatasetDefinition[BaseModel, BaseModel]
    ) -> DatasetDefinition[BaseModel, BaseModel]:
        if isinstance(definition, str):
            try:
                resolved = self._catalog[definition]
            except KeyError as exc:
                raise CFBDDefinitionError(
                    f"Unknown dataset definition: {definition}"
                ) from exc
        else:
            resolved = definition
        if not isinstance(resolved, DatasetDefinition):
            raise CFBDDefinitionError("Requested definition is not a dataset")
        return resolved

    def _workflow_definition(
        self, definition: str | WorkflowDefinition[BaseModel]
    ) -> WorkflowDefinition[BaseModel]:
        if isinstance(definition, str):
            try:
                resolved: AnalyticsDefinition = self._catalog[definition]
            except KeyError as exc:
                raise CFBDDefinitionError(
                    f"Unknown workflow definition: {definition}"
                ) from exc
        else:
            resolved = definition
        if not isinstance(resolved, WorkflowDefinition):
            raise CFBDDefinitionError("Requested definition is not a workflow")
        return resolved


def _validate_parameters(
    model: type[BaseModel], params: Mapping[str, object] | BaseModel
) -> BaseModel:
    if isinstance(params, BaseModel):
        if not isinstance(params, model):
            raise CFBDDefinitionError("Definition parameter model is incompatible")
        return params
    try:
        return model.model_validate(dict(params))
    except ValidationError as exc:
        raise CFBDDefinitionError("Analytics parameters are invalid") from exc


def _validate_table(
    contract: TableContract[BaseModel], rows: Sequence[BaseModel]
) -> tuple[tuple[BaseModel, ...], pa.Table, tuple[QualityResult, ...]]:
    validated = _validate_model_sequence(contract.row_model, rows)
    ordered = tuple(
        sorted(validated, key=lambda row: _row_sort_key(row, contract.order_by))
    )
    keys: set[bytes] = set()
    for row in ordered:
        key_values = []
        for name in contract.keys:
            value = getattr(row, name)
            if value is None:
                raise CFBDAnalyticsError("Candidate-key fields cannot be null")
            if isinstance(value, BaseModel):
                key_values.append(value.model_dump(mode="json"))
            else:
                key_values.append(value)
        encoded = canonical_json(key_values)
        if encoded in keys:
            raise CFBDAnalyticsError("Table violates its declared candidate key")
        keys.add(encoded)
    table = _arrow_table_from_models(
        row_model=contract.row_model,
        models=ordered,
    )
    quality = (
        QualityResult("row_contract", True, 0),
        QualityResult("candidate_key_unique", True, 0),
        QualityResult("deterministic_order", True, 0),
    )
    return ordered, table, quality


def _validate_model_sequence(
    row_model: type[BaseModel], values: object
) -> tuple[BaseModel, ...]:
    adapter = _list_adapter(row_model)
    try:
        return tuple(adapter.validate_python(values))
    except ValidationError as exc:
        raise CFBDAnalyticsError("Transform output violates its row contract") from exc


def _value_from_artifact(
    artifact: ArtifactRef,
    contract: TableContract[BaseModel],
    *,
    reused: bool,
) -> _StepValue:
    table = artifact.load_table()
    adapter = _list_adapter(contract.row_model)
    rows = tuple(
        _models_from_arrow_table(
            row_model=contract.row_model,
            response_adapter=adapter,
            table=table,
        )
    )
    return _StepValue(
        rows=rows,
        row_model=contract.row_model,
        table=table,
        content_digest=artifact.descriptor.content_digest,
        artifact=artifact,
        quality=artifact.descriptor.quality,
        coverage=artifact.descriptor.coverage,
        reused=reused,
    )


def _bound_source_request(
    node: SourceNode,
    operation: EndpointOperation[BaseModel, BaseModel],
    parameters: BaseModel,
) -> BaseModel:
    """Validate one registered request assembled from explicit bindings."""
    request_values: dict[str, object] = {}
    for name, binding in node.bindings.items():
        if isinstance(binding, ParameterBinding):
            request_values[name] = getattr(parameters, binding.parameter)
        elif isinstance(binding, LiteralBinding):
            request_values[name] = binding.value
        else:
            raise AssertionError("Unsupported source value binding")
    try:
        return operation.request_model.model_validate(request_values)
    except ValidationError as exc:
        raise CFBDDefinitionError("Analytics source request is invalid") from exc


def _source_fingerprint(
    *,
    node: SourceNode,
    request: BaseModel,
    request_contract: str,
    source_scope: str,
) -> str:
    payload = {
        "engine": _ENGINE_VERSION,
        "kind": "source",
        "operation": [node.operation_id, node.operation_revision],
        "request_contract": request_contract,
        "request": request.model_dump(
            mode="json", by_alias=True, exclude_none=False, exclude_unset=False
        ),
        "source_scope": source_scope,
        "output": [
            node.output.id,
            node.output.revision,
            node.output.schema_digest,
        ],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _transform_fingerprint(
    *,
    node: TransformNode,
    parameters: BaseModel,
    upstream_digests: tuple[str, ...],
    backend: str | None,
) -> str:
    payload = {
        "engine": _ENGINE_VERSION,
        "kind": "transform",
        "operation": [node.operation_id, node.operation_revision],
        "parameters": parameters.model_dump(
            mode="json", by_alias=True, exclude_none=False, exclude_unset=False
        ),
        "config": dict(node.config),
        "upstream": list(upstream_digests),
        "backend": backend,
        "output": [
            node.output.id,
            node.output.revision,
            node.output.schema_digest,
        ],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _table_digest(contract: TableContract[BaseModel], rows: Sequence[BaseModel]) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "contract": [
                    contract.id,
                    contract.revision,
                    contract.schema_digest,
                ],
                "rows": [row.model_dump(mode="json") for row in rows],
            }
        )
    ).hexdigest()


def _dependencies(node: DefinitionNode) -> frozenset[str]:
    return frozenset(node.inputs) if isinstance(node, TransformNode) else frozenset()


def _topological_nodes(nodes: tuple[DefinitionNode, ...]) -> tuple[DefinitionNode, ...]:
    by_id = {node.id: node for node in nodes}
    pending = set(by_id)
    result: list[DefinitionNode] = []
    completed: set[str] = set()
    while pending:
        ready = sorted(
            node_id
            for node_id in pending
            if _dependencies(by_id[node_id]).issubset(completed)
        )
        if not ready:
            raise CFBDDefinitionError("Definition graph contains a cycle")
        for node_id in ready:
            result.append(by_id[node_id])
            completed.add(node_id)
            pending.remove(node_id)
    return tuple(result)


def _forced_with_descendants(
    nodes: tuple[DefinitionNode, ...], force_steps: frozenset[str]
) -> frozenset[str]:
    by_id = {node.id: node for node in nodes}
    unknown = force_steps.difference(by_id)
    if unknown:
        raise CFBDDefinitionError(f"Unknown forced steps: {sorted(unknown)!r}")
    forced = set(force_steps)
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.id not in forced and _dependencies(node).intersection(forced):
                forced.add(node.id)
                changed = True
    return frozenset(forced)


def _merge_coverage(values: Iterable[_StepValue]) -> tuple[SourceCoverage, ...]:
    by_source: dict[str, SourceCoverage] = {}
    for value in values:
        for coverage in value.coverage:
            by_source[coverage.source_id] = coverage
    return tuple(by_source[key] for key in sorted(by_source))


def _row_sort_key(
    row: BaseModel, fields: tuple[str, ...]
) -> tuple[tuple[int, object], ...]:
    return tuple(_sort_value(getattr(row, name)) for name in fields)


def _sort_value(value: object) -> tuple[int, object]:
    if value is None:
        return (1, "")
    if isinstance(value, BaseModel):
        return (0, canonical_json(value.model_dump(mode="json")).decode())
    if isinstance(value, StrEnum):
        return (0, value.value)
    return (0, value)


def _list_adapter[ModelT: BaseModel](
    row_model: type[ModelT],
) -> TypeAdapter[list[ModelT]]:
    """Construct a typed Pydantic adapter from a runtime row model."""
    # The dynamic alias is the documented Pydantic boundary for runtime models.
    return TypeAdapter(list[row_model])  # type: ignore[valid-type]


def _first_step_failure(
    group: BaseExceptionGroup[_StepFailure],
) -> _StepFailure:
    """Return the first leaf step failure from a TaskGroup exception tree."""
    for exception in group.exceptions:
        if isinstance(exception, _StepFailure):
            return exception
        if isinstance(exception, BaseExceptionGroup):
            return _first_step_failure(exception)
    raise AssertionError("Matched step-failure group contained no step failure")


__all__ = ["DatasetRun", "_AnalyticsEngine"]
