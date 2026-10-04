"""Validate and canonically represent analytical function parameters."""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType, UnionType
from typing import Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from .errors import CFBDRecipeConfigurationError, CFBDRecipeParameterError

_RESERVED_NAMES = frozenset({"client", "plan", "policy", "resume_from"})


@dataclass(frozen=True, slots=True)
class _ValidatedParameters:
    """Retain validated values and which arguments a caller supplied."""

    values: Mapping[str, object]
    provided: frozenset[str]


def _bind_graph_parameters(
    function: object,
    signature: inspect.Signature,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    *,
    is_reference: Callable[[object], bool],
    validate_reference: Callable[[object, object], None],
) -> _ValidatedParameters:
    """Bind graph arguments while deferring validation of typed references."""
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        raise CFBDRecipeParameterError(
            "Recipe parameters do not match its signature"
        ) from exc
    provided = frozenset(bound.arguments)
    bound.apply_defaults()
    hints = get_type_hints(function, include_extras=True)
    validated: dict[str, object] = {}
    try:
        for name, value in bound.arguments.items():
            if is_reference(value):
                validate_reference(value, hints[name])
                validated[name] = value
                continue
            if (
                value is None
                and get_origin(hints[name]) in {UnionType, Union}
                and type(None) in get_args(hints[name])
            ):
                validated[name] = None
                continue
            adapter = _parameter_adapter(hints[name])
            validated[name] = _require_finite(
                adapter.validate_python(value, strict=True)
            )
    except (KeyError, ValidationError, TypeError, ValueError) as exc:
        raise CFBDRecipeParameterError("Recipe parameter validation failed") from exc
    return _ValidatedParameters(MappingProxyType(validated), provided)


def _validate_builder_signature(function: object, *, kind: str) -> inspect.Signature:
    """Validate a decorated builder or operation signature."""
    if not callable(function):
        raise CFBDRecipeConfigurationError(f"@{kind} requires a callable")
    signature = inspect.signature(function)
    if kind in {"dataset", "workflow"} and inspect.iscoroutinefunction(function):
        raise CFBDRecipeConfigurationError(f"@{kind} builders must be synchronous")
    parameters = tuple(signature.parameters.values())
    if kind == "source":
        if not parameters or parameters[0].name != "context":
            raise CFBDRecipeConfigurationError(
                "@source functions require an injected first 'context' parameter"
            )
        parameters = parameters[1:]
        signature = signature.replace(parameters=parameters)
    for parameter in parameters:
        if parameter.name in _RESERVED_NAMES:
            raise CFBDRecipeConfigurationError(
                f"@{kind} parameter {parameter.name!r} is reserved by the runtime"
            )
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            raise CFBDRecipeConfigurationError(
                f"@{kind} does not support variadic analytical parameters"
            )
        if parameter.annotation is inspect.Parameter.empty:
            raise CFBDRecipeConfigurationError(
                f"@{kind} parameter {parameter.name!r} requires an annotation"
            )
    if signature.return_annotation is inspect.Signature.empty:
        raise CFBDRecipeConfigurationError(f"@{kind} requires a return annotation")
    return signature


def _validate_call_parameters(
    function: object,
    signature: inspect.Signature,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> _ValidatedParameters:
    """Bind and strictly validate one recipe call."""
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        raise CFBDRecipeParameterError(
            "Recipe parameters do not match its signature"
        ) from exc
    provided = frozenset(bound.arguments)
    bound.apply_defaults()
    hints = get_type_hints(function, include_extras=True)
    validated: dict[str, object] = {}
    try:
        for name, value in bound.arguments.items():
            annotation = hints[name]
            if (
                value is None
                and get_origin(annotation) in {UnionType, Union}
                and type(None) in get_args(annotation)
            ):
                validated[name] = None
                continue
            adapter = _parameter_adapter(annotation)
            validated[name] = _require_finite(
                adapter.validate_python(value, strict=True)
            )
    except (KeyError, ValidationError, TypeError, ValueError) as exc:
        raise CFBDRecipeParameterError("Recipe parameter validation failed") from exc
    return _ValidatedParameters(MappingProxyType(validated), provided)


def _parameter_adapter(annotation: object) -> TypeAdapter[object]:
    """Respect model-owned configuration while retaining strict call validation."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return TypeAdapter(annotation)
    return TypeAdapter(annotation, config=ConfigDict(strict=True))


def _require_finite(value: object) -> object:
    """Return a value after rejecting all nested non-finite floats."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite values are not supported")
    if isinstance(value, BaseModel):
        _require_finite(value.model_dump(mode="python"))
    elif isinstance(value, Mapping):
        for item in value.values():
            _require_finite(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _require_finite(item)
    return value
