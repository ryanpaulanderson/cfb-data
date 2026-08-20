"""Build canonical Arrow tables from validated tabular response models."""

from __future__ import annotations

import hashlib
import json
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from typing import (
    Annotated,
    Final,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
)

import pyarrow as pa
from pydantic import BaseModel, TypeAdapter

_LogicalKind = Literal[
    "integer",
    "float",
    "boolean",
    "string",
    "scalar",
    "datetime",
    "struct",
    "list",
]
_ScalarKind = Literal["string", "integer", "float"]

_STORAGE_VERSION: Final = "1"
_STORAGE_VERSION_KEY: Final = b"cfb_data.storage_version"
_ROW_MODEL_KEY: Final = b"cfb_data.row_model"
_SCHEMA_DIGEST_KEY: Final = b"cfb_data.logical_schema_sha256"
_WRITER_VERSION_KEY: Final = b"cfb_data.writer_version"
_ANALYTICS_STORAGE_VERSION: Final = "2"
_ANALYTICS_OUTPUT_ID_KEY: Final = b"cfb_data.analytics.output_id"
_ANALYTICS_OUTPUT_REVISION_KEY: Final = b"cfb_data.analytics.output_revision"
_SCALAR_ENCODING: Final = "tagged_struct_v1"
_SCALAR_FIELDS: Final = (
    "kind",
    "string_value",
    "integer_value",
    "float_value",
)


@dataclass(frozen=True, slots=True)
class _LogicalType:
    """Describe one recursively representable table value."""

    kind: _LogicalKind
    nullable: bool = False
    fields: tuple[_LogicalField, ...] = ()
    item: _LogicalType | None = None


@dataclass(frozen=True, slots=True)
class _LogicalField:
    """Bind a declared field name to its recursive logical type."""

    name: str
    type: _LogicalType


@dataclass(frozen=True, slots=True)
class _LogicalSchema:
    """Preserve the declared field order of one Pydantic row model."""

    fields: tuple[_LogicalField, ...]


@dataclass(frozen=True, slots=True)
class _AnalyticsTableIdentity:
    """Identify an analytics table independently of its Python model location."""

    output_id: str
    revision: int

    def __post_init__(self) -> None:
        """Validate the durable output identity."""
        if not isinstance(self.output_id, str):
            raise TypeError("Analytics output IDs must be strings")
        namespace, separator, name = self.output_id.partition(".")
        if not separator or not namespace or not name:
            raise ValueError("Analytics output IDs must be namespaced")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool):
            raise TypeError("Analytics output revisions must be integers")
        if self.revision < 1:
            raise ValueError("Analytics output revisions must be positive")


class _UnsupportedTableAnnotationError(TypeError):
    """Report an annotation that has no backend-neutral representation."""


class _CanonicalTableMetadataError(ValueError):
    """Report incompatible or incomplete cfb-data table metadata."""


class _CanonicalTableSchemaError(ValueError):
    """Report a physical Arrow schema that violates the logical schema."""


class _ScalarEncodingError(ValueError):
    """Report a heterogeneous scalar that violates its tagged encoding."""


def _logical_schema(row_model: type[BaseModel]) -> _LogicalSchema:
    """Derive an ordered recursive schema from a Pydantic model declaration.

    :param row_model: Pydantic model defining one tabular row.
    :return: Backend-neutral recursive table schema.
    :raises _UnsupportedTableAnnotationError: If a field cannot be tabularized.
    """
    return _LogicalSchema(fields=_model_fields(row_model, active_models=frozenset()))


def _model_fields(
    row_model: type[BaseModel],
    *,
    active_models: frozenset[type[BaseModel]],
) -> tuple[_LogicalField, ...]:
    """Derive fields while rejecting recursive model cycles explicitly."""
    if row_model in active_models:
        raise _UnsupportedTableAnnotationError(
            f"Recursive model {row_model.__name__} cannot be tabularized"
        )
    next_active = active_models | {row_model}
    fields: list[_LogicalField] = []
    for name, field_info in row_model.model_fields.items():
        annotation = field_info.annotation
        if annotation is None:
            raise _UnsupportedTableAnnotationError(
                f"Field {row_model.__name__}.{name} has no annotation"
            )
        fields.append(
            _LogicalField(
                name=name,
                type=_logical_type(annotation, active_models=next_active),
            )
        )
    return tuple(fields)


