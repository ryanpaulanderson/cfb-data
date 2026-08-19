"""Execute pure local transform and dataset validation boundaries."""

from __future__ import annotations

import asyncio
import inspect
import time
import types
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._observability import _failure_category
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
    _logical_schema,
    _logical_schema_digest,
)

from ._artifacts import _TableArtifactCodec
from ._checkpoints import (
    _checkpoint_scope,
    _node_fingerprint,
    _OutputContractIdentity,
    _SourceBehavior,
    _UpstreamArtifactIdentity,
)
from ._compiler import _digest
from ._execution import _NodeResult, _resolve_arguments
from ._graph import _CompiledNode, _ValueRef
from ._observability import _AnalyticsDispatcher
from ._persistence import (
    _ArtifactObjectStore,
    _CheckpointCandidate,
    _NodeState,
    _RunDatabase,
    _StoredArtifact,
)
from ._recipes import StepRecipe
from .errors import CFBDArtifactCorruptionError, CFBDRecipeCompilationError
from .observability import AnalyticsEvent, AnalyticsEventType, AnalyticsOutcome

type _Backend = Literal["pandas", "polars"]


class _LocalTransformProvider:
    """Run synchronous trusted transforms off-loop with bounded admission."""

    def __init__(self, *, concurrency: int) -> None:
        """Initialize a local compute provider."""
        if concurrency < 1:
            raise ValueError("Local compute concurrency must be positive")
        self._semaphore = asyncio.Semaphore(concurrency)

    async def execute(
        self,
        recipe: StepRecipe[..., object],
        parameters: Mapping[str, object],
    ) -> object:
        """Execute one step while deterministically owning background work."""
        if recipe._is_async:
            result = recipe._execute_step(parameters)
            if not inspect.isawaitable(result):
                raise TypeError("Async step did not return an awaitable")
            return await result
        async with self._semaphore:
            worker = asyncio.create_task(
                asyncio.to_thread(recipe._execute_step, parameters),
                name=f"cfb-data-local-transform:{recipe.id or recipe.__qualname__}",
            )
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                await asyncio.gather(worker, return_exceptions=True)
                raise


