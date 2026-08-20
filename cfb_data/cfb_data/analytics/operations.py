"""Provide reusable backend-neutral recipe operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from ._graph import _NodeRef, _ValueRef
from ._recipes import step
from .errors import CFBDRecipeCompilationError, CFBDTransformError
from .types import RecipeRef, ValueRef

type _NullTraversal = Literal["error", "return_null"]
type _NullStruct = Literal["error", "null_fields"]
type _ExplosionMode = Literal["inner", "outer"]
type _NullList = Literal["error", "drop", "emit_null"]
type _EmptyList = Literal["error", "drop", "emit_null"]
type _NullElement = Literal["error", "drop", "keep"]


@dataclass(frozen=True, slots=True)
class NestedTransformDiagnostics:
    """Report bounded row effects from one nested logical-record operation."""

    input_rows: int
    output_rows: int
    excluded_source_rows: int
    excluded_elements: int


@dataclass(frozen=True, slots=True)
class NestedTransformResult:
    """Return ordered logical records with explicit row-effect evidence."""

    records: tuple[Mapping[str, object], ...]
    diagnostics: NestedTransformDiagnostics


def nested_value(
    value: object,
    *,
    path: tuple[str | int, ...],
    nulls: _NullTraversal,
) -> object:
    """Extract one nested logical value using structured path tokens.

    :param value: Canonical mapping/list logical value.
    :param path: Non-empty mapping-key and list-index tokens.
    :param nulls: Whether an encountered null returns null or raises.
    :return: Extracted value without type coercion.
    :raises CFBDTransformError: If traversal violates the declared policy.
    """
    if not path or len(path) > 32:
        raise CFBDTransformError("Nested paths require between 1 and 32 tokens")
    if nulls not in {"error", "return_null"}:
        raise CFBDTransformError("Nested null traversal policy is invalid")
    current = value
    for token in path:
        if current is None:
            if nulls == "return_null":
                return None
            raise CFBDTransformError("Nested traversal encountered null")
        if isinstance(token, str):
            if not isinstance(current, Mapping) or token not in current:
                raise CFBDTransformError("Nested mapping token is unavailable")
            current = current[token]
            continue
        if isinstance(token, int) and not isinstance(token, bool):
            if not isinstance(current, list):
                raise CFBDTransformError("Nested index token requires a list")
            try:
                current = current[token]
            except IndexError as exc:
                raise CFBDTransformError("Nested index token is unavailable") from exc
            continue
        raise CFBDTransformError("Nested path tokens must be strings or integers")
    return current


def flatten_struct(
    records: Sequence[Mapping[str, object]],
    *,
    field: str,
    fields: tuple[str, ...],
    prefix: str,
    retain_struct: bool,
    null_struct: _NullStruct,
) -> NestedTransformResult:
    """Flatten one explicitly declared struct without inferring its schema.

    :param records: Ordered canonical logical records.
    :param field: Top-level struct field to flatten.
    :param fields: Exact ordered nested field schema.
    :param prefix: Prefix applied verbatim to flattened field names.
    :param retain_struct: Whether the original struct field remains.
    :param null_struct: Whether null structs error or emit null fields.
    :return: New ordered records and zero-drop diagnostics.
    :raises CFBDTransformError: If schema, null, or collision policy fails.
    """
    _validate_field_name(field, label="Struct field")
    _validate_declared_fields(fields)
    if not isinstance(prefix, str):
        raise CFBDTransformError("Struct prefixes must be strings")
    if null_struct not in {"error", "null_fields"}:
        raise CFBDTransformError("Null struct policy is invalid")
    output_names = tuple(f"{prefix}{name}" for name in fields)
    if len(set(output_names)) != len(output_names):
        raise CFBDTransformError("Flattened struct field names collide")

    flattened: list[Mapping[str, object]] = []
    for record in records:
        if field not in record:
            raise CFBDTransformError("Declared struct field is unavailable")
        struct = record[field]
        if struct is None:
            if null_struct == "error":
                raise CFBDTransformError("Struct field is null")
            values: Mapping[str, object] = {name: None for name in fields}
        else:
            if not isinstance(struct, Mapping):
                raise CFBDTransformError("Struct field is not a mapping")
            if set(struct) != set(fields):
                raise CFBDTransformError(
                    "Struct keys do not match the explicit flatten schema"
                )
            values = struct
        base = dict(record)
        if not retain_struct:
            del base[field]
        collisions = set(base) & set(output_names)
        if collisions:
            raise CFBDTransformError("Flattened fields collide with record fields")
        for source_name, output_name in zip(fields, output_names, strict=True):
            base[output_name] = values[source_name]
        flattened.append(base)
    return NestedTransformResult(
        records=tuple(flattened),
        diagnostics=NestedTransformDiagnostics(
            input_rows=len(records),
            output_rows=len(flattened),
            excluded_source_rows=0,
            excluded_elements=0,
        ),
    )


def explode_list(
    records: Sequence[Mapping[str, object]],
    *,
    field: str,
    mode: _ExplosionMode,
    null_list: _NullList,
    empty_list: _EmptyList,
    null_element: _NullElement,
    ordinal_field: str | None,
    ordinal_start: Literal[0, 1],
) -> NestedTransformResult:
    """Explode exactly one list with complete grain-change semantics.

    :param records: Ordered canonical logical records.
    :param field: One top-level list field whose element replaces the list.
    :param mode: Inner or outer explosion semantics.
    :param null_list: Explicit null-list behavior.
    :param empty_list: Explicit empty-list behavior.
    :param null_element: Explicit behavior for null list elements.
    :param ordinal_field: Optional non-colliding element ordinal field.
    :param ordinal_start: Zero- or one-based ordinal policy.
    :return: Exploded records and exact exclusion diagnostics.
    :raises CFBDTransformError: If any declared semantic invariant fails.
    """
    _validate_field_name(field, label="List field")
    if mode not in {"inner", "outer"}:
        raise CFBDTransformError("Explosion mode is invalid")
    if null_list not in {"error", "drop", "emit_null"}:
        raise CFBDTransformError("Null-list policy is invalid")
    if empty_list not in {"error", "drop", "emit_null"}:
        raise CFBDTransformError("Empty-list policy is invalid")
    if null_element not in {"error", "drop", "keep"}:
        raise CFBDTransformError("Null-element policy is invalid")
    if mode == "inner" and (null_list == "emit_null" or empty_list == "emit_null"):
        raise CFBDTransformError("Inner explosion cannot emit null placeholder rows")
    if mode == "outer" and (
        null_list == "drop" or empty_list == "drop" or null_element == "drop"
    ):
        raise CFBDTransformError("Outer explosion cannot silently omit source rows")
    if ordinal_start not in {0, 1}:
        raise CFBDTransformError("Ordinal start must be zero or one")
    if ordinal_field is not None:
        _validate_field_name(ordinal_field, label="Ordinal field")
        if ordinal_field == field:
            raise CFBDTransformError("Ordinal field collides with exploded field")

    exploded: list[Mapping[str, object]] = []
    excluded_rows = 0
    excluded_elements = 0
    for record in records:
        if field not in record:
            raise CFBDTransformError("Declared list field is unavailable")
        if ordinal_field is not None and ordinal_field in record:
            raise CFBDTransformError("Ordinal field collides with a record field")
        source = record[field]
        action: _NullList | _EmptyList | None
        if source is None:
            action = null_list
            elements: list[object] = []
        elif isinstance(source, list):
            action = empty_list if not source else None
            elements = source
        else:
            raise CFBDTransformError("Exploded field is not a list or null")
        if action == "error":
            raise CFBDTransformError("List state violates explosion policy")
        if action == "drop":
            excluded_rows += 1
            continue
        if action == "emit_null":
            exploded.append(_exploded_record(record, field, None, ordinal_field, None))
            continue
        for index, element in enumerate(elements, start=ordinal_start):
            if element is None:
                if null_element == "error":
                    raise CFBDTransformError("Null list element violates policy")
                if null_element == "drop":
                    excluded_elements += 1
                    continue
            exploded.append(
                _exploded_record(record, field, element, ordinal_field, index)
            )
    return NestedTransformResult(
        records=tuple(exploded),
        diagnostics=NestedTransformDiagnostics(
            input_rows=len(records),
            output_rows=len(exploded),
            excluded_source_rows=excluded_rows,
            excluded_elements=excluded_elements,
        ),
    )


def _exploded_record(
    record: Mapping[str, object],
    field: str,
    element: object,
    ordinal_field: str | None,
    ordinal: int | None,
) -> Mapping[str, object]:
    output = dict(record)
    output[field] = element
    if ordinal_field is not None:
        output[ordinal_field] = ordinal
    return output


def _validate_field_name(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise CFBDTransformError(f"{label} must be a non-empty string")


def _validate_declared_fields(fields: tuple[str, ...]) -> None:
    if not fields or len(fields) != len(set(fields)):
        raise CFBDTransformError(
            "Struct schemas require unique explicitly ordered fields"
        )
    for field in fields:
        _validate_field_name(field, label="Struct schema field")


@step(id="cfb_data.operations.require_one", revision=1, deterministic=True, dask=True)
def require_one[RowT](rows: list[RowT]) -> RowT:
    """Return the only row after enforcing exact cardinality.

    :param rows: Validated source or dataset rows.
    :return: The sole row.
    :raises ValueError: If the input does not contain exactly one row.
    """
    if len(rows) != 1:
        raise ValueError("require_one expected exactly one row")
    return rows[0]


def value[ValueT](
    source: RecipeRef[object],
    *,
    path: tuple[str | int, ...],
    expected_type: type[ValueT],
) -> ValueRef[ValueT]:
    """Bind a validated scalar path from an upstream recipe output.

    :param source: Engine-created reference to an already declared node.
    :param path: Non-empty structured field/index token path.
    :param expected_type: Exact scalar type required after extraction.
    :return: Engine-owned typed scalar reference.
    :raises CFBDRecipeCompilationError: If the reference or path is invalid.
    """
    if not isinstance(source, _NodeRef):
        raise CFBDRecipeCompilationError(
            "value() accepts only engine-created recipe references"
        )
    if (
        not path
        or len(path) > 32
        or any(
            not isinstance(token, (str, int)) or isinstance(token, bool)
            for token in path
        )
    ):
        raise CFBDRecipeCompilationError(
            "value() paths require between one and 32 string/integer tokens"
        )
    if expected_type not in {str, int, float, bool} and not (
        isinstance(expected_type, type) and issubclass(expected_type, Enum)
    ):
        raise CFBDRecipeCompilationError(
            "value() expected_type must be a supported scalar type"
        )
    return cast(
        ValueRef[ValueT],
        _ValueRef(
            node_id=source.node_id,
            path=path,
            expected_type=cast(type[object], expected_type),
        ),
    )


__all__ = [
    "NestedTransformDiagnostics",
    "NestedTransformResult",
    "explode_list",
    "flatten_struct",
    "nested_value",
    "require_one",
    "value",
]