def _logical_type(
    annotation: object,
    *,
    active_models: frozenset[type[BaseModel]],
) -> _LogicalType:
    """Map one supported annotation to its recursive logical type."""
    origin = get_origin(annotation)
    if origin is Annotated:
        annotated_args = get_args(annotation)
        if not annotated_args:
            raise _UnsupportedTableAnnotationError("Empty Annotated type")
        return _logical_type(annotated_args[0], active_models=active_models)

    union_origin = types.UnionType if isinstance(annotation, types.UnionType) else None
    if origin is Union or union_origin is types.UnionType:
        union_args = get_args(annotation)
        non_none = tuple(item for item in union_args if item is not type(None))
        if len(union_args) == 3 and set(union_args) == {str, int, float}:
            return _LogicalType("scalar")
        if len(non_none) != 1 or len(non_none) == len(union_args):
            raise _UnsupportedTableAnnotationError(
                f"Only T | None unions are supported, received {annotation!r}"
            )
        return replace(
            _logical_type(non_none[0], active_models=active_models),
            nullable=True,
        )

    if annotation is bool:
        return _LogicalType("boolean")
    if annotation is int:
        return _LogicalType("integer")
    if annotation is float:
        return _LogicalType("float")
    if annotation is str:
        return _LogicalType("string")
    if annotation is datetime:
        return _LogicalType("datetime")

    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return _LogicalType("string")
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _LogicalType(
            "struct",
            fields=_model_fields(annotation, active_models=active_models),
        )
    if origin is list:
        list_args = get_args(annotation)
        if len(list_args) != 1:
            raise _UnsupportedTableAnnotationError(
                f"List annotation must have one item type: {annotation!r}"
            )
        item_annotation = next(iter(list_args))
        return _LogicalType(
            "list",
            item=_logical_type(item_annotation, active_models=active_models),
        )

    raise _UnsupportedTableAnnotationError(
        f"Unsupported table annotation: {annotation!r}"
    )


def _arrow_table_from_models[ModelT: BaseModel](
    *,
    row_model: type[ModelT],
    models: Sequence[ModelT],
) -> pa.Table:
    """Return the canonical Arrow table for validated model rows.

    :param row_model: Authoritative model defining one row.
    :param models: Validated rows in source order.
    :return: Arrow table with exact recursive schema and storage metadata.
    :raises TypeError: If a row or value violates the logical model type.
    :raises ValueError: If a value violates a logical table invariant.
    """
    logical_schema = _logical_schema(row_model)
    records = _records_from_models(models, row_model, logical_schema)
    storage_records = [
        _encode_storage_struct(record, logical_schema.fields) for record in records
    ]
    return pa.Table.from_pylist(
        storage_records,
        schema=_expected_arrow_schema(row_model, logical_schema=logical_schema),
    )


def _analytics_arrow_table_from_models[ModelT: BaseModel](
    *,
    row_model: type[ModelT],
    models: Sequence[ModelT],
    identity: _AnalyticsTableIdentity,
) -> pa.Table:
    """Return an Arrow table for analytics Parquet codec version 2.

    :param row_model: Authoritative model defining one row.
    :param models: Validated rows in deterministic output order.
    :param identity: Stable recipe-output identity and semantic revision.
    :return: Arrow table whose compatibility is independent of model location.
    :raises TypeError: If a row or value violates the logical model type.
    :raises ValueError: If a value violates a logical table invariant.
    """
    logical_schema = _logical_schema(row_model)
    records = _records_from_models(models, row_model, logical_schema)
    storage_records = [
        _encode_storage_struct(record, logical_schema.fields) for record in records
    ]
    return pa.Table.from_pylist(
        storage_records,
        schema=_analytics_expected_arrow_schema(
            row_model,
            identity=identity,
            logical_schema=logical_schema,
        ),
    )