class _TransformRunner:
    """Own local transform validation, checkpointing, and node evidence."""

    def __init__(
        self,
        *,
        provider: _LocalTransformProvider,
        database: _RunDatabase,
        object_store: _ArtifactObjectStore,
        run_id: str,
        credential_scope: str,
        parent_run_id: str | None,
        source_behavior: _SourceBehavior,
        backend: _Backend,
        dispatcher: _AnalyticsDispatcher,
    ) -> None:
        """Initialize one run-scoped local transformation runner."""
        self._provider = provider
        self._database = database
        self._object_store = object_store
        self._run_id = run_id
        self._credential_scope = credential_scope
        self._parent_run_id = parent_run_id
        self._source_behavior = source_behavior
        self._backend = backend
        self._dispatcher = dispatcher

    async def run_batch(
        self,
        nodes: Sequence[_CompiledNode],
        results: Mapping[str, _NodeResult],
    ) -> Mapping[str, _NodeResult]:
        """Execute ready local nodes and cancel all siblings on failure."""
        tasks = [
            asyncio.create_task(
                self._run_node(node, results),
                name=f"cfb-data-transform:{node.node_id}",
            )
            for node in nodes
        ]
        if not tasks:
            return {}
        try:
            return {node_id: result for node_id, result in await asyncio.gather(*tasks)}
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _run_node(
        self,
        node: _CompiledNode,
        results: Mapping[str, _NodeResult],
    ) -> tuple[str, _NodeResult]:
        if node.kind not in {"step", "dataset"}:
            raise CFBDRecipeCompilationError(
                "Local transform runner accepts only steps and datasets"
            )
        await asyncio.to_thread(
            self._database.transition_node,
            self._run_id,
            node.node_id,
            "ready",
        )
        self._emit(AnalyticsEventType.step_ready, node.node_id)
        parameters = _resolve_arguments(
            node.arguments,
            results,
            allow_node_values=True,
        )
        row_model = _declared_row_model(node)
        output_identity = _output_identity(node)
        output_contract = _OutputContractIdentity(
            name="value",
            output_id=output_identity.output_id,
            revision=output_identity.revision,
            schema_digest=_logical_schema_digest(_logical_schema(row_model)),
            codec_id=_TableArtifactCodec.codec_id,
            codec_version=_TableArtifactCodec.codec_version,
        )
        upstream = _upstream_identities(node, results)
        fingerprint = _node_fingerprint(
            node,
            parameters=_semantic_parameters(node, parameters),
            upstream=upstream,
            outputs=(output_contract,),
            backend=self._backend,
        )
        scope = _checkpoint_scope(
            node,
            parent_run_id=self._parent_run_id,
            source_behavior=self._source_behavior,
        )
        if fingerprint is not None:
            candidate = await asyncio.to_thread(
                self._database.find_checkpoint,
                node_fingerprint=fingerprint,
                output_name="value",
                scope=scope,
                parent_run_id=self._parent_run_id,
                credential_scope=self._credential_scope,
            )
            if candidate is not None:
                reused = await self._load_candidate(
                    node,
                    row_model,
                    output_identity,
                    fingerprint,
                    candidate,
                )
                if reused is not None:
                    return node.node_id, reused

        await asyncio.to_thread(
            self._database.transition_node,
            self._run_id,
            node.node_id,
            "running",
        )
        self._emit(AnalyticsEventType.step_started, node.node_id)
        started = time.monotonic()
        try:
            raw = await self._compute(node, parameters)
            rows, artifact = await asyncio.to_thread(
                self._validate_and_store,
                raw,
                row_model,
                output_identity,
                node,
            )
            if fingerprint is None:
                fingerprint = _digest(
                    {
                        "originating_run": self._run_id,
                        "node": node.node_id,
                        "artifact": artifact.content_digest,
                    }
                )
            await asyncio.to_thread(
                self._database.bind_completed_node,
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=fingerprint,
                artifact=artifact,
                placement="local",
            )
        except asyncio.CancelledError:
            await self._terminal(node.node_id, "cancelled", "cancelled")
            self._emit(
                AnalyticsEventType.step_cancelled,
                node.node_id,
                outcome=AnalyticsOutcome.cancelled,
                duration=time.monotonic() - started,
            )
            raise
        except Exception as exc:
            category = _failure_category(exc)
            await self._terminal(node.node_id, "failed", category)
            self._emit(
                AnalyticsEventType.step_failed,
                node.node_id,
                outcome=AnalyticsOutcome.error,
                failure_category=category,
                duration=time.monotonic() - started,
            )
            raise
        self._emit(
            AnalyticsEventType.step_completed,
            node.node_id,
            outcome=AnalyticsOutcome.success,
            artifact=artifact.content_digest,
            row_count=len(rows),
            duration=time.monotonic() - started,
        )
        return node.node_id, _NodeResult(
            value=rows,
            artifact=artifact,
            node_fingerprint=fingerprint,
            row_model=row_model,
        )

    async def _compute(
        self,
        node: _CompiledNode,
        parameters: Mapping[str, object],
    ) -> object:
        if node.kind == "dataset":
            return parameters["value"]
        recipe = cast(StepRecipe[..., object], node.recipe)
        return await self._provider.execute(recipe, parameters)

    def _validate_and_store(
        self,
        raw: object,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        node: _CompiledNode,
    ) -> tuple[list[BaseModel], _StoredArtifact]:
        try:
            rows = _row_list_adapter(row_model).validate_python(raw)
        except ValidationError as exc:
            raise CFBDRecipeCompilationError(
                "Transform output violates its declared row contract"
            ) from exc
        if node.kind == "dataset":
            _validate_dataset_quality(node, rows)
        table = _analytics_arrow_table_from_models(
            row_model=row_model,
            models=rows,
            identity=identity,
        )
        with self._object_store.staging_directory() as directory:
            staged = _TableArtifactCodec().stage(
                directory=directory,
                table=table,
                row_model=row_model,
                identity=identity,
            )
            artifact = self._object_store.publish(staged)
        return rows, artifact

    async def _load_candidate(
        self,
        node: _CompiledNode,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        fingerprint: str,
        candidate: _CheckpointCandidate,
    ) -> _NodeResult | None:
        try:
            rows = await asyncio.to_thread(
                self._load_rows,
                row_model,
                identity,
                candidate,
            )
            await asyncio.to_thread(
                self._database.bind_reused_node,
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=fingerprint,
                candidate=candidate,
            )
        except CFBDArtifactCorruptionError:
            self._emit(
                AnalyticsEventType.checkpoint_corrupt,
                node.node_id,
                outcome=AnalyticsOutcome.corrupt,
            )
            return None
        self._emit(
            AnalyticsEventType.step_reused,
            node.node_id,
            outcome=AnalyticsOutcome.reused,
            artifact=candidate.binding.content_digest,
            row_count=len(rows),
        )
        return _NodeResult(
            value=rows,
            artifact=_StoredArtifact(
                content_digest=candidate.binding.content_digest,
                manifest=candidate.manifest,
            ),
            node_fingerprint=fingerprint,
            row_model=row_model,
        )

    def _load_rows(
        self,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        candidate: _CheckpointCandidate,
    ) -> list[BaseModel]:
        table = _TableArtifactCodec().load(
            directory=self._object_store.directory(candidate.binding.content_digest),
            manifest=candidate.manifest,
            row_model=row_model,
            identity=identity,
        )
        return _analytics_models_from_arrow_table(
            row_model=row_model,
            response_adapter=_row_list_adapter(row_model),
            table=table,
            identity=identity,
        )

    async def _terminal(
        self,
        node_id: str,
        state: _NodeState,
        category: str,
    ) -> None:
        await asyncio.to_thread(
            self._database.transition_node,
            self._run_id,
            node_id,
            state,
            failure_category=category,
        )

    def _emit(
        self,
        event_type: AnalyticsEventType,
        node_id: str,
        *,
        outcome: AnalyticsOutcome | None = None,
        artifact: str | None = None,
        row_count: int | None = None,
        failure_category: str | None = None,
        duration: float | None = None,
    ) -> None:
        self._dispatcher.emit(
            AnalyticsEvent(
                event_type=event_type,
                run_id=self._run_id,
                node_id=node_id,
                outcome=outcome,
                placement="local",
                artifact_digest=artifact,
                row_count=row_count,
                failure_category=failure_category,
                duration_seconds=duration,
            )
        )


