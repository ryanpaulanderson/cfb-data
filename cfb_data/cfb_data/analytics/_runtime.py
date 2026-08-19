"""Coordinate one durable recipe run through shared execution boundaries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, cast

from pydantic import BaseModel

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._observability import _failure_category

from ._checkpoints import (
    _node_fingerprint,
    _OutputContractIdentity,
    _UpstreamArtifactIdentity,
)
from ._compiler import _CompilableRecipe
from ._compute import _LocalTransformProvider, _TransformExecutorSession
from ._dask import _DaskTransformProvider
from ._execution import _NodeResult
from ._graph import _CompiledGraph, _CompiledNode
from ._observability import _AnalyticsDispatcher
from ._persistence import _analytics_root, _ArtifactObjectStore, _RunDatabase
from ._sources import _SourceRunner
from ._transforms import _TransformRunner
from .config import AnalyticsConfig
from .errors import CFBDRecipeCompilationError, CFBDRunError
from .observability import AnalyticsEvent, AnalyticsEventType, AnalyticsOutcome
from .planning import ExecutionPolicy, _plan_recipe
from .results import ArtifactRef, RecipeRun, RunNodeEvidence, WorkflowOutputs

type SourceBehavior = Literal["preserve_snapshot", "normal_freshness", "refresh"]


class _RuntimeBridge(Protocol):
    """Describe client-owned dependencies used by one coordinator run."""

    executor: _EndpointExecutor
    dataframe_adapter: _DataFrameAdapter[object]
    dataframe_backend: Literal["pandas", "polars"]
    credential_scope: str
    config: object | None


class _RuntimeClient(Protocol):
    """Expose the private client bridge without adding a public resource."""

    def _analytics_bridge(self) -> _RuntimeBridge: ...


def _execute_direct(
    recipe: _CompilableRecipe,
    client: object,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> Awaitable[object]:
    """Return the direct eager-value execution awaitable for one recipe."""

    async def execute() -> object:
        run = await _execute_run(
            recipe,
            client,
            args,
            kwargs,
            policy=None,
            resume_from=None,
            source_behavior=None,
        )
        return run.value

    return execute()


async def _execute_run(
    recipe: _CompilableRecipe,
    client: object,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    *,
    policy: ExecutionPolicy | None,
    resume_from: str | None,
    source_behavior: SourceBehavior | None,
) -> RecipeRun[object]:
    """Execute a compiled recipe and return durable public evidence."""
    selected = policy or ExecutionPolicy()
    _, graph = _plan_recipe(recipe, client, args, kwargs, selected)
    bridge = _runtime_bridge(client)
    config = (
        bridge.config
        if isinstance(bridge.config, AnalyticsConfig)
        else AnalyticsConfig()
    )
    root = _analytics_root(config)
    database = await asyncio.to_thread(_RunDatabase, root / "runs.sqlite3")
    try:
        store = await asyncio.to_thread(_ArtifactObjectStore, root)
        resolved_source_behavior = await asyncio.to_thread(
            _validate_recovery,
            database,
            graph,
            recipe,
            bridge.credential_scope,
            resume_from,
            source_behavior,
        )
        run = await asyncio.to_thread(
            database.create_run,
            recipe_id=recipe.id or graph.root_id,
            recipe_revision=recipe.revision,
            recipe_kind=cast(Literal["dataset", "workflow"], graph.root_kind),
            parameter_fingerprint=graph.parameter_fingerprint,
            graph_fingerprint=graph.graph_fingerprint,
            credential_scope=bridge.credential_scope,
            max_http_attempts=selected.max_http_attempts,
            parent_run_id=resume_from,
            source_behavior=resolved_source_behavior,
        )
        dispatcher = _AnalyticsDispatcher(config.observer)
        dispatcher.emit(
            AnalyticsEvent(
                event_type=AnalyticsEventType.run_planned,
                run_id=run.run_id,
                parent_run_id=resume_from,
            )
        )
        await asyncio.to_thread(database.transition_run, run.run_id, "running")
        dispatcher.emit(
            AnalyticsEvent(
                event_type=AnalyticsEventType.run_started,
                run_id=run.run_id,
                parent_run_id=resume_from,
            )
        )
        started = time.monotonic()
        try:
            results = await _execute_graph(
                graph=graph,
                bridge=bridge,
                database=database,
                store=store,
                run_id=run.run_id,
                parent_run_id=resume_from,
                source_behavior=resolved_source_behavior,
                policy=selected,
                dispatcher=dispatcher,
            )
            public = await _public_result(
                graph=graph,
                results=results,
                bridge=bridge,
                database=database,
                root=root,
                run_id=run.run_id,
                parent_run_id=resume_from,
            )
        except asyncio.CancelledError:
            await asyncio.to_thread(database.transition_run, run.run_id, "cancelled")
            dispatcher.emit(
                AnalyticsEvent(
                    event_type=AnalyticsEventType.run_cancelled,
                    run_id=run.run_id,
                    parent_run_id=resume_from,
                    outcome=AnalyticsOutcome.cancelled,
                    duration_seconds=time.monotonic() - started,
                )
            )
            raise
        except Exception as exc:
            node_id = await asyncio.to_thread(
                _failed_node_id,
                database,
                run.run_id,
                graph.nodes,
            )
            category = _failure_category(exc)
            await asyncio.to_thread(
                database.transition_run,
                run.run_id,
                "failed",
                node_id=node_id,
                failure_category=category,
            )
            dispatcher.emit(
                AnalyticsEvent(
                    event_type=AnalyticsEventType.run_failed,
                    run_id=run.run_id,
                    parent_run_id=resume_from,
                    node_id=node_id,
                    outcome=AnalyticsOutcome.error,
                    failure_category=category,
                    duration_seconds=time.monotonic() - started,
                )
            )
            raise CFBDRunError(
                run_id=run.run_id,
                node_id=node_id,
                category=category,
            ) from exc
        await asyncio.to_thread(database.transition_run, run.run_id, "completed")
        dispatcher.emit(
            AnalyticsEvent(
                event_type=AnalyticsEventType.run_completed,
                run_id=run.run_id,
                parent_run_id=resume_from,
                outcome=AnalyticsOutcome.success,
                duration_seconds=time.monotonic() - started,
            )
        )
        return public
    finally:
        await asyncio.to_thread(database.close)


async def _execute_graph(
    *,
    graph: _CompiledGraph,
    bridge: _RuntimeBridge,
    database: _RunDatabase,
    store: _ArtifactObjectStore,
    run_id: str,
    parent_run_id: str | None,
    source_behavior: SourceBehavior,
    policy: ExecutionPolicy,
    dispatcher: _AnalyticsDispatcher,
) -> Mapping[str, _NodeResult]:
    """Schedule deterministic ready batches across coordinator-owned sessions."""
    source_runner = _SourceRunner(
        endpoint_executor=bridge.executor,
        database=database,
        object_store=store,
        run_id=run_id,
        credential_scope=bridge.credential_scope,
        parent_run_id=parent_run_id,
        source_behavior=source_behavior,
        concurrency=policy.retrieval_concurrency,
        dispatcher=dispatcher,
    )
    local_provider = _LocalTransformProvider(concurrency=policy.compute_concurrency)
    dask_provider: _DaskTransformProvider | None = None
    if policy.executor == "dask":
        dask_provider = _DaskTransformProvider(
            max_workers=policy.dask_max_workers,
            threads_per_worker=policy.dask_threads_per_worker,
            transfer_limit_bytes=policy.dask_transfer_limit_bytes,
        )
    local_runner = _transform_runner(
        local_provider,
        database=database,
        store=store,
        run_id=run_id,
        credential_scope=bridge.credential_scope,
        parent_run_id=parent_run_id,
        source_behavior=source_behavior,
        backend=bridge.dataframe_backend,
        dispatcher=dispatcher,
    )
    dask_runner = (
        _transform_runner(
            dask_provider,
            database=database,
            store=store,
            run_id=run_id,
            credential_scope=bridge.credential_scope,
            parent_run_id=parent_run_id,
            source_behavior=source_behavior,
            backend=bridge.dataframe_backend,
            dispatcher=dispatcher,
        )
        if dask_provider is not None
        else None
    )
    results: dict[str, _NodeResult] = {}
    completed: set[str] = set()
    remaining = list(graph.nodes)
    try:
        while remaining:
            ready = tuple(
                node
                for node in remaining
                if all(dependency in completed for dependency in node.dependencies)
            )
            if not ready:
                raise CFBDRecipeCompilationError(
                    "Compiled recipe has no executable ready node"
                )
            source_nodes = tuple(node for node in ready if node.kind == "source")
            dask_nodes = tuple(
                node
                for node in ready
                if dask_runner is not None
                and node.kind == "step"
                and node.declaration.dask_eligible
            )
            local_nodes = tuple(
                node
                for node in ready
                if node.kind in {"step", "dataset"} and node not in dask_nodes
            )
            batches: list[asyncio.Task[Mapping[str, _NodeResult]]] = []
            if source_nodes:
                batches.append(
                    asyncio.create_task(source_runner.run_batch(source_nodes, results))
                )
            if local_nodes:
                batches.append(
                    asyncio.create_task(local_runner.run_batch(local_nodes, results))
                )
            if dask_nodes and dask_runner is not None:
                batches.append(
                    asyncio.create_task(dask_runner.run_batch(dask_nodes, results))
                )
            try:
                batch_results = await asyncio.gather(*batches)
            except BaseException:
                for batch_task in batches:
                    if not batch_task.done():
                        batch_task.cancel()
                await asyncio.gather(*batches, return_exceptions=True)
                raise
            for batch_result in batch_results:
                results.update(batch_result)
            for node in ready:
                if node.kind == "workflow":
                    await _commit_workflow_boundary(
                        node,
                        results=results,
                        database=database,
                        run_id=run_id,
                        backend=bridge.dataframe_backend,
                        dispatcher=dispatcher,
                    )
                completed.add(node.node_id)
                remaining.remove(node)
    except BaseException:
        await _close_providers((dask_provider, local_provider))
        raise
    failures = await _close_providers((dask_provider, local_provider))
    if failures:
        raise failures[0]
    return MappingProxyType(results)


async def _close_providers(
    providers: Sequence[_TransformExecutorSession | None],
) -> tuple[BaseException, ...]:
    """Attempt every provider close and return bounded cleanup failures."""
    failures: list[BaseException] = []
    for provider in providers:
        if provider is None:
            continue
        try:
            await provider.aclose()
        except BaseException as exc:
            failures.append(exc)
    return tuple(failures)


def _transform_runner(
    provider: _TransformExecutorSession,
    *,
    database: _RunDatabase,
    store: _ArtifactObjectStore,
    run_id: str,
    credential_scope: str,
    parent_run_id: str | None,
    source_behavior: SourceBehavior,
    backend: Literal["pandas", "polars"],
    dispatcher: _AnalyticsDispatcher,
) -> _TransformRunner:
    return _TransformRunner(
        provider=provider,
        database=database,
        object_store=store,
        run_id=run_id,
        credential_scope=credential_scope,
        parent_run_id=parent_run_id,
        source_behavior=source_behavior,
        backend=backend,
        dispatcher=dispatcher,
    )


async def _commit_workflow_boundary(
    node: _CompiledNode,
    *,
    results: Mapping[str, _NodeResult],
    database: _RunDatabase,
    run_id: str,
    backend: Literal["pandas", "polars"],
    dispatcher: _AnalyticsDispatcher,
) -> None:
    """Bind named workflow outputs to their existing immutable objects."""
    await asyncio.to_thread(database.transition_node, run_id, node.node_id, "ready")
    dispatcher.emit(
        AnalyticsEvent(
            event_type=AnalyticsEventType.step_ready,
            run_id=run_id,
            node_id=node.node_id,
            placement="coordinator",
        )
    )
    await asyncio.to_thread(database.transition_node, run_id, node.node_id, "running")
    dispatcher.emit(
        AnalyticsEvent(
            event_type=AnalyticsEventType.step_started,
            run_id=run_id,
            node_id=node.node_id,
            placement="coordinator",
        )
    )
    named: list[tuple[str, _NodeResult]] = []
    for name, argument in node.arguments.items():
        dependency = getattr(argument.value, "node_id", None)
        if not isinstance(dependency, str) or dependency not in results:
            raise CFBDRecipeCompilationError("Workflow output dependency is not ready")
        named.append((name, results[dependency]))
    upstream = tuple(
        _UpstreamArtifactIdentity(
            dependency=node.dependencies[index],
            output_name=name,
            content_digest=result.artifact.content_digest,
        )
        for index, (name, result) in enumerate(named)
    )
    outputs = tuple(
        _OutputContractIdentity(
            name=name,
            output_id=result.artifact.manifest.body.output_id,
            revision=result.artifact.manifest.body.output_revision,
            schema_digest=result.artifact.manifest.body.schema_digest,
            codec_id=result.artifact.manifest.body.codec_id,
            codec_version=result.artifact.manifest.body.codec_version,
        )
        for name, result in named
    )
    fingerprint = _node_fingerprint(
        node,
        parameters={"outputs": tuple(name for name, _ in named)},
        upstream=upstream,
        outputs=outputs,
        backend=backend,
    )
    if fingerprint is None:
        fingerprint = node.node_id
    await asyncio.to_thread(
        database.bind_completed_outputs,
        run_id=run_id,
        node_id=node.node_id,
        outputs=tuple(
            (name, fingerprint, result.artifact, "coordinator")
            for name, result in named
        ),
    )
    dispatcher.emit(
        AnalyticsEvent(
            event_type=AnalyticsEventType.step_completed,
            run_id=run_id,
            node_id=node.node_id,
            placement="coordinator",
            outcome=AnalyticsOutcome.success,
        )
    )


async def _public_result(
    *,
    graph: _CompiledGraph,
    results: Mapping[str, _NodeResult],
    bridge: _RuntimeBridge,
    database: _RunDatabase,
    root: Path,
    run_id: str,
    parent_run_id: str | None,
) -> RecipeRun[object]:
    frames: dict[str, object] = {}
    artifacts: dict[str, ArtifactRef] = {}
    for name, node_id in graph.outputs.items():
        result = results[node_id]
        row_model = result.row_model
        if row_model is None:
            raise CFBDRecipeCompilationError("Recipe output has no row contract")
        frames[name] = await asyncio.to_thread(
            bridge.dataframe_adapter.from_models,
            endpoint=graph.root_id,
            row_model=row_model,
            models=cast(Sequence[BaseModel], result.value),
        )
        artifacts[name] = ArtifactRef._from_stored(
            root=root,
            artifact=result.artifact,
            row_model=row_model,
        )
    bindings = await asyncio.to_thread(database.bindings, run_id)
    evidence: list[RunNodeEvidence] = []
    reused = 0
    for binding in bindings:
        state = await asyncio.to_thread(database.node_state, run_id, binding.node_id)
        is_reused = state == "reused"
        reused += int(is_reused)
        evidence.append(
            RunNodeEvidence(
                node_id=binding.node_id,
                output_name=binding.output_name,
                content_digest=binding.content_digest,
                placement=binding.placement,
                reused=is_reused,
            )
        )
    value: object = (
        frames["value"] if graph.root_kind == "dataset" else WorkflowOutputs(frames)
    )
    return RecipeRun(
        run_id=run_id,
        parent_run_id=parent_run_id,
        value=value,
        artifacts=MappingProxyType(artifacts),
        lineage=tuple(evidence),
        actual_http_attempts=await asyncio.to_thread(database.attempt_count, run_id),
        reused_nodes=reused,
    )


def _validate_recovery(
    database: _RunDatabase,
    graph: _CompiledGraph,
    recipe: _CompilableRecipe,
    credential_scope: str,
    resume_from: str | None,
    requested_behavior: SourceBehavior | None,
) -> SourceBehavior:
    if requested_behavior not in {
        None,
        "preserve_snapshot",
        "normal_freshness",
        "refresh",
    }:
        raise ValueError("source_behavior is invalid")
    if resume_from is None:
        if requested_behavior == "preserve_snapshot":
            raise CFBDRecipeCompilationError(
                "preserve_snapshot requires an explicit parent run"
            )
        return requested_behavior or "normal_freshness"
    parent = database.get_run(resume_from)
    expected = (
        recipe.id or graph.root_id,
        recipe.revision,
        graph.root_kind,
        graph.parameter_fingerprint,
        graph.graph_fingerprint,
        credential_scope,
    )
    actual = (
        parent.recipe_id,
        parent.recipe_revision,
        parent.recipe_kind,
        parent.parameter_fingerprint,
        parent.graph_fingerprint,
        parent.credential_scope,
    )
    if actual != expected or parent.state not in {"failed", "cancelled"}:
        raise CFBDRecipeCompilationError(
            "Parent run is not a compatible failed or cancelled execution"
        )
    return requested_behavior or "preserve_snapshot"


def _failed_node_id(
    database: _RunDatabase,
    run_id: str,
    nodes: Sequence[_CompiledNode],
) -> str:
    for node in nodes:
        if database.node_state(run_id, node.node_id) in {"failed", "cancelled"}:
            return node.node_id
    return "coordinator"


def _runtime_bridge(client: object) -> _RuntimeBridge:
    if not hasattr(client, "_analytics_bridge"):
        raise TypeError("Recipe execution requires a CFBDClient")
    return cast(_RuntimeClient, client)._analytics_bridge()


__all__: tuple[str, ...] = ()
