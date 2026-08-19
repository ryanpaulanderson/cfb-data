"""Plan recipe execution purely and inspect existing state without mutation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Literal, Protocol, cast

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.cache._coordinator import CacheCoordinator
from cfb_data.cache._key import response_cache_key
from cfb_data.cache._models import ResponsePeek, ResponsePeekStatus
from cfb_data.client import DataFrameBackend

from ._compiler import _CompilableRecipe, _compile_recipe, _digest
from ._graph import _CompiledGraph, _ValueRef
from .errors import CFBDRecipeCompilationError

type ExecutorName = Literal["local", "dask"]
type NodePlacement = Literal["coordinator", "dask"]
type CheckpointMode = Literal["all", "outputs_only", "off"]
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
    dask_max_workers: int = 4
    dask_threads_per_worker: int = 1
    dask_transfer_limit_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        """Reject unbounded or internally inconsistent execution controls."""
        if self.executor not in {"local", "dask"}:
            raise ValueError("executor must be 'local' or 'dask'")
        if self.checkpoint_mode not in {"all", "outputs_only", "off"}:
            raise ValueError("checkpoint_mode is invalid")
        positive = (
            self.retrieval_concurrency,
            self.compute_concurrency,
            self.max_http_attempts,
            self.max_expanded_nodes,
            self.dask_max_workers,
            self.dask_threads_per_worker,
            self.dask_transfer_limit_bytes,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in positive
        ):
            raise ValueError("Execution policy limits must be positive integers")


@dataclass(frozen=True, slots=True)
class RecipePlanNode:
    """Describe one redacted compiled node and its deterministic placement."""

    node_id: str
    kind: Literal["source", "step", "dataset", "workflow"]
    dependencies: tuple[str, ...]
    placement: NodePlacement
    parameter_names: tuple[str, ...]
    deferred_parameters: tuple[str, ...]


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
    checkpoint_dispositions: Mapping[str, Literal["unavailable"]]


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
    nodes: list[RecipePlanNode] = []
    logical_source_cost = 0
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
        ):
            placement = "dask"
        if node.kind == "source":
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
        if not isinstance(operation, _ManyEndpointOperation):
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
    checkpoint_values: dict[str, Literal["unavailable"]] = {
        node.node_id: "unavailable" for node in graph.nodes
    }
    checkpoints = MappingProxyType(checkpoint_values)
    return RecipeInspection(
        plan=compiled_plan,
        source_dispositions=MappingProxyType(dispositions),
        checkpoint_dispositions=checkpoints,
    )


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
