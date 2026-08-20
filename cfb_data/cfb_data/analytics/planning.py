"""Plan recipe execution purely and inspect existing state without mutation."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Literal, Protocol, cast

from cfb_data._operation import _EndpointOperation
from cfb_data.cache._coordinator import CacheCoordinator
from cfb_data.cache._key import response_cache_key
from cfb_data.cache._models import ResponsePeek, ResponsePeekStatus
from cfb_data.client import DataFrameBackend

from ._checkpoints import _node_fingerprint
from ._compiler import _CompilableRecipe, _compile_recipe, _digest
from ._contracts import _table_row_model
from ._execution import _resolve_arguments
from ._graph import _CompiledGraph, _CompiledNode, _ValueRef
from ._persistence import _analytics_root, _ArtifactObjectStore, _RunDatabaseReader
from ._transforms import _output_contract, _output_identity, _semantic_parameters
from .config import AnalyticsConfig
from .errors import CFBDArtifactCorruptionError, CFBDRecipeCompilationError

type ExecutorName = Literal["local", "dask"]
type NodePlacement = Literal["coordinator", "dask"]
type CheckpointMode = Literal["all", "outputs_only", "off"]
type CheckpointDisposition = Literal[
    "disabled",
    "missing",
    "reusable",
    "corrupt",
    "deferred",
    "unavailable",
]
type SourceDisposition = Literal[
    "disabled",
    "missing",
    "fresh",
    "stale",
    "expired",
    "corrupt",
    "deferred",
    "unavailable",
]


class _PlanningBridge(Protocol):
    """Describe in-memory client values required by planning and inspection."""

    dataframe_backend: DataFrameBackend
    retry_max_attempts: int
    base_url: str
    credential_scope: str
    cache_enabled: bool
    cache_coordinator: CacheCoordinator
    config: object | None


class _PlanningClient(Protocol):
    """Expose the private bridge supplied by the primary client."""

    def _analytics_bridge(self) -> _PlanningBridge: ...


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Control bounded operational execution without changing portable content."""

    executor: ExecutorName = "local"
    retrieval_concurrency: int = 4
    compute_concurrency: int = 1
    max_http_attempts: int = 100
    max_expanded_nodes: int = 10_000
    checkpoint_mode: CheckpointMode = "all"
    recompute_nodes: tuple[str, ...] = ()
    dask_max_workers: int = 4
    dask_threads_per_worker: int = 1
    dask_transfer_limit_bytes: int = 512 * 1024 * 1024
    dask_max_attempts: int = 1
    dask_step_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject unbounded or internally inconsistent execution controls."""
        if self.executor not in {"local", "dask"}:
            raise ValueError("executor must be 'local' or 'dask'")
        if self.checkpoint_mode not in {"all", "outputs_only", "off"}:
            raise ValueError("checkpoint_mode is invalid")
        if (
            not isinstance(self.recompute_nodes, tuple)
            or any(
                not isinstance(node_id, str) or not node_id
                for node_id in self.recompute_nodes
            )
            or len(set(self.recompute_nodes)) != len(self.recompute_nodes)
        ):
            raise ValueError("recompute_nodes must contain unique non-empty node IDs")
        positive = (
            self.retrieval_concurrency,
            self.compute_concurrency,
            self.max_http_attempts,
            self.max_expanded_nodes,
            self.dask_max_workers,
            self.dask_threads_per_worker,
            self.dask_transfer_limit_bytes,
            self.dask_max_attempts,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in positive
        ):
            raise ValueError("Execution policy limits must be positive integers")
        timeout = self.dask_step_timeout_seconds
        if timeout is not None and (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Dask step timeout must be a positive finite number")


@dataclass(frozen=True, slots=True)
class RecipePlanNode:
    """Describe one redacted compiled node and its deterministic placement."""

    node_id: str
    kind: Literal["source", "step", "dataset", "workflow"]
    dependencies: tuple[str, ...]
    placement: NodePlacement
    parameter_names: tuple[str, ...]
    deferred_parameters: tuple[str, ...]
    recompute: bool


@dataclass(frozen=True, slots=True)
class RecipePlan:
    """Expose a deterministic state-independent execution plan."""

    recipe_id: str
    revision: int | None
    kind: Literal["dataset", "workflow"]
    graph_fingerprint: str
    fingerprint: str
    parameter_fingerprint: str
    nodes: tuple[RecipePlanNode, ...]
    outputs: tuple[str, ...]
    worst_case_http_attempts: int
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecipeInspection:
    """Report read-only response and checkpoint disposition for one plan."""

    plan: RecipePlan
    source_dispositions: Mapping[str, SourceDisposition]
    checkpoint_dispositions: Mapping[str, CheckpointDisposition]


def _plan_recipe(
    recipe: _CompilableRecipe,
    client: object,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    policy: ExecutionPolicy | None,
) -> tuple[RecipePlan, _CompiledGraph]:
    selected = policy or ExecutionPolicy()
    bridge = _client_bridge(client)
    graph = _compile_recipe(recipe, args, kwargs, max_nodes=selected.max_expanded_nodes)
    recompute_nodes = _expanded_recompute_nodes(graph, selected.recompute_nodes)
    nodes: list[RecipePlanNode] = []
    logical_source_cost = 0
    planned_source_requests: set[str] = set()
    for node in graph.nodes:
        if bridge.dataframe_backend not in node.declaration.supported_backends:
            raise CFBDRecipeCompilationError(
                f"Node {node.node_id} does not support the selected DataFrame backend"
            )
        placement: NodePlacement = "coordinator"
        if (
            selected.executor == "dask"
            and node.kind == "step"
            and node.declaration.dask_eligible
            and _table_row_model(node, required=False) is not None
        ):
            placement = "dask"
        if node.kind == "source":
            request_key = _source_request_key(node)
            if request_key not in planned_source_requests:
                planned_source_requests.add(request_key)
                logical_source_cost += node.declaration.source_cost or 0
        deferred = tuple(
            name
            for name, argument in node.arguments.items()
            if isinstance(argument.value, _ValueRef)
        )
        nodes.append(
            RecipePlanNode(
                node_id=node.node_id,
                kind=node.kind,
                dependencies=node.dependencies,
                placement=placement,
                parameter_names=tuple(node.arguments),
                deferred_parameters=deferred,
                recompute=node.node_id in recompute_nodes,
            )
        )
    worst_case_attempts = logical_source_cost * bridge.retry_max_attempts
    if worst_case_attempts > selected.max_http_attempts:
        raise CFBDRecipeCompilationError(
            "Recipe worst-case HTTP attempts exceed execution policy"
        )
    plan_fingerprint = _digest(
        {
            "graph": graph.graph_fingerprint,
            "backend": bridge.dataframe_backend,
            "executor": selected.executor,
            "placements": [node.placement for node in nodes],
            "attempts": worst_case_attempts,
            "max_nodes": selected.max_expanded_nodes,
            "checkpoint_mode": selected.checkpoint_mode,
            "recompute_nodes": sorted(recompute_nodes),
        }
    )
    plan = RecipePlan(
        recipe_id=recipe.id or graph.root_id,
        revision=recipe.revision,
        kind=cast(Literal["dataset", "workflow"], graph.root_kind),
        graph_fingerprint=graph.graph_fingerprint,
        fingerprint=plan_fingerprint,
        parameter_fingerprint=graph.parameter_fingerprint,
        nodes=tuple(nodes),
        outputs=tuple(graph.outputs),
        worst_case_http_attempts=worst_case_attempts,
        diagnostics=(),
    )
    return plan, graph


def _expanded_recompute_nodes(
    graph: _CompiledGraph,
    requested: tuple[str, ...],
) -> frozenset[str]:
    """Expand explicitly forced nodes through their dependency descendants."""
    known = frozenset(node.node_id for node in graph.nodes)
    unknown = tuple(node_id for node_id in requested if node_id not in known)
    if unknown:
        raise CFBDRecipeCompilationError(
            "Execution policy references an unknown recompute node"
        )
    expanded = set(requested)
    for node in graph.nodes:
        if any(dependency in expanded for dependency in node.dependencies):
            expanded.add(node.node_id)
    return frozenset(expanded)


def _checkpoint_nodes(
    graph: _CompiledGraph,
    mode: CheckpointMode,
) -> frozenset[str]:
    """Select bindings eligible for later reuse without dropping lineage."""
    if mode == "all":
        return frozenset(node.node_id for node in graph.nodes)
    if mode == "off":
        return frozenset()
    if not any(node.node_id == graph.root_id for node in graph.nodes):
        raise CFBDRecipeCompilationError("Compiled recipe has no root boundary")
    return frozenset((*graph.outputs.values(), graph.root_id))


def _source_request_key(node: _CompiledNode) -> str:
    """Return a static identity for one exact or identically deferred request."""
    operation = node.declaration.operation
    if not isinstance(operation, _EndpointOperation):
        return _digest({"source_node": node.node_id})
    if all(argument.kind == "literal" for argument in node.arguments.values()):
        filters = {name: argument.value for name, argument in node.arguments.items()}
        request = operation.resolve(None, filters)
        request_identity: object = operation.serialized_parameters(request)
    else:
        request_identity = {
            "arguments": {
                name: argument.value for name, argument in node.arguments.items()
            },
            "provided": sorted(node.provided),
        }
    return _digest(
        {
            "operation": operation.id,
            "revision": operation.revision,
            "contract": operation.response_contract,
            "request": request_identity,
        }
    )


async def _inspect_recipe(
    recipe: _CompilableRecipe,
    client: object,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    *,
    policy: ExecutionPolicy | None,
    plan: RecipePlan | None,
) -> RecipeInspection:
    compiled_plan, graph = _plan_recipe(recipe, client, args, kwargs, policy)
    if plan is not None and plan.fingerprint != compiled_plan.fingerprint:
        raise CFBDRecipeCompilationError(
            "Supplied plan does not match the validated recipe parameters and policy"
        )
    bridge = _client_bridge(client)
    dispositions: dict[str, SourceDisposition] = {}
    for node in graph.nodes:
        if node.kind != "source":
            continue
        if any(argument.kind == "value" for argument in node.arguments.values()):
            dispositions[node.node_id] = "deferred"
            continue
        operation = node.declaration.operation
        if not isinstance(operation, _EndpointOperation):
            dispositions[node.node_id] = "unavailable"
            continue
        if not bridge.cache_enabled:
            dispositions[node.node_id] = "disabled"
            continue
        filters = {
            name: argument.value
            for name, argument in node.arguments.items()
            if argument.kind == "literal"
        }
        request = operation.resolve(None, filters)
        key = response_cache_key(
            base_url=bridge.base_url,
            endpoint=operation.endpoint,
            parameters=operation.serialized_parameters(request),
            response_contract=operation.response_contract,
            credential_scope=bridge.credential_scope,
        )
        peek = await bridge.cache_coordinator.peek_response(key)
        dispositions[node.node_id] = _peek_disposition(peek, datetime.now(UTC))
    selected = policy or ExecutionPolicy()
    checkpoint_nodes = _checkpoint_nodes(graph, selected.checkpoint_mode)
    recompute_nodes = _expanded_recompute_nodes(graph, selected.recompute_nodes)
    config = (
        bridge.config
        if isinstance(bridge.config, AnalyticsConfig)
        else AnalyticsConfig()
    )
    database_path = _analytics_root(config) / "runs.sqlite3"
    reader = (
        await asyncio.to_thread(_RunDatabaseReader, database_path)
        if await asyncio.to_thread(database_path.is_file)
        else None
    )
    store = (
        None
        if reader is None
        else _ArtifactObjectStore(_analytics_root(config), create=False)
    )
    try:
        checkpoint_values = {
            node.node_id: await _checkpoint_disposition(
                node,
                reader=reader,
                store=store,
                credential_scope=bridge.credential_scope,
                backend=bridge.dataframe_backend,
                enabled=(
                    node.node_id in checkpoint_nodes
                    and node.node_id not in recompute_nodes
                ),
            )
            for node in graph.nodes
        }
    finally:
        if reader is not None:
            await asyncio.to_thread(reader.close)
    checkpoints = MappingProxyType(checkpoint_values)
    return RecipeInspection(
        plan=compiled_plan,
        source_dispositions=MappingProxyType(dispositions),
        checkpoint_dispositions=checkpoints,
    )


async def _checkpoint_disposition(
    node: _CompiledNode,
    *,
    reader: _RunDatabaseReader | None,
    store: _ArtifactObjectStore | None,
    credential_scope: str,
    backend: DataFrameBackend,
    enabled: bool,
) -> CheckpointDisposition:
    """Inspect one globally reusable checkpoint without resolving source data."""
    if not enabled or node.kind == "source":
        return "disabled"
    if reader is None or store is None:
        return "missing"
    row_model = _table_row_model(node, required=False)
    if node.kind == "workflow" or node.dependencies or row_model is None:
        return "deferred"
    parameters = _resolve_arguments(node.arguments, {}, allow_node_values=True)
    identity = _output_identity(node)
    output = _output_contract(
        identity,
        row_model=row_model,
        control_adapter=None,
    )
    fingerprint = _node_fingerprint(
        node,
        parameters=_semantic_parameters(node, parameters),
        upstream=(),
        outputs=(output,),
        backend=backend,
    )
    if fingerprint is None:
        return "unavailable"
    try:
        candidate = await asyncio.to_thread(
            reader.find_checkpoint,
            node_fingerprint=fingerprint,
            output_name="value",
            scope="global",
            parent_run_id=None,
            credential_scope=credential_scope,
        )
        if candidate is None:
            return "missing"
        manifest = await asyncio.to_thread(
            store.load_manifest,
            candidate.binding.content_digest,
        )
        if manifest != candidate.manifest:
            return "corrupt"
    except CFBDArtifactCorruptionError:
        return "corrupt"
    return "reusable"


def _peek_disposition(peek: ResponsePeek, now: datetime) -> SourceDisposition:
    status = peek.status
    if status is ResponsePeekStatus.missing:
        return "missing"
    if status is ResponsePeekStatus.expired:
        return "expired"
    if status is ResponsePeekStatus.corrupt:
        return "corrupt"
    record = peek.record
    if record is None:
        raise AssertionError("Retained cache peek must include its record")
    return "fresh" if record.fresh_until > now else "stale"


def _client_bridge(client: object) -> _PlanningBridge:
    if not hasattr(client, "_analytics_bridge"):
        raise TypeError("Recipe planning requires a CFBDClient")
    return cast(_PlanningClient, client)._analytics_bridge()


__all__ = [
    "ExecutionPolicy",
    "RecipeInspection",
    "RecipePlan",
    "RecipePlanNode",
]
