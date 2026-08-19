"""Share validated node values across source and transform executors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel

from ._graph import _NodeArgument, _NodeRef, _ValueRef
from ._persistence import _StoredArtifact
from .errors import CFBDRecipeCompilationError


@dataclass(frozen=True, slots=True)
class _NodeResult:
    """Carry one validated value and its immutable artifact identity."""

    value: object
    artifact: _StoredArtifact
    node_fingerprint: str | None
    row_model: type[BaseModel] | None


def _resolve_arguments(
    arguments: Mapping[str, _NodeArgument],
    results: Mapping[str, _NodeResult],
    *,
    allow_node_values: bool,
) -> dict[str, object]:
    """Resolve literals, upstream values, and exact typed scalar references."""
    parameters: dict[str, object] = {}
    for name, argument in arguments.items():
        if argument.kind == "literal":
            parameters[name] = argument.value
            continue
        if argument.kind == "node":
            if not allow_node_values:
                raise CFBDRecipeCompilationError(
                    "Source parameters cannot consume an entire upstream output"
                )
            node_id = getattr(argument.value, "node_id", None)
            if not isinstance(node_id, str) or node_id not in results:
                raise CFBDRecipeCompilationError(
                    "Upstream node parameter dependency is not ready"
                )
            parameters[name] = results[node_id].value
            continue
        if argument.kind == "structure":
            parameters[name] = _resolve_structure(
                argument.value,
                results,
                allow_node_values=allow_node_values,
            )
            continue
        reference = cast(_ValueRef, argument.value)
        upstream = results.get(reference.node_id)
        if upstream is None:
            raise CFBDRecipeCompilationError(
                "Late-bound parameter dependency is not ready"
            )
        parameters[name] = _extract_scalar(upstream.value, reference)
    return parameters


def _resolve_structure(
    value: object,
    results: Mapping[str, _NodeResult],
    *,
    allow_node_values: bool,
) -> object:
    """Resolve references within a finite list, tuple, or mapping."""
    if isinstance(value, _NodeRef):
        if not allow_node_values:
            raise CFBDRecipeCompilationError(
                "Source parameters cannot consume an entire upstream output"
            )
        upstream = results.get(value.node_id)
        if upstream is None:
            raise CFBDRecipeCompilationError(
                "Structured upstream dependency is not ready"
            )
        return upstream.value
    if isinstance(value, _ValueRef):
        upstream = results.get(value.node_id)
        if upstream is None:
            raise CFBDRecipeCompilationError(
                "Structured scalar dependency is not ready"
            )
        return _extract_scalar(upstream.value, value)
    if isinstance(value, Mapping):
        return {
            key: _resolve_structure(item, results, allow_node_values=allow_node_values)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_structure(item, results, allow_node_values=allow_node_values)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _resolve_structure(item, results, allow_node_values=allow_node_values)
            for item in value
        )
    return value


def _extract_scalar(value: object, reference: _ValueRef) -> object:
    """Traverse a structured validated value and require its exact scalar type."""
    current = value
    for token in reference.path:
        if isinstance(token, int):
            if not isinstance(current, Sequence) or isinstance(current, str | bytes):
                raise CFBDRecipeCompilationError("Scalar path expected a sequence")
            try:
                current = current[token]
            except IndexError as exc:
                raise CFBDRecipeCompilationError(
                    "Scalar path index is unavailable"
                ) from exc
        elif isinstance(current, BaseModel):
            if token not in current.__class__.model_fields:
                raise CFBDRecipeCompilationError("Scalar path field is unavailable")
            current = getattr(current, token)
        elif isinstance(current, Mapping):
            if token not in current:
                raise CFBDRecipeCompilationError("Scalar path key is unavailable")
            current = current[token]
        else:
            raise CFBDRecipeCompilationError("Scalar path cannot be traversed")
    if type(current) is not reference.expected_type:
        raise CFBDRecipeCompilationError("Scalar path value has the wrong type")
    return current


__all__: tuple[str, ...] = ()
