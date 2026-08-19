"""Represent compiled recipe graphs independently from execution policy."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from ._declarations import RecipeKind, _RecipeDeclaration
from .errors import CFBDRecipeCompilationError, CFBDRecipeUsageError

type _ArgumentKind = Literal["literal", "node", "value", "structure"]


@dataclass(frozen=True, slots=True)
class _NodeArgument:
    """Bind one validated literal or upstream reference to a node call."""

    kind: _ArgumentKind
    value: object


@dataclass(frozen=True, slots=True)
class _CompiledNode:
    """Describe one immutable executable or validation boundary."""

    node_id: str
    kind: RecipeKind
    declaration: _RecipeDeclaration
    recipe: object
    arguments: Mapping[str, _NodeArgument]
    provided: frozenset[str]
    dependencies: tuple[str, ...]
    output_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _CompiledGraph:
    """Hold one deterministic topologically ordered recipe graph."""

    root_id: str
    root_kind: RecipeKind
    nodes: tuple[_CompiledNode, ...]
    outputs: Mapping[str, str]
    parameter_fingerprint: str
    graph_fingerprint: str


@dataclass(frozen=True, slots=True)
class _NodeRef:
    """Reference one node output while a recipe graph is being built."""

    node_id: str


class _WorkflowRef(Mapping[str, _NodeRef]):
    """Reference explicitly named workflow outputs without flattening them."""

    __slots__ = ("_outputs",)

    def __init__(self, outputs: Mapping[str, _NodeRef]) -> None:
        """Freeze the named workflow output references."""
        self._outputs = MappingProxyType(dict(outputs))

    def __getitem__(self, name: str) -> _NodeRef:
        try:
            return self._outputs[name]
        except KeyError as exc:
            raise CFBDRecipeUsageError(
                f"Workflow has no declared output named {name!r}"
            ) from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._outputs)

    def __len__(self) -> int:
        return len(self._outputs)


@dataclass(frozen=True, slots=True)
class _ValueRef:
    """Reference one validated scalar path in an upstream node output."""

    node_id: str
    path: tuple[str | int, ...]
    expected_type: type[object]


def _node_dependencies(arguments: Mapping[str, _NodeArgument]) -> tuple[str, ...]:
    """Return unique dependencies in argument declaration order."""
    dependencies: list[str] = []
    for argument in arguments.values():
        node_ids: tuple[str, ...]
        if argument.kind == "node":
            if not isinstance(argument.value, _NodeRef):
                raise AssertionError("Node arguments must contain node references")
            node_ids = (argument.value.node_id,)
        elif argument.kind == "value":
            if not isinstance(argument.value, _ValueRef):
                raise AssertionError("Value arguments must contain value references")
            node_ids = (argument.value.node_id,)
        elif argument.kind == "structure":
            node_ids = tuple(_structured_dependencies(argument.value))
        else:
            node_ids = ()
        for node_id in node_ids:
            if node_id not in dependencies:
                dependencies.append(node_id)
    return tuple(dependencies)


def _structured_dependencies(value: object) -> Iterator[str]:
    """Yield references embedded in one finite structured argument."""
    if isinstance(value, _NodeRef | _ValueRef):
        yield value.node_id
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _structured_dependencies(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _structured_dependencies(item)


def _require_node_ref(value: object, *, boundary: str) -> _NodeRef:
    """Narrow one builder result to a graph reference."""
    if not isinstance(value, _NodeRef):
        raise CFBDRecipeCompilationError(
            f"{boundary} builders must return one recipe reference"
        )
    return value