def _declared_row_model(node: _CompiledNode) -> type[BaseModel]:
    output_type = node.declaration.output_type
    if not isinstance(output_type, type) or not issubclass(output_type, BaseModel):
        raise CFBDRecipeCompilationError(
            "Table steps and datasets require a declared Pydantic row model"
        )
    return output_type


def _output_identity(node: _CompiledNode) -> _AnalyticsTableIdentity:
    recipe_id = node.declaration.recipe_id
    revision = node.declaration.revision
    if recipe_id is None or revision is None:
        return _AnalyticsTableIdentity(
            output_id=f"notebook.{_digest(node.node_id)[:32]}",
            revision=1,
        )
    return _AnalyticsTableIdentity(output_id=recipe_id, revision=revision)


def _upstream_identities(
    node: _CompiledNode,
    results: Mapping[str, _NodeResult],
) -> tuple[_UpstreamArtifactIdentity, ...]:
    return tuple(
        _UpstreamArtifactIdentity(
            dependency=dependency,
            output_name="value",
            content_digest=results[dependency].artifact.content_digest,
        )
        for dependency in node.dependencies
    )


def _semantic_parameters(
    node: _CompiledNode,
    resolved: Mapping[str, object],
) -> dict[str, object]:
    """Retain literals and binding shape without hashing upstream row values."""
    semantic: dict[str, object] = {}
    for name, argument in node.arguments.items():
        if argument.kind == "literal":
            semantic[name] = resolved[name]
            continue
        if argument.kind == "node":
            node_id = getattr(argument.value, "node_id", None)
            semantic[name] = {
                "upstream_index": node.dependencies.index(node_id),
            }
            continue
        scalar = cast(_ValueRef, argument.value)
        reference = scalar.path
        expected_type = scalar.expected_type
        if not isinstance(reference, tuple) or not isinstance(expected_type, type):
            raise CFBDRecipeCompilationError("Scalar binding metadata is invalid")
        semantic[name] = {
            "upstream_index": node.dependencies.index(scalar.node_id),
            "path": reference,
            "type": f"{expected_type.__module__}:{expected_type.__qualname__}",
        }
    return semantic


def _validate_dataset_quality(
    node: _CompiledNode,
    rows: Sequence[BaseModel],
) -> None:
    """Validate declared uniqueness and preexisting deterministic ordering."""
    keys = node.declaration.keys
    if keys:
        seen: set[tuple[object, ...]] = set()
        for row in rows:
            key = tuple(getattr(row, field) for field in keys)
            if any(value is None for value in key):
                raise ValueError("Dataset candidate keys cannot contain nulls")
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ValueError("Dataset candidate keys must be hashable") from exc
            if duplicate:
                raise ValueError("Dataset candidate keys are not unique")
    order_by = node.declaration.order_by
    if order_by:
        order = [tuple(getattr(row, field) for field in order_by) for row in rows]
        try:
            if order != sorted(order):
                raise ValueError("Dataset rows violate declared deterministic order")
        except TypeError as exc:
            raise ValueError(
                "Dataset ordering fields are not mutually comparable"
            ) from exc


def _row_list_adapter(
    row_model: type[BaseModel],
) -> TypeAdapter[list[BaseModel]]:
    """Build a typed list adapter from a runtime-declared row model."""
    annotation = types.GenericAlias(list, row_model)
    return cast(TypeAdapter[list[BaseModel]], TypeAdapter(annotation))


__all__: tuple[str, ...] = ()