def _models_from_arrow_table[ModelT: BaseModel](
    *,
    row_model: type[ModelT],
    response_adapter: TypeAdapter[list[ModelT]],
    table: pa.Table,
) -> list[ModelT]:
    """Validate and return models decoded from a canonical Arrow table.

    :param row_model: Expected authoritative row model.
    :param response_adapter: Pydantic adapter for a list of expected rows.
    :param table: Canonical Arrow table to decode.
    :return: Fully Pydantic-validated rows in table order.
    :raises _CanonicalTableMetadataError: If cfb-data metadata is incompatible.
    :raises _CanonicalTableSchemaError: If the Arrow schema is incompatible.
    :raises _ScalarEncodingError: If a tagged scalar is malformed.
    :raises pydantic.ValidationError: If decoded rows violate the model contract.
    """
    records = _logical_records_from_arrow_table(row_model=row_model, table=table)
    return response_adapter.validate_python(records)


def _analytics_models_from_arrow_table[ModelT: BaseModel](
    *,
    row_model: type[ModelT],
    response_adapter: TypeAdapter[list[ModelT]],
    table: pa.Table,
    identity: _AnalyticsTableIdentity,
) -> list[ModelT]:
    """Validate models decoded from an analytics Parquet codec 2 table.

    :param row_model: Authoritative model defining one row.
    :param response_adapter: Pydantic adapter for a list of expected rows.
    :param table: Canonical analytics Parquet codec 2 table to decode.
    :param identity: Expected stable recipe-output identity and revision.
    :return: Fully Pydantic-validated rows in table order.
    """
    records = _analytics_logical_records_from_arrow_table(
        row_model=row_model,
        table=table,
        identity=identity,
    )
    return response_adapter.validate_python(records)


def _logical_records_from_arrow_table(
    *,
    row_model: type[BaseModel],
    table: pa.Table,
) -> list[dict[str, object]]:
    """Decode canonical storage values into backend-neutral logical records.

    :param row_model: Expected authoritative row model.
    :param table: Canonical Arrow table to decode.
    :return: Python records preserving row order and logical scalar values.
    :raises _CanonicalTableMetadataError: If cfb-data metadata is incompatible.
    :raises _CanonicalTableSchemaError: If the Arrow schema is incompatible.
    :raises _ScalarEncodingError: If a tagged scalar is malformed.
    """
    logical_schema = _logical_schema(row_model)
    _assert_canonical_arrow_table(
        row_model=row_model,
        table=table,
        logical_schema=logical_schema,
    )
    return [
        _decode_storage_struct(record, logical_schema.fields)
        for record in table.to_pylist()
    ]


def _analytics_logical_records_from_arrow_table(
    *,
    row_model: type[BaseModel],
    table: pa.Table,
    identity: _AnalyticsTableIdentity,
) -> list[dict[str, object]]:
    """Decode an analytics Parquet codec 2 table into logical records.

    :param row_model: Authoritative model defining one row.
    :param table: Canonical analytics Parquet codec 2 table to decode.
    :param identity: Expected stable recipe-output identity and revision.
    :return: Python records preserving row and field order.
    :raises _CanonicalTableMetadataError: If metadata is incompatible.
    :raises _CanonicalTableSchemaError: If the physical schema differs.
    :raises _ScalarEncodingError: If a tagged scalar is malformed.
    """
    logical_schema = _logical_schema(row_model)
    _assert_analytics_arrow_table(
        row_model=row_model,
        table=table,
        identity=identity,
        logical_schema=logical_schema,
    )
    return [
        _decode_storage_struct(record, logical_schema.fields)
        for record in table.to_pylist()
    ]


def _assert_canonical_arrow_table(
    *,
    row_model: type[BaseModel],
    table: pa.Table,
    logical_schema: _LogicalSchema | None = None,
) -> None:
    """Verify physical schema and cfb-data metadata for an expected row model.

    :param row_model: Expected authoritative row model.
    :param table: Arrow table to inspect without decoding row values.
    :param logical_schema: Previously derived schema, if already available.
    :raises _CanonicalTableMetadataError: If required metadata is incompatible.
    :raises _CanonicalTableSchemaError: If the physical schema differs.
    """
    schema = logical_schema or _logical_schema(row_model)
    expected = _expected_arrow_schema(row_model, logical_schema=schema)
    _assert_table_schema_and_metadata(
        table=table,
        expected=expected,
        compatibility_keys=(
            _STORAGE_VERSION_KEY,
            _ROW_MODEL_KEY,
            _SCHEMA_DIGEST_KEY,
        ),
    )


