"""Convert validated row models through a backend-neutral logical schema."""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Literal,
    Protocol,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

import pandas as pd
from pydantic import BaseModel

from cfb_data.errors import (
    CFBDDataFrameConversionError,
    CFBDOptionalDependencyError,
)

if TYPE_CHECKING:
    import polars as pl

_LogicalKind = Literal[
    "integer",
    "float",
    "boolean",
    "string",
    "datetime",
    "struct",
    "list",
]


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


class _UnsupportedTableAnnotationError(TypeError):
    """Report an annotation that has no backend-neutral representation."""


_FrameT_co = TypeVar("_FrameT_co", covariant=True)


class _DataFrameAdapter(Protocol[_FrameT_co]):
    """Convert validated rows to one concrete eager DataFrame type."""

    def from_models(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        models: Sequence[BaseModel],
    ) -> _FrameT_co:
        """Return a frame preserving all validated rows and columns."""


class _PandasAdapter:
    """Create pandas DataFrames with explicit native and nullable dtypes."""

    def from_models(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        models: Sequence[BaseModel],
    ) -> pd.DataFrame:
        """Return a pandas frame for validated model rows.

        :param endpoint: Endpoint producing the rows.
        :param row_model: Authoritative Pydantic row model.
        :param models: Validated rows in API order.
        :return: DataFrame with a normal :class:`pandas.RangeIndex`.
        :raises CFBDDataFrameConversionError: If conversion loses the contract.
        """
        try:
            schema = _logical_schema(row_model)
            records = _records_from_models(models, row_model, schema)
            columns = {
                field.name: pd.Series(
                    [record[field.name] for record in records],
                    dtype=_pandas_dtype(field.type),
                )
                for field in schema.fields
            }
            frame = pd.DataFrame(columns)
            _assert_frame_shape(
                columns=list(frame.columns),
                row_count=len(frame),
                expected_columns=[field.name for field in schema.fields],
                expected_rows=len(records),
            )
            if not frame.index.equals(pd.RangeIndex(len(records))):
                raise ValueError("pandas conversion did not preserve a RangeIndex")
            return frame
        except CFBDDataFrameConversionError:
            raise
        except Exception as exc:
            raise CFBDDataFrameConversionError(
                endpoint=endpoint,
                backend="pandas",
            ) from exc


class _PolarsAdapter:
    """Create strict Polars DataFrames with native nested columns."""

    def from_models(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        models: Sequence[BaseModel],
    ) -> pl.DataFrame:
        """Return a Polars frame for validated model rows.

        :param endpoint: Endpoint producing the rows.
        :param row_model: Authoritative Pydantic row model.
        :param models: Validated rows in API order.
        :return: Strict eager Polars DataFrame.
        :raises CFBDOptionalDependencyError: If Polars is not installed.
        :raises CFBDDataFrameConversionError: If conversion loses the contract.
        """
        try:
            import polars as pl
        except ModuleNotFoundError as exc:
            if exc.name == "polars":
                raise CFBDOptionalDependencyError(
                    'Polars support requires pip install "cfb-data[polars]"'
                ) from exc
            raise

        try:
            schema = _logical_schema(row_model)
            records = _records_from_models(models, row_model, schema)
            polars_schema = {
                field.name: _polars_dtype(field.type) for field in schema.fields
            }
            frame = pl.from_dicts(records, schema=polars_schema, strict=True)
            _assert_frame_shape(
                columns=frame.columns,
                row_count=frame.height,
                expected_columns=[field.name for field in schema.fields],
                expected_rows=len(records),
            )
            return frame
        except CFBDOptionalDependencyError:
            raise
        except Exception as exc:
            raise CFBDDataFrameConversionError(
                endpoint=endpoint,
                backend="polars",
            ) from exc


def _logical_schema(row_model: type[BaseModel]) -> _LogicalSchema:
    """Derive an ordered recursive schema from a Pydantic model declaration."""
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


def _records_from_models(
    models: Sequence[BaseModel],
    row_model: type[BaseModel],
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
    if not isinstance(value, Mapping):
        raise TypeError("Struct value must be a mapping")
    mapping = cast(Mapping[object, object], value)
    expected_names = tuple(field.name for field in fields)
    if set(mapping) != set(expected_names):
        raise ValueError("Struct keys do not match the logical schema")
    return {
        field.name: _normalize_value(mapping[field.name], field.type)
        for field in fields
    }


def _normalize_value(value: object, logical_type: _LogicalType) -> object:
    """Normalize one model-derived value for both DataFrame adapters."""
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


def _pandas_dtype(logical_type: _LogicalType) -> object:
    """Return the exact pandas dtype for a logical type."""
    if logical_type.kind == "integer":
        return "Int64" if logical_type.nullable else "int64"
    if logical_type.kind == "float":
        return "Float64" if logical_type.nullable else "float64"
    if logical_type.kind == "boolean":
        return "boolean" if logical_type.nullable else "bool"
    if logical_type.kind == "string":
        return "string"
    if logical_type.kind == "datetime":
        return "datetime64[ns, UTC]"
    if logical_type.kind in {"struct", "list"}:
        return object
    raise AssertionError(f"Unreachable logical kind: {logical_type.kind}")


def _polars_dtype(logical_type: _LogicalType) -> pl.DataType:
    """Return the strict Polars dtype for a logical type."""
    import polars as pl

    if logical_type.kind == "integer":
        return pl.Int64()
    if logical_type.kind == "float":
        return pl.Float64()
    if logical_type.kind == "boolean":
        return pl.Boolean()
    if logical_type.kind == "string":
        return pl.String()
    if logical_type.kind == "datetime":
        return pl.Datetime(time_unit="us", time_zone="UTC")
    if logical_type.kind == "struct":
        return pl.Struct(
            [
                pl.Field(field.name, _polars_dtype(field.type))
                for field in logical_type.fields
            ]
        )
    if logical_type.kind == "list" and logical_type.item is not None:
        return pl.List(_polars_dtype(logical_type.item))
    raise AssertionError(f"Unreachable logical kind: {logical_type.kind}")


def _assert_frame_shape(
    *,
    columns: Sequence[str],
    row_count: int,
    expected_columns: Sequence[str],
    expected_rows: int,
) -> None:
    """Reject conversions that changed column order or lost rows."""
    if list(columns) != list(expected_columns):
        raise ValueError("DataFrame columns do not match the logical schema")
    if row_count != expected_rows:
        raise ValueError("DataFrame row count does not match validated rows")
