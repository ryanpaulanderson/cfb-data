"""Execute validated source nodes concurrently in the client coordinator."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import cast

import pyarrow as pa
from pydantic import BaseModel

from cfb_data._executor import _EndpointExecutor
from cfb_data._observability import _analytics_retrieval_context, _failure_category
from cfb_data._operation import _ManyEndpointOperation
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
    _logical_schema,
    _logical_schema_digest,
)
from cfb_data._transport import _attempt_reservation_context

from ._artifacts import _TableArtifactCodec
from ._checkpoints import (
    _checkpoint_scope,
    _node_fingerprint,
    _OutputContractIdentity,
    _SourceBehavior,
)
from ._compiler import _digest
from ._execution import _NodeResult, _resolve_arguments
from ._graph import _CompiledNode
from ._observability import _AnalyticsDispatcher
from ._persistence import (
    _ArtifactObjectStore,
    _CheckpointCandidate,
    _NodeState,
    _RunDatabase,
    _StoredArtifact,
)
from ._recipes import SourceRecipe
from .errors import CFBDArtifactCorruptionError, CFBDRecipeCompilationError
from .observability import (
    AnalyticsEvent,
    AnalyticsEventType,
    AnalyticsOutcome,
)


class _EndpointSourceContext:
    """Allow one source body to issue exactly one descriptor-owned retrieval."""

    def __init__(
        self,
        runner: _SourceRunner,
        node: _CompiledNode,
        operation: _ManyEndpointOperation[BaseModel, BaseModel],
    ) -> None:
        """Bind a source node to its one endpoint operation."""
        self._runner = runner
        self._node = node
        self._operation = operation
        self._used = False

    async def retrieve(self, **parameters: object) -> list[BaseModel]:
        """Return validated rows from the coordinator-owned endpoint executor."""
        if self._used:
            raise CFBDRecipeCompilationError(
                "A source boundary may retrieve its endpoint only once"
            )
        self._used = True
        return await self._runner._retrieve(self._node, self._operation, parameters)


class _SourceRunner:
    """Own bounded source concurrency, deduplication, and durable commits."""

    def __init__(
        self,
        *,
        endpoint_executor: _EndpointExecutor,
        database: _RunDatabase,
        object_store: _ArtifactObjectStore,
        run_id: str,
        credential_scope: str,
        parent_run_id: str | None,
        source_behavior: _SourceBehavior,
        concurrency: int,
        dispatcher: _AnalyticsDispatcher,
    ) -> None:
        """Initialize one run-scoped source coordinator."""
        if concurrency < 1:
            raise ValueError("Source concurrency must be positive")
        self._endpoint_executor = endpoint_executor
        self._database = database
        self._object_store = object_store
        self._run_id = run_id
        self._credential_scope = credential_scope
        self._parent_run_id = parent_run_id
        self._source_behavior = source_behavior
        self._semaphore = asyncio.Semaphore(concurrency)
        self._dispatcher = dispatcher
        self._retrievals: dict[str, asyncio.Task[list[BaseModel]]] = {}

    async def run_batch(
        self,
        nodes: Sequence[_CompiledNode],
        results: Mapping[str, _NodeResult],
    ) -> Mapping[str, _NodeResult]:
        """Execute a deterministic ready batch and cancel siblings on failure."""
        tasks: list[asyncio.Task[tuple[str, _NodeResult]]] = []
        for node in nodes:
            if node.kind != "source":
                raise CFBDRecipeCompilationError(
                    "Source runner accepts only compiled source nodes"
                )
            task = asyncio.create_task(
                self._run_node(node, results),
                name=f"cfb-data-source:{node.node_id}",
            )
            tasks.append(task)
        if not tasks:
            return {}
        try:
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
        except asyncio.CancelledError:
            await _cancel_and_await(tasks)
            await _cancel_and_await(tuple(self._retrievals.values()))
            raise
        failure = next(
            (
                task.exception()
                for task in done
                if not task.cancelled() and task.exception() is not None
            ),
            None,
        )
        if failure is not None:
            await _cancel_and_await(pending)
            await _cancel_and_await(tuple(self._retrievals.values()))
            await asyncio.gather(*done, return_exceptions=True)
            raise failure
        if pending:
            await asyncio.gather(*pending)
        return {
            node_id: result for node_id, result in (task.result() for task in tasks)
        }

    async def _run_node(
        self,
        node: _CompiledNode,
        results: Mapping[str, _NodeResult],
    ) -> tuple[str, _NodeResult]:
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
            allow_node_values=False,
        )
        operation = _operation(node)
        identity = _AnalyticsTableIdentity(
            output_id=operation.id,
            revision=operation.revision,
        )
        output = _OutputContractIdentity(
            name="value",
            output_id=operation.id,
            revision=operation.revision,
            schema_digest=_logical_schema_digest(_logical_schema(operation.row_model)),
            codec_id=_TableArtifactCodec.codec_id,
            codec_version=_TableArtifactCodec.codec_version,
        )
        fingerprint = _node_fingerprint(
            node,
            parameters=parameters,
            upstream=(),
            outputs=(output,),
            backend="pandas",
        )
        if fingerprint is None:
            raise AssertionError("Endpoint sources must have durable identity")
        scope = _checkpoint_scope(
            node,
            parent_run_id=self._parent_run_id,
            source_behavior=self._source_behavior,
        )
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
                operation,
                identity,
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
            recipe = cast(SourceRecipe[..., object], node.recipe)
            context = _EndpointSourceContext(self, node, operation)
            value = await recipe._execute_source(context, parameters)
            rows = operation.response_adapter.validate_python(value)
            artifact = await asyncio.to_thread(
                self._store_and_bind_rows,
                rows,
                operation.row_model,
                identity,
                node.node_id,
                fingerprint,
            )
        except asyncio.CancelledError:
            await asyncio.to_thread(
                self._record_terminal_node,
                node.node_id,
                "cancelled",
                "cancelled",
            )
            self._emit(
                AnalyticsEventType.step_cancelled,
                node.node_id,
                outcome=AnalyticsOutcome.cancelled,
                duration=time.monotonic() - started,
            )
            raise
        except Exception as exc:
            await asyncio.to_thread(
                self._record_terminal_node,
                node.node_id,
                "failed",
                _failure_category(exc),
            )
            self._emit(
                AnalyticsEventType.step_failed,
                node.node_id,
                outcome=AnalyticsOutcome.error,
                failure_category=_failure_category(exc),
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
            row_model=operation.row_model,
        )

    async def _retrieve(
        self,
        node: _CompiledNode,
        operation: _ManyEndpointOperation[BaseModel, BaseModel],
        parameters: Mapping[str, object],
    ) -> list[BaseModel]:
        request = operation.resolve(None, dict(parameters))
        serialized = operation.serialized_parameters(request)
        retrieval_key = _digest(
            {
                "operation": operation.id,
                "revision": operation.revision,
                "parameters": serialized,
                "contract": operation.response_contract,
            }
        )
        task = self._retrievals.get(retrieval_key)
        if task is None:
            task = asyncio.create_task(
                self._retrieve_once(node, operation, request),
                name=f"cfb-data-retrieval:{operation.id}",
            )
            self._retrievals[retrieval_key] = task
        return await asyncio.shield(task)

    async def _retrieve_once(
        self,
        node: _CompiledNode,
        operation: _ManyEndpointOperation[BaseModel, BaseModel],
        request: BaseModel,
    ) -> list[BaseModel]:
        async def reserve(endpoint: str, attempt: int) -> None:
            record = await asyncio.to_thread(
                self._database.reserve_attempt,
                run_id=self._run_id,
                node_id=node.node_id,
                endpoint=endpoint,
                retry_number=attempt,
            )
            self._dispatcher.emit(
                AnalyticsEvent(
                    event_type=AnalyticsEventType.source_attempt_reserved,
                    run_id=self._run_id,
                    node_id=node.node_id,
                    attempt_id=str(record.ordinal),
                )
            )

        async with self._semaphore:
            with (
                _analytics_retrieval_context(self._run_id, node.node_id),
                _attempt_reservation_context(reserve),
            ):
                return await operation.fetch(self._endpoint_executor, request)

    async def _load_candidate(
        self,
        node: _CompiledNode,
        operation: _ManyEndpointOperation[BaseModel, BaseModel],
        identity: _AnalyticsTableIdentity,
        fingerprint: str,
        candidate: _CheckpointCandidate,
    ) -> _NodeResult | None:
        try:
            rows = await asyncio.to_thread(
                self._load_rows,
                operation,
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
            row_model=operation.row_model,
        )

    def _store_and_bind_rows(
        self,
        rows: Sequence[BaseModel],
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        node_id: str,
        fingerprint: str,
    ) -> _StoredArtifact:
        """Stage, publish, and durably bind source rows under one reservation."""
        table: pa.Table = _analytics_arrow_table_from_models(
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
            artifact, _ = self._database.publish_completed_node(
                run_id=self._run_id,
                node_id=node_id,
                output_name="value",
                node_fingerprint=fingerprint,
                staged=staged,
                object_store=self._object_store,
                placement="coordinator",
            )
            return artifact

    def _load_rows(
        self,
        operation: _ManyEndpointOperation[BaseModel, BaseModel],
        identity: _AnalyticsTableIdentity,
        candidate: _CheckpointCandidate,
    ) -> list[BaseModel]:
        """Load and fully validate one source checkpoint off the event loop."""
        table = _TableArtifactCodec().load(
            directory=self._object_store.directory(candidate.binding.content_digest),
            manifest=candidate.manifest,
            row_model=operation.row_model,
            identity=identity,
        )
        return _analytics_models_from_arrow_table(
            row_model=operation.row_model,
            response_adapter=operation.response_adapter,
            table=table,
            identity=identity,
        )

    def _record_terminal_node(
        self,
        node_id: str,
        state: _NodeState,
        failure_category: str,
    ) -> None:
        self._database.transition_node(
            self._run_id,
            node_id,
            state,
            failure_category=failure_category,
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
                placement="coordinator",
                artifact_digest=artifact,
                row_count=row_count,
                failure_category=failure_category,
                duration_seconds=duration,
            )
        )


def _operation(
    node: _CompiledNode,
) -> _ManyEndpointOperation[BaseModel, BaseModel]:
    operation = node.declaration.operation
    if not isinstance(operation, _ManyEndpointOperation):
        raise CFBDRecipeCompilationError(
            "This source has no executable endpoint operation descriptor"
        )
    return cast(_ManyEndpointOperation[BaseModel, BaseModel], operation)


async def _cancel_and_await[ValueT](
    tasks: Iterable[asyncio.Task[ValueT]],
) -> None:
    """Cancel every unfinished task and retrieve all terminal outcomes."""
    owned = tuple(tasks)
    for task in owned:
        if not task.done():
            task.cancel()
    await asyncio.gather(*owned, return_exceptions=True)


__all__: tuple[str, ...] = ()