def _assert_analytics_arrow_table(
    *,
    row_model: type[BaseModel],
    table: pa.Table,
    identity: _AnalyticsTableIdentity,
    logical_schema: _LogicalSchema | None = None,
) -> None:
    """Verify an analytics Parquet codec 2 table against its output contract.

    :param row_model: Authoritative row model supplying the logical schema.
    :param table: Arrow table to inspect without decoding row values.
    :param identity: Expected stable recipe-output identity and revision.
    :param logical_schema: Previously derived schema, if already available.
    :raises _CanonicalTableMetadataError: If metadata is incompatible.
    :raises _CanonicalTableSchemaError: If the physical schema differs.
    """
    schema = logical_schema or _logical_schema(row_model)
    expected = _analytics_expected_arrow_schema(
        row_model,
        identity=identity,
        logical_schema=schema,
    )
    _assert_table_schema_and_metadata(
        table=table,
        expected=expected,
        compatibility_keys=(
            _STORAGE_VERSION_KEY,
            _ANALYTICS_OUTPUT_ID_KEY,
            _ANALYTICS_OUTPUT_REVISION_KEY,
            _SCHEMA_DIGEST_KEY,
        ),
    )


def _assert_table_schema_and_metadata(
    *,
    table: pa.Table,
    expected: pa.Schema,
    compatibility_keys: tuple[bytes, ...],
) -> None:
    """Verify physical schema and selected compatibility metadata."""
    if not table.schema.remove_metadata().equals(expected.remove_metadata()):
        raise _CanonicalTableSchemaError(
            "Arrow table does not match the expected physical schema"
        )

    metadata = table.schema.metadata
    if metadata is None:
        raise _CanonicalTableMetadataError("Arrow table has no cfb-data metadata")

    expected_metadata = expected.metadata
    if expected_metadata is None:
        raise AssertionError("Expected Arrow schema metadata is missing")
    for key in compatibility_keys:
        if metadata.get(key) != expected_metadata[key]:
            raise _CanonicalTableMetadataError(
                "Arrow table has incompatible cfb-data metadata"
            )

    writer_version = metadata.get(_WRITER_VERSION_KEY)
    if writer_version is None:
        raise _CanonicalTableMetadataError("Arrow table has no writer version")
    try:
        decoded_writer_version = writer_version.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _CanonicalTableMetadataError(
            "Arrow table writer version is not UTF-8"
        ) from exc
    if not decoded_writer_version:
        raise _CanonicalTableMetadataError("Arrow table writer version is empty")


def _expected_arrow_schema(
    row_model: type[BaseModel],
    *,
    logical_schema: _LogicalSchema | None = None,
) -> pa.Schema:
    """Return the canonical physical schema and metadata for a row model."""
    schema = logical_schema or _logical_schema(row_model)
    return pa.schema(
        [_arrow_field(field) for field in schema.fields],
        metadata=_storage_metadata(row_model, schema),
    )


def _analytics_expected_arrow_schema(
    row_model: type[BaseModel],
    *,
    identity: _AnalyticsTableIdentity,
    logical_schema: _LogicalSchema | None = None,
) -> pa.Schema:
    """Return the analytics Parquet codec 2 schema for an output contract.

    :param row_model: Authoritative model supplying ordered logical fields.
    :param identity: Stable recipe-output identity and revision.
    :param logical_schema: Previously derived schema, if already available.
    :return: Exact physical schema and codec 2 compatibility metadata.
    """
    schema = logical_schema or _logical_schema(row_model)
    return pa.schema(
        [_arrow_field(field) for field in schema.fields],
        metadata=_analytics_storage_metadata(identity, schema),
    )


def _arrow_field(field: _LogicalField) -> pa.Field[pa.DataType]:
    """Return one Arrow field with recursive logical nullability."""
    return pa.field(
        field.name,
        _arrow_type(field.type),
        nullable=field.type.nullable,
    )


