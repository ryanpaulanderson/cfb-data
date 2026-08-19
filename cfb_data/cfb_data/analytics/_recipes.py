"""Implement immutable callable wrappers for analytics recipes."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import (
    TYPE_CHECKING,
    Concatenate,
    ParamSpec,
    Self,
    TypeVar,
    cast,
    overload,
)

from pydantic import BaseModel

from ._declarations import RecipeKind, _RecipeDeclaration, _validate_row_type
from ._parameters import (
    _bind_graph_parameters,
    _validate_builder_signature,
    _validate_call_parameters,
    _ValidatedParameters,
)
from ._registration import _publish_candidate
from .errors import CFBDRecipeConfigurationError, CFBDRecipeUsageError
from .types import RecipeRef, SourceContext

if TYPE_CHECKING:
    from ._runtime import SourceBehavior
    from .planning import ExecutionPolicy, RecipeInspection, RecipePlan
    from .results import RecipeRun, WorkflowOutputs

P = ParamSpec("P")
R = TypeVar("R")
FrameT = TypeVar("FrameT")

_BACKENDS = frozenset({"pandas", "polars"})


class _Recipe[**P, R]:
    """Protect one immutable author function and its semantic declaration."""

    _function: Callable[P, R]
    _declaration: _RecipeDeclaration
    _signature: inspect.Signature
    _alias: str | None
    _sealed: bool
    __qualname__: str
    __module__: str

    __slots__ = (
        "__dict__",
        "_declaration",
        "_function",
        "_signature",
        "_alias",
        "_sealed",
        "__weakref__",
    )

    def __init__(
        self,
        function: Callable[P, R],
        declaration: _RecipeDeclaration,
        *,
        alias: str | None = None,
    ) -> None:
        """Initialize an immutable recipe wrapper."""
        object.__setattr__(self, "_function", function)
        object.__setattr__(self, "_declaration", declaration)
        signature = _validate_builder_signature(function, kind=declaration.kind)
        object.__setattr__(self, "_signature", signature)
        object.__setattr__(self, "_alias", alias)
        object.__setattr__(self, "__wrapped__", function)
        object.__setattr__(self, "__name__", function.__name__)
        object.__setattr__(self, "__qualname__", function.__qualname__)
        object.__setattr__(self, "__module__", function.__module__)
        object.__setattr__(self, "__doc__", function.__doc__)
        object.__setattr__(self, "__annotations__", function.__annotations__)
        public_signature = signature
        if declaration.kind in {"dataset", "workflow"}:
            client = inspect.Parameter(
                "client",
                kind=inspect.Parameter.POSITIONAL_ONLY,
                annotation="CFBDClient[FrameT]",
            )
            public_signature = signature.replace(
                parameters=(client, *signature.parameters.values())
            )
        object.__setattr__(self, "__signature__", public_signature)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("Recipe objects are immutable")
        object.__setattr__(self, name, value)

    @property
    def id(self) -> str | None:
        """Return the stable namespaced identity, when declared."""
        return self._declaration.recipe_id

    @property
    def revision(self) -> int | None:
        """Return the semantic revision, when declared."""
        return self._declaration.revision

    @property
    def kind(self) -> RecipeKind:
        """Return the recipe boundary kind."""
        return self._declaration.kind

    def as_(self, alias: str) -> Self:
        """Return an immutable invocation wrapper with a stable composition alias."""
        if not alias or not alias.replace("_", "a").replace("-", "a").isalnum():
            raise CFBDRecipeConfigurationError("Recipe aliases must be non-empty slugs")
        return type(self)(self._function, self._declaration, alias=alias)

    def _validated(
        self, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> Mapping[str, object]:
        return _validate_call_parameters(
            self._function, self._signature, args, kwargs
        ).values

    def _validated_parameters(
        self, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> _ValidatedParameters:
        return _validate_call_parameters(self._function, self._signature, args, kwargs)

    def _validated_graph_parameters(
        self, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> _ValidatedParameters:
        from ._compiler import _is_reference, _validate_reference_type

        return _bind_graph_parameters(
            self._function,
            self._signature,
            args,
            kwargs,
            is_reference=_is_reference,
            validate_reference=_validate_reference_type,
        )

    def _call_builder(self, parameters: Mapping[str, object]) -> R:
        callable_function = cast(Callable[..., R], self._function)
        return callable_function(**parameters)


class SourceRecipe[**P, R](_Recipe[P, R]):
    """Represent a coordinator-only validated source operation."""

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> RecipeRef[R]:
        """Add the source to an active recipe graph."""
        from ._graph_context import _call_in_build_context

        return _call_in_build_context(self, args, kwargs)

    def bind(self, **parameters: object) -> RecipeRef[R]:
        """Bind request parameters to literals or validated upstream scalars.

        :param parameters: Complete request bindings by parameter name.
        :return: Source reference in the active graph builder.
        :raises CFBDRecipeUsageError: If no graph is being built.
        """
        from ._graph_context import _call_in_build_context

        return _call_in_build_context(self, (), parameters)

    async def _execute_source(
        self,
        context: object,
        parameters: Mapping[str, object],
    ) -> object:
        """Execute the trusted source body with an engine-owned context."""
        callable_function = cast(Callable[..., object], self._function)
        result = callable_function(context, **parameters)
        if inspect.isawaitable(result):
            return await cast(Awaitable[object], result)
        return result


class StepRecipe[**P, R](_Recipe[P, R]):
    """Represent one pure transformation boundary."""

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> RecipeRef[R]:
        """Add the transformation to an active recipe graph."""
        from ._graph_context import _call_in_build_context

        return _call_in_build_context(self, args, kwargs)

    @property
    def _is_async(self) -> bool:
        """Return whether execution must remain on the coordinator loop."""
        return inspect.iscoroutinefunction(self._function)

    def _execute_step(self, parameters: Mapping[str, object]) -> object:
        """Invoke the trusted step body with validated resolved parameters."""
        callable_function = cast(Callable[..., object], self._function)
        return callable_function(**parameters)


class DatasetRecipe[**P, R](_Recipe[P, R]):
    """Represent one directly executable validated tabular recipe."""

    @overload
    def __call__(
        self, client: object, *args: P.args, **kwargs: P.kwargs
    ) -> Awaitable[FrameT]: ...

    @overload
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> RecipeRef[R]: ...

    def __call__(self, *args: object, **kwargs: object) -> object:
        """Build a nested reference or execute this dataset through a client."""
        from ._graph_context import _active_build_context, _call_in_build_context

        if _active_build_context() is not None:
            return _call_in_build_context(self, args, kwargs)
        if not args:
            raise CFBDRecipeUsageError("Top-level dataset calls require a CFBDClient")
        from cfb_data.client import CFBDClient

        if not isinstance(args[0], CFBDClient):
            raise CFBDRecipeUsageError("Top-level dataset calls require a CFBDClient")
        from ._runtime import _execute_direct

        return _execute_direct(self, args[0], args[1:], kwargs)

    async def plan(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        **kwargs: object,
    ) -> RecipePlan:
        """Return a pure state-independent execution plan."""
        from ._compiler import _CompilableRecipe
        from .planning import _plan_recipe

        plan, _ = _plan_recipe(
            cast(_CompilableRecipe, self), client, args, kwargs, policy
        )
        return plan

    async def inspect(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        plan: RecipePlan | None = None,
        **kwargs: object,
    ) -> RecipeInspection:
        """Inspect exact cache and checkpoint state without mutation."""
        from ._compiler import _CompilableRecipe
        from .planning import _inspect_recipe

        return await _inspect_recipe(
            cast(_CompilableRecipe, self),
            client,
            args,
            kwargs,
            policy=policy,
            plan=plan,
        )

    async def run(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
        source_behavior: SourceBehavior | None = None,
        **kwargs: object,
    ) -> RecipeRun[FrameT]:
        """Execute the dataset and return its frame and durable evidence."""
        from ._compiler import _CompilableRecipe
        from ._runtime import _execute_run

        result = await _execute_run(
            cast(_CompilableRecipe, self),
            client,
            args,
            kwargs,
            policy=policy,
            resume_from=resume_from,
            source_behavior=source_behavior,
        )
        return cast("RecipeRun[FrameT]", result)


class WorkflowRecipe[**P, R](_Recipe[P, R]):
    """Represent one directly executable named-output workflow."""

    @overload
    def __call__(
        self, client: object, *args: P.args, **kwargs: P.kwargs
    ) -> Awaitable[WorkflowOutputs[FrameT]]: ...

    @overload
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> RecipeRef[R]: ...

    def __call__(self, *args: object, **kwargs: object) -> object:
        """Build a nested reference or execute this workflow through a client."""
        from ._graph_context import _active_build_context, _call_in_build_context

        if _active_build_context() is not None:
            return _call_in_build_context(self, args, kwargs)
        if not args:
            raise CFBDRecipeUsageError("Top-level workflow calls require a CFBDClient")
        from cfb_data.client import CFBDClient

        if not isinstance(args[0], CFBDClient):
            raise CFBDRecipeUsageError("Top-level workflow calls require a CFBDClient")
        from ._runtime import _execute_direct

        return _execute_direct(self, args[0], args[1:], kwargs)

    async def plan(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        **kwargs: object,
    ) -> RecipePlan:
        """Return a pure state-independent execution plan."""
        from ._compiler import _CompilableRecipe
        from .planning import _plan_recipe

        plan, _ = _plan_recipe(
            cast(_CompilableRecipe, self), client, args, kwargs, policy
        )
        return plan

    async def inspect(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        plan: RecipePlan | None = None,
        **kwargs: object,
    ) -> RecipeInspection:
        """Inspect exact cache and checkpoint state without mutation."""
        from ._compiler import _CompilableRecipe
        from .planning import _inspect_recipe

        return await _inspect_recipe(
            cast(_CompilableRecipe, self),
            client,
            args,
            kwargs,
            policy=policy,
            plan=plan,
        )

    async def run(
        self,
        client: object,
        *args: object,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
        source_behavior: SourceBehavior | None = None,
        **kwargs: object,
    ) -> RecipeRun[WorkflowOutputs[FrameT]]:
        """Execute the workflow and return named frames and durable evidence."""
        from ._compiler import _CompilableRecipe
        from ._runtime import _execute_run

        result = await _execute_run(
            cast(_CompilableRecipe, self),
            client,
            args,
            kwargs,
            policy=policy,
            resume_from=resume_from,
            source_behavior=source_behavior,
        )
        return cast("RecipeRun[WorkflowOutputs[FrameT]]", result)


@overload
def source[**Params, Row](
    function: Callable[Concatenate[SourceContext[Row], Params], Awaitable[list[Row]]],
    *,
    operation: object | None = None,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    cost: int | None = None,
) -> SourceRecipe[Params, list[Row]]: ...


@overload
def source[**Params, Row](
    function: None = None,
    *,
    operation: object | None = None,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    cost: int | None = None,
) -> Callable[
    [Callable[Concatenate[SourceContext[Row], Params], Awaitable[list[Row]]]],
    SourceRecipe[Params, list[Row]],
]: ...


def source(
    function: object | None = None,
    *,
    operation: object | None = None,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    cost: int | None = None,
) -> object:
    """Decorate one endpoint-backed or custom coordinator source."""
    derived_id = getattr(operation, "id", None) if operation is not None else None
    derived_revision = (
        getattr(operation, "revision", None) if operation is not None else None
    )
    derived_output = (
        getattr(operation, "row_model", None) if operation is not None else None
    )
    derived_cost = getattr(operation, "cost", None) if operation is not None else None
    if operation is not None and any(
        value is not None for value in (id, revision, output, cost)
    ):
        raise CFBDRecipeConfigurationError(
            "Endpoint-backed sources derive identity, output, and cost from operation"
        )
    recipe_id = derived_id if operation is not None else id
    semantic_revision = derived_revision if operation is not None else revision
    output_type = derived_output if operation is not None else output
    source_cost = derived_cost if operation is not None else cost
    if recipe_id is None or semantic_revision is None or output_type is None:
        raise CFBDRecipeConfigurationError(
            "Custom sources require id, revision, and output"
        )
    if source_cost is None or not isinstance(source_cost, int) or source_cost < 0:
        raise CFBDRecipeConfigurationError(
            "Sources require a bounded non-negative cost"
        )
    declaration = _RecipeDeclaration(
        kind="source",
        recipe_id=_validate_identity(recipe_id),
        revision=_validate_revision(semantic_revision),
        output_type=output_type,
        deterministic=False,
        supported_backends=_BACKENDS,
        dask_eligible=False,
        operation=operation,
        source_cost=source_cost,
    )
    return _decorate(
        cast(Callable[..., object] | None, function),
        declaration,
        SourceRecipe,
    )


@overload
def step[**Params, Result](
    function: Callable[Params, Result],
    *,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    deterministic: bool = True,
    backends: frozenset[str] = _BACKENDS,
    dask: bool = True,
) -> StepRecipe[Params, Result]: ...


@overload
def step[**Params, Result](
    function: None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    deterministic: bool = True,
    backends: frozenset[str] = _BACKENDS,
    dask: bool = True,
) -> Callable[[Callable[Params, Result]], StepRecipe[Params, Result]]: ...


def step[**Params, Result](
    function: Callable[Params, Result] | None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
    output: type[object] | None = None,
    deterministic: bool = True,
    backends: frozenset[str] = _BACKENDS,
    dask: bool = True,
) -> (
    StepRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], StepRecipe[Params, Result]]
):
    """Decorate one pure validated transform boundary."""
    declaration = _RecipeDeclaration(
        kind="step",
        recipe_id=_optional_identity(id),
        revision=_optional_revision(id, revision),
        output_type=output,
        deterministic=deterministic,
        supported_backends=_validate_backends(backends),
        dask_eligible=dask and not inspect.iscoroutinefunction(function),
    )
    return _decorate(function, declaration, StepRecipe)


@overload
def dataset[**Params, Result](
    function: Callable[Params, Result],
    *,
    id: str | None = None,
    revision: int | None = None,
    row: type[BaseModel],
    grain: str,
    keys: tuple[str, ...],
    order_by: tuple[str, ...] = (),
    partition_by: tuple[str, ...] = (),
    event_time: str | None = None,
) -> DatasetRecipe[Params, Result]: ...


@overload
def dataset[**Params, Result](
    function: None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
    row: type[BaseModel],
    grain: str,
    keys: tuple[str, ...],
    order_by: tuple[str, ...] = (),
    partition_by: tuple[str, ...] = (),
    event_time: str | None = None,
) -> Callable[[Callable[Params, Result]], DatasetRecipe[Params, Result]]: ...


def dataset[**Params, Result](
    function: Callable[Params, Result] | None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
    row: type[BaseModel],
    grain: str,
    keys: tuple[str, ...],
    order_by: tuple[str, ...] = (),
    partition_by: tuple[str, ...] = (),
    event_time: str | None = None,
) -> (
    DatasetRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], DatasetRecipe[Params, Result]]
):
    """Decorate one final tabular analytical product."""
    field_names = frozenset(row.model_fields)
    _require_fields(field_names, keys, "keys")
    _require_fields(field_names, order_by, "order_by")
    _require_fields(field_names, partition_by, "partition_by")
    if event_time is not None and event_time not in field_names:
        raise CFBDRecipeConfigurationError("event_time must name a row-model field")
    if not grain.strip():
        raise CFBDRecipeConfigurationError("Datasets require a non-empty grain")
    declaration = _RecipeDeclaration(
        kind="dataset",
        recipe_id=_optional_identity(id),
        revision=_optional_revision(id, revision),
        output_type=_validate_row_type(row),
        deterministic=True,
        supported_backends=_BACKENDS,
        dask_eligible=False,
        grain=grain.strip(),
        keys=keys,
        order_by=order_by,
        partition_by=partition_by,
        event_time=event_time,
    )
    return _decorate(function, declaration, DatasetRecipe)


@overload
def workflow[**Params, Result](
    function: Callable[Params, Result],
    *,
    id: str | None = None,
    revision: int | None = None,
) -> WorkflowRecipe[Params, Result]: ...


@overload
def workflow[**Params, Result](
    function: None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
) -> Callable[[Callable[Params, Result]], WorkflowRecipe[Params, Result]]: ...


def workflow[**Params, Result](
    function: Callable[Params, Result] | None = None,
    *,
    id: str | None = None,
    revision: int | None = None,
) -> (
    WorkflowRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], WorkflowRecipe[Params, Result]]
):
    """Decorate one ordered named-output analytical composition."""
    declaration = _RecipeDeclaration(
        kind="workflow",
        recipe_id=_optional_identity(id),
        revision=_optional_revision(id, revision),
        output_type=None,
        deterministic=True,
        supported_backends=_BACKENDS,
        dask_eligible=False,
    )
    return _decorate(function, declaration, WorkflowRecipe)


@overload
def _decorate[**Params, Result](
    function: Callable[Params, Result] | None,
    declaration: _RecipeDeclaration,
    recipe_type: type[SourceRecipe[Params, Result]],
) -> (
    SourceRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], SourceRecipe[Params, Result]]
): ...


@overload
def _decorate[**Params, Result](
    function: Callable[Params, Result] | None,
    declaration: _RecipeDeclaration,
    recipe_type: type[StepRecipe[Params, Result]],
) -> (
    StepRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], StepRecipe[Params, Result]]
): ...


@overload
def _decorate[**Params, Result](
    function: Callable[Params, Result] | None,
    declaration: _RecipeDeclaration,
    recipe_type: type[DatasetRecipe[Params, Result]],
) -> (
    DatasetRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], DatasetRecipe[Params, Result]]
): ...


@overload
def _decorate[**Params, Result](
    function: Callable[Params, Result] | None,
    declaration: _RecipeDeclaration,
    recipe_type: type[WorkflowRecipe[Params, Result]],
) -> (
    WorkflowRecipe[Params, Result]
    | Callable[[Callable[Params, Result]], WorkflowRecipe[Params, Result]]
): ...


def _decorate[**Params, Result](
    function: Callable[Params, Result] | None,
    declaration: _RecipeDeclaration,
    recipe_type: type[_Recipe[Params, Result]],
) -> (
    _Recipe[Params, Result]
    | Callable[[Callable[Params, Result]], _Recipe[Params, Result]]
):
    def apply(candidate: Callable[Params, Result]) -> _Recipe[Params, Result]:
        candidate_declaration = declaration
        if declaration.kind == "step" and inspect.iscoroutinefunction(candidate):
            candidate_declaration = replace(declaration, dask_eligible=False)
        recipe = recipe_type(candidate, candidate_declaration)
        _publish_candidate(recipe)
        return recipe

    return apply(function) if function is not None else apply


def _validate_identity(value: object) -> str:
    if not isinstance(value, str) or "." not in value or not value.strip():
        raise CFBDRecipeConfigurationError("Recipe IDs must be namespaced strings")
    return value


def _optional_identity(value: str | None) -> str | None:
    return None if value is None else _validate_identity(value)


def _validate_revision(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CFBDRecipeConfigurationError("Recipe revisions must be positive integers")
    return value


def _optional_revision(identity: str | None, revision: int | None) -> int | None:
    if (identity is None) != (revision is None):
        raise CFBDRecipeConfigurationError(
            "Recipe id and revision must be declared together"
        )
    return None if revision is None else _validate_revision(revision)


def _validate_backends(backends: frozenset[str]) -> frozenset[str]:
    if not backends or not backends <= _BACKENDS:
        raise CFBDRecipeConfigurationError(
            "Step backends must select pandas and/or polars"
        )
    return backends


def _require_fields(
    available: frozenset[str], names: tuple[str, ...], label: str
) -> None:
    if len(names) != len(set(names)) or not set(names) <= available:
        raise CFBDRecipeConfigurationError(
            f"Dataset {label} must contain unique row-model fields"
        )
