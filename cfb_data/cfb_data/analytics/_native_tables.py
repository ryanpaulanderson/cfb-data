"""Adapt native dataframe partitions at typed structural boundaries.

Dask and pandas expose dynamically typed expression and partition methods.
This module confines that boundary and immediately verifies native frame
types. Public recipe code uses the typed Narwhals interface and ``Table``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Protocol, cast

import narwhals.stable.v2 as nw
import pandas as pd
from narwhals.stable.v2.typing import IntoLazyFrame

from .errors import CFBDTransformError
from .tables import PartitionFunction, Table


class _NativePartitionFrame(Protocol):
    """Type the verified Dask dynamic methods used only at this boundary."""

    def compute(self, *, scheduler: str) -> object: ...

    def assign(self, **columns: object) -> object: ...

    def map_partitions(
        self,
        function: Callable[..., pd.DataFrame],
        *args: object,
        meta: pd.DataFrame,
        clear_divisions: bool,
    ) -> object: ...


def _require_lazy(value: object) -> nw.LazyFrame[IntoLazyFrame]:
    """Narrow one native adapter result to the public lazy interface."""
    if not isinstance(value, nw.LazyFrame):
        raise TypeError("Native table operation did not return a lazy frame")
    return cast(nw.LazyFrame[IntoLazyFrame], value)


def _pandas_meta(frame: nw.LazyFrame[IntoLazyFrame]) -> pd.DataFrame:
    """Return typed empty metadata without evaluating a dataframe graph."""
    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        return native.iloc[:0].copy()
    from dask.dataframe import DataFrame

    if not isinstance(native, DataFrame):
        raise TypeError("Native tables require pandas or Dask DataFrames")
    meta: object = native._meta
    if not isinstance(meta, pd.DataFrame):
        raise TypeError("Dask table metadata is not a pandas DataFrame")
    return meta.copy()


def _map_partitions(
    frame: nw.LazyFrame[IntoLazyFrame],
    function: PartitionFunction,
    meta: pd.DataFrame,
) -> nw.LazyFrame[IntoLazyFrame]:
    """Map a bounded structural kernel without sampling it for metadata."""
    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        return _require_lazy(nw.from_native(function(native)).lazy())
    from dask.dataframe import DataFrame

    if not isinstance(native, DataFrame):
        raise TypeError("Native tables require pandas or Dask DataFrames")
    result = cast(_NativePartitionFrame, native).map_partitions(
        function, meta=meta, clear_divisions=True
    )
    if not isinstance(result, DataFrame):
        raise TypeError("Partition mapping changed the native dataframe type")
    return _require_lazy(nw.from_native(result))


def _normalization_kernel(column: str, into: str) -> PartitionFunction:
    """Bind exact whitespace and casefold normalization for one partition."""

    def normalize(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result[into] = (
            frame[column]
            .astype("string")
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .str.casefold()
        )
        return result

    return normalize


def _nested_kernel(
    column: str, fields: dict[str, str], dtypes: dict[str, str]
) -> PartitionFunction:
    """Bind a partition-local struct projection using pandas accessors."""

    def project(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        source = frame[column].astype(object)
        for field, target in fields.items():
            result[target] = source.str.get(field)
            if target in dtypes:
                result[target] = result[target].astype(dtypes[target])
        return result

    return project


def _pack_kernel(columns: dict[str, str], into: str) -> PartitionFunction:
    """Bind a bounded native record projection for nested presentation."""

    def pack(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        nested = frame[list(columns)].rename(columns=columns)
        result[into] = pd.Series(
            nested.to_dict(orient="records"), index=frame.index, dtype=object
        )
        return result

    return pack


def _explode_kernel(
    column: str,
    fields: dict[str, str],
    ordinal: str,
    dtypes: dict[str, str],
) -> PartitionFunction:
    """Bind native structural explosion while retaining original positions."""

    def explode(frame: pd.DataFrame) -> pd.DataFrame:
        parent = "__cfb_structural_parent"
        if parent in frame.columns:
            raise CFBDTransformError("Structural parent column collides")
        result = frame.copy()
        result[parent] = range(len(result))
        result = result.loc[result[column].astype(object).str.len().fillna(0) > 0]
        result = result.explode(column, ignore_index=True)
        result[ordinal] = result.groupby(parent, sort=False).cumcount()
        source = result[column].astype(object)
        for field, target in fields.items():
            result[target] = source.str.get(field)
            if target in dtypes:
                result[target] = result[target].astype(dtypes[target])
        return result.drop(columns=[column, parent])

    return explode


def _ordered_records(
    frame: nw.LazyFrame[IntoLazyFrame],
    keys: tuple[str, ...],
    column: str,
    into: str,
    ordinal_field: str,
    max_group_rows: int,
    keep_ordinal: bool,
) -> nw.LazyFrame[IntoLazyFrame]:
    """Use native list aggregation then bound and order each nested group."""
    if max_group_rows < 1:
        raise ValueError("Nested group row limit must be positive")
    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        grouped = native.groupby(list(keys), dropna=False)[column].agg(list)
        result = grouped.rename(into).reset_index()
        return _require_lazy(
            nw.from_native(
                _sort_nested_records(
                    result, into, ordinal_field, max_group_rows, keep_ordinal
                )
            ).lazy()
        )
    from dask.dataframe import DataFrame

    if not isinstance(native, DataFrame):
        raise TypeError("Native tables require pandas or Dask DataFrames")
    grouped = native.groupby(list(keys), dropna=False)[column].agg(list, split_out=True)
    result = grouped.rename(into).reset_index()
    meta: object = result._meta
    if not isinstance(meta, pd.DataFrame):
        raise TypeError("Grouped metadata is not a pandas frame")
    ordered = cast(_NativePartitionFrame, result).map_partitions(
        _sort_nested_records,
        into,
        ordinal_field,
        max_group_rows,
        keep_ordinal,
        meta=meta,
        clear_divisions=True,
    )
    if not isinstance(ordered, DataFrame):
        raise TypeError("Nested aggregation changed the native dataframe type")
    return _require_lazy(nw.from_native(ordered))


def _sort_nested_records(
    frame: pd.DataFrame,
    column: str,
    ordinal_field: str,
    max_group_rows: int,
    keep_ordinal: bool,
) -> pd.DataFrame:
    """Order one already-grouped bounded struct list by its source evidence."""

    def order(value: object) -> list[dict[str, object]]:
        if not isinstance(value, list) or len(value) > max_group_rows:
            raise CFBDTransformError("Nested group violates its record bound")
        records: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, dict) or not all(isinstance(k, str) for k in item):
                raise CFBDTransformError("Nested aggregate contains an invalid struct")
            record = cast(dict[str, object], item)
            position = record.get(ordinal_field)
            if not isinstance(position, int) or isinstance(position, bool):
                raise CFBDTransformError("Nested aggregate lacks an integer ordinal")
            records.append(record)
        ordered = sorted(records, key=partial(_record_ordinal, field=ordinal_field))
        return (
            ordered
            if keep_ordinal
            else [
                {key: item for key, item in record.items() if key != ordinal_field}
                for record in ordered
            ]
        )

    result = frame.copy()
    result[column] = result[column].map(order)
    return result


def _record_ordinal(record: Mapping[str, object], *, field: str) -> int:
    value = record[field]
    if not isinstance(value, int) or isinstance(value, bool):
        raise CFBDTransformError("Nested record ordinal is invalid")
    return value


def _fill_lists(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Retain unmatched nested aggregates as explicitly empty lists."""
    result = frame.copy()
    for column in columns:
        missing = result[column].isna()
        result.loc[missing, column] = pd.Series(
            [[] for _ in range(int(missing.sum()))],
            index=result.index[missing],
            dtype=object,
        )
    return result


