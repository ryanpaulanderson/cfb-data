"""Test portable flat-table operations through both supported backends."""

from __future__ import annotations

from typing import Literal

import narwhals.stable.v2 as nw
import pandas as pd
import polars as pl
import pyarrow as pa
import pytest
from cfb_data.analytics import (
    rename_columns,
    select_columns,
    sort_rows,
    strict_cast_columns,
)
from cfb_data.analytics.errors import CFBDTransformError

type NativeFrame = pd.DataFrame | pl.DataFrame
type Backend = Literal["pandas", "polars"]


def _pandas(table: pa.Table) -> pd.DataFrame:
    return table.to_pandas(types_mapper=pd.ArrowDtype)


def _materialize(table: pa.Table, backend: Backend) -> NativeFrame:
    if backend == "pandas":
        return _pandas(table)
    frame = pl.from_arrow(table)
    if not isinstance(frame, pl.DataFrame):
        raise AssertionError("Arrow table materialized as a Polars Series")
    return frame


def _arrow(frame: NativeFrame) -> pa.Table:
    portable = nw.from_native(frame, eager_only=True)
    assert isinstance(portable, nw.DataFrame)
    return portable.to_arrow().combine_chunks()


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_select_preserves_declared_order_and_backend(backend: Backend) -> None:
    source = pa.table({"id": [1, 2], "name": ["a", "b"], "score": [2.0, 1.0]})
    native = _materialize(source, backend)

    result = select_columns(native, columns=("score", "id"))

    assert type(result) is type(native)
    assert _arrow(result).equals(source.select(("score", "id")))


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_select_rejects_duplicates_and_missing_columns(backend: Backend) -> None:
    native = _materialize(pa.table({"id": [1]}), backend)

    with pytest.raises(CFBDTransformError, match="unique"):
        select_columns(native, columns=("id", "id"))
    with pytest.raises(CFBDTransformError, match="unavailable"):
        select_columns(native, columns=("missing",))


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_rename_preserves_order_and_rejects_collisions(backend: Backend) -> None:
    native = _materialize(pa.table({"id": [1], "score": [2.0]}), backend)

    result = rename_columns(native, mapping={"score": "rating"})

    assert _arrow(result).column_names == ["id", "rating"]
    with pytest.raises(CFBDTransformError, match="collide"):
        rename_columns(native, mapping={"score": "id"})


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_strict_cast_uses_equal_arrow_semantics(backend: Backend) -> None:
    native = _materialize(pa.table({"id": pa.array([1, 2], type=pa.int64())}), backend)

    result = strict_cast_columns(native, columns={"id": "float64"})

    expected = pa.table({"id": pa.array([1.0, 2.0], type=pa.float64())})
    assert _arrow(result).equals(expected)


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_strict_cast_rejects_lossy_values(backend: Backend) -> None:
    native = _materialize(pa.table({"score": [1.5]}), backend)

    with pytest.raises(CFBDTransformError, match="lose or reject"):
        strict_cast_columns(native, columns={"score": "int64"})


@pytest.mark.parametrize("backend", ("pandas", "polars"))
def test_sort_is_stable_and_places_nulls_explicitly(backend: Backend) -> None:
    source = pa.table(
        {
            "id": pa.array([1, 2, 3, 4], type=pa.int64()),
            "score": pa.array([2, None, 2, 1], type=pa.int64()),
        }
    )

    result = sort_rows(
        _materialize(source, backend),
        by=("score",),
        descending=False,
        nulls_last=True,
    )

    assert _arrow(result).column("id").to_pylist() == [4, 1, 3, 2]
