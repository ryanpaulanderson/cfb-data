"""Validate and encode bounded native dataframe execution results."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import GenericAlias
from typing import Protocol, cast

import numpy as np
import pandas as pd
import pyarrow as pa
from pydantic import BaseModel, TypeAdapter

from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _AnalyticsTableIdentity,
)

from .errors import CFBDTransformError
from .tables import Table


class _Computable(Protocol):
    """Type a verified native collection's local computation boundary."""

    def compute(self, *, scheduler: str) -> object: ...

    def to_delayed(self, *, optimize_graph: bool = False) -> object: ...


class _ComputeGraphs(Protocol):
    """Confine Dask's variadic untyped computation boundary."""

    def __call__(
        self, *graphs: object, scheduler: str, optimize_graph: bool
    ) -> tuple[object, ...]: ...


class _SummaryFromPandas(Protocol):
    """Confine Dask's untyped eager-summary construction boundary."""

    def __call__(
        self, frame: pd.DataFrame, *, npartitions: int, sort: bool
    ) -> object: ...


class _ConcatSummaries(Protocol):
    """Confine Dask's untyped shared-summary concatenation boundary."""

    def __call__(
        self, frames: Sequence[object], *, ignore_unknown_divisions: bool
    ) -> object: ...


def _validation_tasks(table: Table) -> tuple[object, ...]:
    """Lower shared global reductions once without repeated dataframe fusion."""
    from dask.dataframe import DataFrame, concat, from_pandas

    summaries: list[DataFrame] = []
    summary_indices: list[int] = []
    by_name: dict[str, int] = {}
    for check in table._checks:
        native = check.frame.to_native()
        if isinstance(native, DataFrame):
            if native.npartitions != 1:
                raise CFBDTransformError(
                    "Global check must produce one summary partition"
                )
        elif isinstance(native, pd.DataFrame):
            converted = cast(_SummaryFromPandas, from_pandas)(
                native, npartitions=1, sort=False
            )
            if not isinstance(converted, DataFrame):
                raise CFBDTransformError("Global summary did not produce a dataframe")
            native = converted
        else:
            raise CFBDTransformError("Global check did not return a native dataframe")
        name: object = native._name
        if not isinstance(name, str):
            raise CFBDTransformError("Global summary has an invalid graph identity")
        index = by_name.get(name)
        if index is None:
            index = len(summaries)
            by_name[name] = index
            summaries.append(native)
        summary_indices.append(index)
    if not summaries:
        return ()
    # Concatenation retains one partition per contract in declaration order.
    # Lowering this shared expression once lets Dask reuse common subgraphs.
    combined = cast(_ConcatSummaries, concat)(summaries, ignore_unknown_divisions=True)
    if not isinstance(combined, DataFrame):
        raise CFBDTransformError("Combined validation did not produce a dataframe")
    parts = cast(_Computable, combined).to_delayed(optimize_graph=False)
    if not isinstance(parts, list) or len(parts) != len(summaries):
        raise CFBDTransformError("Global validation changed its summary partitions")
    return tuple(parts[index] for index in summary_indices)


def _validate_local_checks(table: Table) -> None:
    """Evaluate shared physical check graphs together before publication."""
    from dask.base import compute

    summaries = cast(_ComputeGraphs, compute)(
        *_validation_tasks(table), scheduler="threads", optimize_graph=False
    )
    for check, result in zip(table._checks, summaries, strict=True):
        if not isinstance(result, pd.DataFrame):
            raise CFBDTransformError("Global check did not return a pandas summary")
        _check_frame(result, check.message)


@dataclass(frozen=True, slots=True)
class _EncodedPartition:
    """Return one validated bounded partition with redacted execution evidence."""

    table: pa.Table
    worker_pid: int
    duration_seconds: float


def _encode_partition(
    frame: pd.DataFrame,
    row_model: type[BaseModel],
    identity: _AnalyticsTableIdentity,
    transfer_limit_bytes: int,
) -> _EncodedPartition:
    """Validate one pandas partition and encode its canonical logical values."""
    started = time.monotonic()
    expected = tuple(row_model.model_fields)
    if tuple(frame.columns) != expected:
        raise CFBDTransformError("Table columns differ from the declared row contract")
    raw: object = frame.to_dict(orient="records")
    cleaned = _logical_value(raw)
    adapter = cast(
        TypeAdapter[list[BaseModel]], TypeAdapter(GenericAlias(list, row_model))
    )
    rows = adapter.validate_python(cleaned)
    table = _analytics_arrow_table_from_models(
        row_model=row_model,
        models=rows,
        identity=identity,
    )
    if table.nbytes > transfer_limit_bytes:
        raise CFBDTransformError("Native partition exceeds the transfer byte limit")
    return _EncodedPartition(table, os.getpid(), time.monotonic() - started)


def _logical_value(value: object) -> object:
    """Normalize pandas missing/scalar representations at the schema boundary."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.ndarray):
        return _logical_value(value.tolist())
    if isinstance(value, np.generic):
        return _logical_value(value.item())
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CFBDTransformError("Table struct contains non-string field names")
        return {key: _logical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_logical_value(item) for item in value]
    return value


def _check_frame(frame: pd.DataFrame, message: str) -> None:
    """Require one bounded zero-violation summary from a global reduction."""
    if list(frame.columns) != ["invalid_count"] or len(frame) != 1:
        raise CFBDTransformError("Global validation returned an invalid summary")
    invalid: object = frame.iloc[0, 0]
    if not isinstance(invalid, (int, np.integer)) or int(invalid) != 0:
        raise CFBDTransformError(message)


def _local_native_parts(
    table: Table,
    row_model: type[BaseModel],
    identity: _AnalyticsTableIdentity,
    transfer_limit_bytes: int,
) -> Iterator[_EncodedPartition]:
    """Compute checked native partitions through Dask's local scheduler."""
    from dask.dataframe import DataFrame
    from dask.delayed import Delayed, delayed

    _validate_local_checks(table)
    native = table.frame.to_native()
    if isinstance(native, pd.DataFrame):
        yield _encode_partition(native, row_model, identity, transfer_limit_bytes)
        return
    if not isinstance(native, DataFrame):
        raise CFBDTransformError("Native execution requires a dataframe")
    delayed_parts: object = cast(_Computable, native).to_delayed(optimize_graph=False)
    if not isinstance(delayed_parts, list):
        raise CFBDTransformError("Dask partition graph is invalid")
    for part in delayed_parts:
        encoded = delayed(_encode_partition)(
            part,
            row_model,
            identity,
            transfer_limit_bytes,
        )
        if not isinstance(encoded, Delayed):
            raise CFBDTransformError("Native encoding did not create a delayed task")
        result = cast(_Computable, encoded).compute(scheduler="threads")
        if not isinstance(result, _EncodedPartition):
            raise CFBDTransformError("Native worker returned an invalid partition")
        yield result


def _next_partition(iterator: Iterator[_EncodedPartition]) -> _EncodedPartition | None:
    """Advance a native partition iterator without crossing StopIteration into asyncio."""
    return next(iterator, None)


__all__: tuple[str, ...] = ()