def _list_lengths(frame: pd.DataFrame, *, columns: dict[str, str]) -> pd.DataFrame:
    """Project cardinalities without iterating over list observations."""
    result = frame.copy()
    for source, target in columns.items():
        result[target] = frame[source].str.len().astype("Int64")
    return result


def _collect_table(table: Table) -> pd.DataFrame:
    """Collect explicit native results after validating global summaries."""
    from dask.dataframe import DataFrame

    from ._native_execution import _validate_local_checks

    _validate_local_checks(table)
    native = table.frame.to_native()
    result = (
        cast(_NativePartitionFrame, native).compute(scheduler="threads")
        if isinstance(native, DataFrame)
        else native
    )
    if not isinstance(result, pd.DataFrame):
        raise CFBDTransformError("Native table did not return a pandas frame")
    return result.reset_index(drop=True)


class _GroupCounter(Protocol):
    """Type the native distributed cumulative-count result boundary."""

    def cumcount(self) -> object: ...


def _with_group_index(
    frame: nw.LazyFrame[IntoLazyFrame], keys: tuple[str, ...], name: str
) -> nw.LazyFrame[IntoLazyFrame]:
    """Assign Dask's cross-partition group counters without gathering groups."""
    from dask.dataframe import DataFrame

    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        return _require_lazy(
            nw.from_native(
                native.assign(
                    **{name: native.groupby(list(keys), dropna=False).cumcount()}
                )
            ).lazy()
        )
    if not isinstance(native, DataFrame):
        raise CFBDTransformError("Group indexing requires a native dataframe")
    counter = cast(_GroupCounter, native.groupby(list(keys), dropna=False)).cumcount()
    result = cast(_NativePartitionFrame, native).assign(**{name: counter})
    if not isinstance(result, DataFrame):
        raise CFBDTransformError("Group indexing changed the dataframe type")
    return _require_lazy(nw.from_native(result))


