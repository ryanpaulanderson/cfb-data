"""Compile pure recipe builders into deterministic immutable graphs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from types import MappingProxyType, UnionType
from typing import Protocol, cast, get_args, get_origin

from pydantic import BaseModel

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.errors import CFBDRequestValidationError

from ._declarations import RecipeKind, _RecipeDeclaration
from ._graph import (
    _CompiledGraph,
    _CompiledNode,
    _node_dependencies,
    _NodeArgument,
    _NodeRef,
    _require_node_ref,
    _ValueRef,
    _WorkflowRef,
)
from ._parameters import _ValidatedParameters
from .errors import CFBDRecipeCompilationError

_ACTIVE_BUILDER: ContextVar[_GraphBuilder | None] = ContextVar(
    "cfb_data_analytics_builder", default=None
)


class _CompilableRecipe(Protocol):
    """Describe private recipe behavior required by graph compilation."""

    _alias: str | None
    _declaration: _RecipeDeclaration
    __module__: str
    __qualname__: str

    @property
    def id(self) -> str | None: ...

    @property
    def revision(self) -> int | None: ...

    @property
    def kind(self) -> RecipeKind: ...

    def _validated_parameters(
        self, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> _ValidatedParameters: ...

    def _validated_graph_parameters(
        self, args: tuple[object, ...], kwargs: Mapping[str, object]
    ) -> _ValidatedParameters: ...

    def _call_builder(self, parameters: Mapping[str, object]) -> object: ...


@dataclass(slots=True)
class _NamespaceState:
    """Track one builder namespace and its child invocation identities."""

    path: str
    invocations: dict[str, tuple[str, object]]


class _GraphBuilder:
    """Build one finite graph from trusted pure recipe functions."""

    def __init__(self, *, max_nodes: int) -> None:
        """Initialize bounded graph compilation state."""
        self._max_nodes = max_nodes
        self._nodes: list[_CompiledNode] = []
        self._namespace_stack: list[_NamespaceState] = []
        self._recipe_stack: list[object] = []

    def compile(
        self,
        recipe: _CompilableRecipe,
        args: tuple[object, ...],
        kwargs: Mapping[str, object],
    ) -> _CompiledGraph:
        """Compile a top-level dataset or workflow without operational I/O."""
        kind = recipe.kind
        if kind not in {"dataset", "workflow"}:
            raise CFBDRecipeCompilationError(
                "Only datasets and workflows are top-level analytical products"
            )
        validated = recipe._validated_parameters(args, kwargs)
        stable_id = recipe.id or _notebook_identity(recipe)
        root_path = f"{kind}:{stable_id}@{recipe.revision or 0}"
        token = _ACTIVE_BUILDER.set(self)
        try:
            result = self._build_boundary(recipe, validated, root_path)
        finally:
            _ACTIVE_BUILDER.reset(token)
        outputs = _root_outputs(kind, result)
        parameter_fingerprint = _digest(
            {"provided": sorted(validated.provided), "values": validated.values}
        )
        graph_fingerprint = _digest(
            {
                "ir": 1,
                "root": root_path,
                "nodes": [_node_identity(node) for node in self._nodes],
                "outputs": outputs,
            }
        )
        return _CompiledGraph(
            root_id=root_path,
            root_kind=kind,
            nodes=tuple(self._nodes),
            outputs=MappingProxyType(outputs),
            parameter_fingerprint=parameter_fingerprint,
            graph_fingerprint=graph_fingerprint,
        )

    def call(
        self,
        recipe: _CompilableRecipe,
        args: tuple[object, ...],
        kwargs: Mapping[str, object],
    ) -> _NodeRef | _WorkflowRef:
        """Add one nested boundary from an ordinary recipe call."""
        if not self._namespace_stack:
            raise CFBDRecipeCompilationError("Recipe call has no parent namespace")
        validated = recipe._validated_graph_parameters(args, kwargs)
        parent = self._namespace_stack[-1]
        identity = recipe.id or _notebook_identity(recipe)
        alias = recipe._alias
        invocation_name = alias or f"{recipe.kind}:{identity}@{recipe.revision or 0}"
        call_fingerprint = _digest(
            {"provided": sorted(validated.provided), "values": validated.values}
        )
        previous = parent.invocations.get(invocation_name)
        if previous is not None:
            previous_fingerprint, previous_result = previous
            if previous_fingerprint == call_fingerprint:
                return cast(_NodeRef | _WorkflowRef, previous_result)
            if alias is None:
                raise CFBDRecipeCompilationError(
                    "Repeated recipe calls with different parameters require as_(alias)"
                )
            raise CFBDRecipeCompilationError(
                f"Duplicate recipe alias {alias!r} in one parent boundary"
            )
        child_path = f"{parent.path}/{invocation_name}"
        result = self._build_boundary(recipe, validated, child_path)
        parent.invocations[invocation_name] = (call_fingerprint, result)
        return result

    def _build_boundary(
        self,
        recipe: _CompilableRecipe,
        validated: _ValidatedParameters,
        path: str,
    ) -> _NodeRef | _WorkflowRef:
        if recipe in self._recipe_stack:
            raise CFBDRecipeCompilationError(
                "Recursive recipe composition is forbidden"
            )
        self._recipe_stack.append(recipe)
        self._namespace_stack.append(_NamespaceState(path=path, invocations={}))
        try:
            kind = recipe.kind
            if kind in {"source", "step"}:
                arguments = _encode_arguments(validated.values)
                if kind == "source":
                    _validate_literal_source_request(recipe, arguments)
                node = _CompiledNode(
                    node_id=path,
                    kind=kind,
                    declaration=recipe._declaration,
                    recipe=recipe,
                    arguments=arguments,
                    provided=validated.provided,
                    dependencies=_node_dependencies(arguments),
                )
                self._append(node)
                return _NodeRef(path)
            built = recipe._call_builder(validated.values)
            if kind == "dataset":
                upstream = _require_node_ref(built, boundary="Dataset")
                node = _CompiledNode(
                    node_id=path,
                    kind="dataset",
                    declaration=recipe._declaration,
                    recipe=recipe,
                    arguments=MappingProxyType(
                        {"value": _NodeArgument("node", upstream)}
                    ),
                    provided=validated.provided,
                    dependencies=(upstream.node_id,),
                )
                self._append(node)
                return _NodeRef(path)
            outputs = _validate_workflow_outputs(built)
            node = _CompiledNode(
                node_id=path,
                kind="workflow",
                declaration=recipe._declaration,
                recipe=recipe,
                arguments=MappingProxyType(
                    {
                        name: _NodeArgument("node", output)
                        for name, output in outputs.items()
                    }
                ),
                provided=validated.provided,
                dependencies=tuple(output.node_id for output in outputs.values()),
                output_names=tuple(outputs),
            )
            self._append(node)
            return _WorkflowRef(outputs)
        finally:
            self._namespace_stack.pop()
            self._recipe_stack.pop()

    def _append(self, node: _CompiledNode) -> None:
        if any(existing.node_id == node.node_id for existing in self._nodes):
            raise CFBDRecipeCompilationError(f"Duplicate compiled node {node.node_id}")
        if len(self._nodes) >= self._max_nodes:
            raise CFBDRecipeCompilationError(
                f"Recipe graph exceeds the {self._max_nodes}-node limit"
            )
        self._nodes.append(node)


def _validate_literal_source_request(
    recipe: _CompilableRecipe,
    arguments: Mapping[str, _NodeArgument],
) -> None:
    """Validate descriptor-owned literal requests during pure compilation."""
    if any(argument.kind != "literal" for argument in arguments.values()):
        return
    operation = recipe._declaration.operation
    if not isinstance(operation, _ManyEndpointOperation):
        return
    try:
        operation.resolve(
            None,
            {name: argument.value for name, argument in arguments.items()},
        )
    except (CFBDRequestValidationError, TypeError) as exc:
        raise CFBDRecipeCompilationError(
            "Source request parameters violate the endpoint contract"
        ) from exc


def _compile_recipe(
    recipe: _CompilableRecipe,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    *,
    max_nodes: int = 10_000,
) -> _CompiledGraph:
    """Compile one top-level recipe into a state-independent graph."""
    return _GraphBuilder(max_nodes=max_nodes).compile(recipe, args, kwargs)


def _current_builder() -> _GraphBuilder | None:
    """Return the task-local graph builder."""
    return _ACTIVE_BUILDER.get()


def _encode_arguments(values: Mapping[str, object]) -> Mapping[str, _NodeArgument]:
    encoded: dict[str, _NodeArgument] = {}
    for name, value in values.items():
        if isinstance(value, _NodeRef):
            encoded[name] = _NodeArgument("node", value)
        elif isinstance(value, _ValueRef):
            encoded[name] = _NodeArgument("value", value)
        else:
            encoded[name] = _NodeArgument("literal", value)
    return MappingProxyType(encoded)


def _is_reference(value: object) -> bool:
    """Return whether a graph argument contains an engine-owned reference."""
    if isinstance(value, (_NodeRef, _ValueRef)):
        return True
    if isinstance(value, Mapping):
        return any(_is_reference(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_is_reference(item) for item in value)
    return False


def _validate_reference_type(value: object, annotation: object) -> None:
    """Validate scalar reference compatibility without evaluating its value."""
    if not isinstance(value, _ValueRef):
        return
    accepted = (
        get_args(annotation) if get_origin(annotation) is UnionType else (annotation,)
    )
    if value.expected_type not in accepted:
        raise CFBDRecipeCompilationError(
            "Bound scalar type is incompatible with the source parameter"
        )


def _validate_workflow_outputs(value: object) -> dict[str, _NodeRef]:
    if not isinstance(value, Mapping) or not value:
        raise CFBDRecipeCompilationError(
            "Workflow builders must return a non-empty mapping of named references"
        )
    outputs: dict[str, _NodeRef] = {}
    for name, output in value.items():
        if not isinstance(name, str) or not name or name in outputs:
            raise CFBDRecipeCompilationError(
                "Workflow output names must be unique non-empty strings"
            )
        outputs[name] = _require_node_ref(output, boundary="Workflow")
    return outputs


def _root_outputs(kind: str, result: _NodeRef | _WorkflowRef) -> dict[str, str]:
    if kind == "dataset":
        if not isinstance(result, _NodeRef):
            raise AssertionError("Dataset compilation returned a workflow reference")
        return {"value": result.node_id}
    if not isinstance(result, _WorkflowRef):
        raise AssertionError("Workflow compilation returned a node reference")
    return {name: output.node_id for name, output in result.items()}


def _notebook_identity(recipe: _CompilableRecipe) -> str:
    return f"{recipe.__module__}.{recipe.__qualname__}"


def _node_identity(node: _CompiledNode) -> object:
    return {
        "id": node.node_id,
        "kind": node.kind,
        "recipe": node.declaration.recipe_id,
        "revision": node.declaration.revision,
        "provided": sorted(node.provided),
        "arguments": {
            name: {"kind": argument.kind, "value": argument.value}
            for name, argument in node.arguments.items()
        },
        "dependencies": node.dependencies,
        "outputs": node.output_names,
    }


def _digest(value: object) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return {"$float": value.hex()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, (date, datetime, time)):
        return {"$temporal": value.isoformat()}
    if isinstance(value, Enum):
        return {"$enum": _canonical(value.value)}
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="json"))
    if isinstance(value, _NodeRef):
        return {"$node": value.node_id}
    if isinstance(value, _ValueRef):
        return {
            "$value": value.node_id,
            "path": list(value.path),
            "type": f"{value.expected_type.__module__}:{value.expected_type.__qualname__}",
        }
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise CFBDRecipeCompilationError(
        f"Unsupported canonical recipe value type {type(value).__name__}"
    )