def _arrow_type(logical_type: _LogicalType) -> pa.DataType:
    """Return the canonical Arrow data type for one logical type."""
    if logical_type.kind == "integer":
        return pa.int64()
    if logical_type.kind == "float":
        return pa.float64()
    if logical_type.kind == "boolean":
        return pa.bool_()
    if logical_type.kind == "string":
        return pa.string()
    if logical_type.kind == "datetime":
        return pa.timestamp("us", tz="UTC")
    if logical_type.kind == "scalar":
        return pa.struct(
            [
                pa.field("kind", pa.string(), nullable=False),
                pa.field("string_value", pa.string(), nullable=True),
                pa.field("integer_value", pa.binary(), nullable=True),
                pa.field("float_value", pa.float64(), nullable=True),
            ]
        )
    if logical_type.kind == "struct":
        return pa.struct([_arrow_field(field) for field in logical_type.fields])
    if logical_type.kind == "list" and logical_type.item is not None:
        return pa.list_(
            pa.field(
                "element",
                _arrow_type(logical_type.item),
                nullable=logical_type.item.nullable,
            )
        )
    raise AssertionError(f"Unreachable logical kind: {logical_type.kind}")


def _records_from_models[ModelT: BaseModel](
    models: Sequence[ModelT],
    row_model: type[ModelT],
    schema: _LogicalSchema,
) -> list[dict[str, object]]:
    """Dump validated models in Python mode and normalize logical values."""
    records: list[dict[str, object]] = []
    for model in models:
        if not isinstance(model, row_model):
            raise TypeError(
                f"Expected {row_model.__name__}, received {type(model).__name__}"
            )
        raw: object = model.model_dump(mode="python", by_alias=False)
        records.append(_normalize_struct(raw, schema.fields))
    return records


def _normalize_struct(
    value: object,
    fields: tuple[_LogicalField, ...],
) -> dict[str, object]:
    """Normalize a model-derived mapping in declared field order."""
    mapping = _checked_mapping(value, fields)
    return {
        field.name: _normalize_value(mapping[field.name], field.type)
        for field in fields
    }


def _normalize_value(value: object, logical_type: _LogicalType) -> object:
    """Normalize one model-derived value against its logical type."""
    if value is None:
        if logical_type.nullable:
            return None
        raise TypeError("Non-nullable logical value is null")

    if logical_type.kind == "boolean":
        if not isinstance(value, bool):
            raise TypeError("Boolean logical value has the wrong type")
        return value
    if logical_type.kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("Integer logical value has the wrong type")
        return value
    if logical_type.kind == "float":
        if not isinstance(value, float):
            raise TypeError("Float logical value has the wrong type")
        return value
    if logical_type.kind == "string":
        if isinstance(value, StrEnum):
            return value.value
        if not isinstance(value, str):
            raise TypeError("String logical value has the wrong type")
        return value
    if logical_type.kind == "scalar":
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise TypeError("Heterogeneous scalar value has the wrong type")
        return value
    if logical_type.kind == "datetime":
        if not isinstance(value, datetime):
            raise TypeError("Datetime logical value has the wrong type")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime logical values must be timezone-aware")
        return value.astimezone(UTC)
    if logical_type.kind == "struct":
        return _normalize_struct(value, logical_type.fields)
    if logical_type.kind == "list":
        if not isinstance(value, list) or logical_type.item is None:
            raise TypeError("List logical value has the wrong type")
        return [_normalize_value(item, logical_type.item) for item in value]
    raise AssertionError(f"Unreachable logical kind: {logical_type.kind}")


def _encode_storage_struct(
    value: object,
    fields: tuple[_LogicalField, ...],
) -> dict[str, object]:
    """Encode one normalized logical struct for canonical Arrow storage."""
    mapping = _checked_mapping(value, fields)
    return {
        field.name: _encode_storage_value(mapping[field.name], field.type)
        for field in fields
    }


