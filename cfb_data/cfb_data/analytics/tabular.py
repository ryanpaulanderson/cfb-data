"""Provide portable flat-table operations for pandas and Polars frames."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

import narwhals.stable.v2 as nw
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
from narwhals.stable.v2.typing import IntoDataFrame

from .errors import CFBDTransformError

type PortableDType = Literal[
    "boolean",
    "int64",
    "float64",
    "string",
    "date32",
    "timestamp[us]",
    "timestamp[us, UTC]",
]
type _Backend = Literal["pandas", "polars"]

_PORTABLE_DTYPES: Mapping[PortableDType, pa.DataType] = {
    "boolean": pa.bool_(),
    "int64": pa.int64(),
    "float64": pa.float64(),
    "string": pa.string(),
    "date32": pa.date32(),
    "timestamp[us]": pa.timestamp("us"),
    "timestamp[us, UTC]": pa.timestamp("us", tz="UTC"),
}


def select_columns[FrameT: IntoDataFrame](
    frame: FrameT, *, columns: tuple[str, ...]
) -> FrameT:
    """Select an explicit ordered set of unique columns.

    :param frame: Eager pandas or Polars DataFrame.
    :param columns: Exact output column order.
    :return: A new frame of the same backend.
    :raises CFBDTransformError: If the frame or selection is invalid.
    """
    portable = _portable_frame(frame)
    _validate_columns(columns, label="Selected columns")
    _require_available(portable, columns)
    return _native_frame(portable.select(columns), backend=_backend(frame))


def rename_columns[FrameT: IntoDataFrame](
    frame: FrameT,
    *,
    mapping: Mapping[str, str],
) -> FrameT:
    """Rename columns without allowing overwrite or ambiguous output.

    :param frame: Eager pandas or Polars DataFrame.
    :param mapping: Non-empty source-to-output name mapping.
    :return: A new frame of the same backend and original column order.
    :raises CFBDTransformError: If names are missing, invalid, or collide.
    """
    portable = _portable_frame(frame)
    if not mapping:
        raise CFBDTransformError("Rename mappings cannot be empty")
    sources = tuple(mapping)
    targets = tuple(mapping.values())
    _validate_columns(sources, label="Rename source columns")
    _validate_columns(targets, label="Rename target columns")
    _require_available(portable, sources)
    unchanged = set(portable.columns) - set(sources)
    if unchanged & set(targets):
        raise CFBDTransformError("Renamed columns collide with existing columns")
    return _native_frame(portable.rename(dict(mapping)), backend=_backend(frame))


def strict_cast_columns[FrameT: IntoDataFrame](
    frame: FrameT,
    *,
    columns: Mapping[str, PortableDType],
) -> FrameT:
    """Apply Arrow-safe casts with an explicit finite logical type vocabulary.

    Casting never enables unsafe overflow or truncation. String parsing and
    temporal formatting remain separate explicit operations.

    :param frame: Eager pandas or Polars DataFrame.
    :param columns: Non-empty mapping of column names to target logical types.
    :return: A new frame of the same backend and original column order.
    :raises CFBDTransformError: If a target is missing, unsupported, or lossy.
    """
    portable = _portable_frame(frame)
    if not columns:
        raise CFBDTransformError("Strict cast mappings cannot be empty")
    names = tuple(columns)
    _validate_columns(names, label="Strict cast columns")
    _require_available(portable, names)
    table = portable.to_arrow()
    cast_table = table
    for index, field in enumerate(table.schema):
        target_name = columns.get(field.name)
        if target_name is None:
            continue
        target = _PORTABLE_DTYPES.get(target_name)
        if target is None:
            raise CFBDTransformError("Strict cast target type is unsupported")
        try:
            casted = pc.cast(table[field.name], target_type=target, safe=True)
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as exc:
            raise CFBDTransformError("Strict cast would lose or reject values") from exc
        cast_table = cast_table.set_column(
            index,
            pa.field(
                field.name,
                target,
                nullable=field.nullable,
                metadata=field.metadata,
            ),
            casted,
        )
    return _native_from_arrow(cast_table, original=frame)


def sort_rows[FrameT: IntoDataFrame](
    frame: FrameT,
    *,
    by: tuple[str, ...],
    descending: bool | tuple[bool, ...] = False,
    nulls_last: bool,
) -> FrameT:
    """Sort rows stably with an explicit null-placement policy.

    Equal keys retain input order by adding a collision-free ordinal only for
    the duration of the operation.

    :param frame: Eager pandas or Polars DataFrame.
    :param by: Non-empty unique ordered sort keys.
    :param descending: One direction for all keys or one per key.
    :param nulls_last: Whether null keys sort after non-null keys.
    :return: A stably sorted frame of the same backend.
    :raises CFBDTransformError: If keys or directions are invalid.
    """
    portable = _portable_frame(frame)
    _validate_columns(by, label="Sort columns")
    _require_available(portable, by)
    directions = _sort_directions(descending, width=len(by))
    ordinal = _temporary_column(portable.columns)
    ordered = (
        portable.with_row_index(ordinal)
        .sort(
            (*by, ordinal),
            descending=(*directions, False),
            nulls_last=nulls_last,
        )
        .drop(ordinal)
    )
    return _native_frame(ordered, backend=_backend(frame))


def _portable_frame[FrameT: IntoDataFrame](frame: FrameT) -> nw.DataFrame[FrameT]:
    backend = _backend(frame)
    try:
        portable = nw.from_native(frame, eager_only=True)
    except (TypeError, ValueError) as exc:
        raise CFBDTransformError(
            f"{backend} frame cannot enter portable tabular operations"
        ) from exc
    if not isinstance(portable, nw.DataFrame):
        raise CFBDTransformError("Portable operations require an eager DataFrame")
    return portable


def _native_frame[FrameT: IntoDataFrame](
    frame: nw.DataFrame[FrameT],
    *,
    backend: _Backend,
) -> FrameT:
    native = nw.to_native(frame)
    if _backend(native) != backend:
        raise CFBDTransformError("Portable operation changed the frame backend")
    return native


def _native_from_arrow[FrameT: IntoDataFrame](
    table: pa.Table,
    *,
    original: FrameT,
) -> FrameT:
    backend = _backend(original)
    try:
        if backend == "pandas":
            native = table.to_pandas(types_mapper=pd.ArrowDtype)
        else:
            portable = nw.DataFrame.from_arrow(table, backend=backend)
            native = nw.to_native(portable)
    except (TypeError, ValueError, pa.ArrowException) as exc:
        raise CFBDTransformError(
            "Arrow result cannot materialize in the backend"
        ) from exc
    if _backend(native) != backend:
        raise CFBDTransformError("Arrow materialization changed the frame backend")
    return cast(FrameT, native)


def _backend(frame: object) -> _Backend:
    module = type(frame).__module__.partition(".")[0]
    if module == "pandas" and type(frame).__name__ == "DataFrame":
        return "pandas"
    if module == "polars" and type(frame).__name__ == "DataFrame":
        return "polars"
    raise CFBDTransformError("Portable operations support pandas and Polars DataFrames")


def _validate_columns(columns: tuple[str, ...], *, label: str) -> None:
    if (
        not columns
        or len(columns) != len(set(columns))
        or any(not isinstance(column, str) or not column for column in columns)
    ):
        raise CFBDTransformError(f"{label} must be non-empty unique names")


def _require_available[FrameT: IntoDataFrame](
    frame: nw.DataFrame[FrameT],
    columns: tuple[str, ...],
) -> None:
    if not set(columns) <= set(frame.columns):
        raise CFBDTransformError("Declared columns are unavailable")


def _sort_directions(
    descending: bool | tuple[bool, ...],
    *,
    width: int,
) -> tuple[bool, ...]:
    if isinstance(descending, bool):
        return (descending,) * width
    if len(descending) != width or any(
        not isinstance(direction, bool) for direction in descending
    ):
        raise CFBDTransformError("Sort directions must match the sort keys")
    return descending


def _temporary_column(columns: list[str]) -> str:
    candidate = "__cfb_data_input_ordinal"
    while candidate in columns:
        candidate = f"_{candidate}"
    return candidate


__all__ = [
    "PortableDType",
    "rename_columns",
    "select_columns",
    "sort_rows",
    "strict_cast_columns",
]