def _with_row_index(
    frame: nw.LazyFrame[IntoLazyFrame], name: str
) -> nw.LazyFrame[IntoLazyFrame]:
    """Build prefix-offset metadata tasks and native partition assignments."""
    import dask
    import dask.dataframe as dd
    from dask.delayed import Delayed, delayed

    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        return _require_lazy(nw.from_native(_index_partition(native, 0, name)).lazy())
    if not isinstance(native, dd.DataFrame):
        raise CFBDTransformError("Indexing requires a native dataframe")
    meta = _pandas_meta(frame)
    meta[name] = pd.Series(dtype="int64")
    parts = cast(_PartitionGraph, native).to_delayed(optimize_graph=False)
    if not isinstance(parts, list):
        raise CFBDTransformError("Native partition graph is invalid")
    offset: object = 0
    indexed: list[Delayed] = []
    for part in parts:
        indexed.append(delayed(_index_partition)(part, offset, name))
        offset = delayed(_add_lengths)(offset, delayed(len)(part))
    with dask.config.set({"dataframe.convert-string": False}):
        result = dd.from_delayed(indexed, meta=meta)
    return _require_lazy(nw.from_native(result))


class _PartitionGraph(Protocol):
    """Type the verified native delayed partition graph boundary."""

    def to_delayed(self, *, optimize_graph: bool = False) -> object: ...


def _index_partition(frame: pd.DataFrame, offset: int, name: str) -> pd.DataFrame:
    """Assign an integer range in one partition from a computed prefix offset."""
    result = frame.copy()
    result[name] = range(offset, offset + len(result))
    return result


def _add_lengths(left: int, right: int) -> int:
    """Combine partition metadata without gathering any table rows."""
    return left + right


def _explode_values_kernel(column: str, into: str, ordinal: str) -> PartitionFunction:
    """Bind native scalar-list explosion without fabricated empty observations."""

    def explode(frame: pd.DataFrame) -> pd.DataFrame:
        parent = "__cfb_structural_parent"
        if parent in frame.columns:
            raise CFBDTransformError("Structural parent column collides")
        result = frame.copy()
        result[parent] = range(len(result))
        result = result.loc[
            result[column].astype(object).str.len().fillna(0) > 0
        ].explode(column, ignore_index=True)
        positions = result.groupby(parent, sort=False).cumcount()
        values = result[column]
        result = result.drop(columns=[column, parent])
        result[into] = values
        result[ordinal] = positions
        return result

    return explode


def _ordered_values(
    frame: nw.LazyFrame[IntoLazyFrame],
    keys: tuple[str, ...],
    column: str,
    into: str,
    limit: int,
) -> nw.LazyFrame[IntoLazyFrame]:
    """Use native grouping and bounded ordering for scalar identity evidence."""
    from dask.dataframe import DataFrame

    native = frame.to_native()
    if isinstance(native, pd.DataFrame):
        result = (
            native.groupby(list(keys), dropna=False)[column]
            .agg(list)
            .rename(into)
            .reset_index()
        )
        return _require_lazy(
            nw.from_native(_sort_scalar_lists(result, into, limit)).lazy()
        )
    if not isinstance(native, DataFrame):
        raise CFBDTransformError("Scalar aggregation requires a native dataframe")
    grouped = (
        native.groupby(list(keys), dropna=False)[column]
        .agg(list, split_out=True)
        .rename(into)
        .reset_index()
    )
    meta: object = grouped._meta
    if not isinstance(meta, pd.DataFrame):
        raise CFBDTransformError("Grouped metadata is invalid")
    result = cast(_NativePartitionFrame, grouped).map_partitions(
        _sort_scalar_lists, into, limit, meta=meta, clear_divisions=True
    )
    if not isinstance(result, DataFrame):
        raise CFBDTransformError("Scalar aggregation changed dataframe type")
    return _require_lazy(nw.from_native(result))


def _sort_scalar_lists(frame: pd.DataFrame, column: str, limit: int) -> pd.DataFrame:
    """Order one already-grouped bounded scalar evidence list."""
    from numbers import Integral

    def order(value: object) -> list[int]:
        if (
            not isinstance(value, list)
            or len(value) > limit
            or not all(
                isinstance(item, Integral) and not isinstance(item, bool)
                for item in value
            )
        ):
            raise CFBDTransformError("Identity candidate evidence is invalid")
        return sorted(int(item) for item in value)

    result = frame.copy()
    result[column] = result[column].map(order)
    return result


__all__: tuple[str, ...] = ()