def _encode_storage_value(value: object, logical_type: _LogicalType) -> object:
    """Encode one logical value into its canonical Arrow storage value."""
    if value is None:
        if logical_type.nullable:
            return None
        raise TypeError("Non-nullable storage value is null")
    if logical_type.kind == "scalar":
        return _encode_scalar(value)
    if logical_type.kind == "struct":
        return _encode_storage_struct(value, logical_type.fields)
    if logical_type.kind == "list":
        if not isinstance(value, list) or logical_type.item is None:
            raise TypeError("List storage value has the wrong type")
        return [_encode_storage_value(item, logical_type.item) for item in value]
    return _normalize_value(value, logical_type)


def _encode_scalar(value: object) -> dict[str, object]:
    """Encode a heterogeneous scalar without losing its concrete Python type."""
    if isinstance(value, str):
        kind: _ScalarKind = "string"
        selected_field = "string_value"
    elif isinstance(value, int) and not isinstance(value, bool):
        kind = "integer"
        selected_field = "integer_value"
        value = _encode_integer(value)
    elif isinstance(value, float):
        kind = "float"
        selected_field = "float_value"
    else:
        raise TypeError("Heterogeneous scalar storage value has the wrong type")

    encoded: dict[str, object] = {
        "kind": kind,
        "string_value": None,
        "integer_value": None,
        "float_value": None,
    }
    encoded[selected_field] = value
    return encoded


def _encode_integer(value: int) -> bytes:
    """Encode an arbitrary integer as canonical signed big-endian bytes.

    :param value: Integer to preserve without a fixed-width bound.
    :return: Minimal two's-complement byte representation.
    """
    if value >= 0:
        byte_count = max(1, (value.bit_length() + 8) // 8)
    else:
        byte_count = max(1, ((~value).bit_length() + 8) // 8)
    return value.to_bytes(byte_count, byteorder="big", signed=True)


def _decode_storage_struct(
    value: object,
    fields: tuple[_LogicalField, ...],
) -> dict[str, object]:
    """Decode one canonical Arrow struct into logical Python values."""
    mapping = _checked_mapping(value, fields)
    return {
        field.name: _decode_storage_value(mapping[field.name], field.type)
        for field in fields
    }


def _decode_storage_value(value: object, logical_type: _LogicalType) -> object:
    """Decode one canonical Arrow value into its logical Python value."""
    if value is None:
        if logical_type.nullable:
            return None
        raise TypeError("Non-nullable storage value is null")
    if logical_type.kind == "scalar":
        return _decode_scalar(value)
    if logical_type.kind == "struct":
        return _decode_storage_struct(value, logical_type.fields)
    if logical_type.kind == "list":
        if not isinstance(value, list) or logical_type.item is None:
            raise TypeError("List storage value has the wrong type")
        return [_decode_storage_value(item, logical_type.item) for item in value]
    return _normalize_value(value, logical_type)


def _decode_scalar(value: object) -> str | int | float:
    """Decode and validate one tagged heterogeneous scalar."""
    if not isinstance(value, Mapping):
        raise _ScalarEncodingError("Tagged scalar must be a mapping")
    mapping = cast(Mapping[object, object], value)
    if set(mapping) != set(_SCALAR_FIELDS):
        raise _ScalarEncodingError("Tagged scalar fields are invalid")

    kind = mapping["kind"]
    if kind not in {"string", "integer", "float"}:
        raise _ScalarEncodingError("Tagged scalar kind is invalid")
    field_by_kind = {
        "string": "string_value",
        "integer": "integer_value",
        "float": "float_value",
    }
    selected_field = field_by_kind[kind]
    populated_fields = [
        field_name
        for field_name in _SCALAR_FIELDS[1:]
        if mapping[field_name] is not None
    ]
    if populated_fields != [selected_field]:
        raise _ScalarEncodingError("Tagged scalar value slots are invalid")

    selected_value = mapping[selected_field]
    if kind == "string" and isinstance(selected_value, str):
        return selected_value
    if kind == "integer" and isinstance(selected_value, bytes):
        integer_value = int.from_bytes(selected_value, byteorder="big", signed=True)
        if _encode_integer(integer_value) == selected_value:
            return integer_value
        raise _ScalarEncodingError("Tagged scalar integer is not canonical")
    if kind == "float" and isinstance(selected_value, float):
        return selected_value
    raise _ScalarEncodingError("Tagged scalar value type does not match its kind")


def _checked_mapping(
    value: object,
    fields: tuple[_LogicalField, ...],
) -> Mapping[object, object]:
    """Return a mapping whose keys exactly match the declared struct fields."""
    if not isinstance(value, Mapping):
        raise TypeError("Struct value must be a mapping")
    mapping = cast(Mapping[object, object], value)
    expected_names = tuple(field.name for field in fields)
    if set(mapping) != set(expected_names):
        raise ValueError("Struct keys do not match the logical schema")
    return mapping


def _storage_metadata(
    row_model: type[BaseModel],
    schema: _LogicalSchema,
) -> dict[bytes | str, bytes | str]:
    """Return deterministic namespaced metadata for a canonical table."""
    return {
        _STORAGE_VERSION_KEY: _STORAGE_VERSION.encode("ascii"),
        _ROW_MODEL_KEY: _row_model_identifier(row_model).encode("utf-8"),
        _SCHEMA_DIGEST_KEY: _logical_schema_digest(schema).encode("ascii"),
        _WRITER_VERSION_KEY: _installed_package_version().encode("utf-8"),
    }


def _analytics_storage_metadata(
    identity: _AnalyticsTableIdentity,
    schema: _LogicalSchema,
) -> dict[bytes | str, bytes | str]:
    """Return deterministic metadata for an analytics Parquet codec 2 table."""
    return {
        _STORAGE_VERSION_KEY: _ANALYTICS_STORAGE_VERSION.encode("ascii"),
        _ANALYTICS_OUTPUT_ID_KEY: identity.output_id.encode("utf-8"),
        _ANALYTICS_OUTPUT_REVISION_KEY: str(identity.revision).encode("ascii"),
        _SCHEMA_DIGEST_KEY: _logical_schema_digest(schema).encode("ascii"),
        _WRITER_VERSION_KEY: _installed_package_version().encode("utf-8"),
    }


def _row_model_identifier(row_model: type[BaseModel]) -> str:
    """Return the stable module-qualified identity stored with a row model."""
    return f"{row_model.__module__}:{row_model.__qualname__}"


def _logical_schema_digest(schema: _LogicalSchema) -> str:
    """Return a stable digest of logical shape, order, and nullability."""
    payload = json.dumps(
        _logical_schema_payload(schema),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _logical_schema_payload(schema: _LogicalSchema) -> dict[str, object]:
    """Return the deterministic JSON-compatible form of a logical schema."""
    return {
        "fields": [
            {"name": field.name, "type": _logical_type_payload(field.type)}
            for field in schema.fields
        ]
    }


def _logical_type_payload(logical_type: _LogicalType) -> dict[str, object]:
    """Return the deterministic JSON-compatible form of a logical type."""
    payload: dict[str, object] = {
        "kind": logical_type.kind,
        "nullable": logical_type.nullable,
    }
    if logical_type.kind == "scalar":
        payload["encoding"] = {
            "name": _SCALAR_ENCODING,
            "fields": [
                {"name": "kind", "kind": "string", "nullable": False},
                {
                    "name": "string_value",
                    "kind": "string",
                    "nullable": True,
                },
                {
                    "name": "integer_value",
                    "kind": "binary",
                    "nullable": True,
                },
                {
                    "name": "float_value",
                    "kind": "float",
                    "nullable": True,
                },
            ],
            "kind_to_value_field": [
                ["string", "string_value"],
                ["integer", "integer_value"],
                ["float", "float_value"],
            ],
            "populated_value_slots": 1,
        }
    if logical_type.kind == "struct":
        payload["fields"] = [
            {"name": field.name, "type": _logical_type_payload(field.type)}
            for field in logical_type.fields
        ]
    if logical_type.kind == "list" and logical_type.item is not None:
        payload["item"] = _logical_type_payload(logical_type.item)
    return payload


def _installed_package_version() -> str:
    """Return package metadata version without duplicating pyproject state."""
    try:
        return version("cfb-data")
    except PackageNotFoundError:
        return "unknown"
