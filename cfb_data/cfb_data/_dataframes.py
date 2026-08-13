"""Materialize canonical Arrow tables as pandas or Polars DataFrames."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, TypeVar

import pandas as pd
import pyarrow as pa
from pydantic import BaseModel

from cfb_data._tabular import (
    _arrow_table_from_models,
    _assert_canonical_arrow_table,
    _logical_records_from_arrow_table,
    _logical_schema,
    _LogicalType,
)
from cfb_data.errors import (
    CFBDDataFrameConversionError,
    CFBDOptionalDependencyError,
    _sanitized_cause,
)

if TYPE_CHECKING:
    import polars as pl

_FrameT_co = TypeVar("_FrameT_co", covariant=True)


class _DataFrameAdapter(Protocol[_FrameT_co]):
    """Convert canonical tabular values to one eager DataFrame type."""

    def from_models(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        models: Sequence[BaseModel],
    ) -> _FrameT_co:
        """Return a frame preserving all validated rows and columns."""

    def from_table(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        table: pa.Table,
    ) -> _FrameT_co:
        """Return a frame materialized from a canonical Arrow table."""


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
            table = _arrow_table_from_models(row_model=row_model, models=models)
            return self.from_table(
                endpoint=endpoint,
                row_model=row_model,
                table=table,
            )
        except CFBDDataFrameConversionError:
            raise
        except Exception as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDDataFrameConversionError(
            endpoint=endpoint,
            backend="pandas",
        ) from safe_cause

    def from_table(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        table: pa.Table,
    ) -> pd.DataFrame:
        """Return a pandas frame from a canonical Arrow table.

        :param endpoint: Endpoint associated with the table.
        :param row_model: Authoritative Pydantic row model.
        :param table: Canonical Arrow table in source row order.
        :return: DataFrame with explicit pandas dtypes and nested objects.
        :raises CFBDDataFrameConversionError: If conversion loses the contract.
        """
        try:
            schema = _logical_schema(row_model)
            records = _logical_records_from_arrow_table(
                row_model=row_model,
                table=table,
            )
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
                expected_rows=table.num_rows,
            )
            if not frame.index.equals(pd.RangeIndex(table.num_rows)):
                raise ValueError("pandas conversion did not preserve a RangeIndex")
            return frame
        except CFBDDataFrameConversionError:
            raise
        except Exception as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDDataFrameConversionError(
            endpoint=endpoint,
            backend="pandas",
        ) from safe_cause


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
        self._require_polars()
        try:
            table = _arrow_table_from_models(row_model=row_model, models=models)
            return self.from_table(
                endpoint=endpoint,
                row_model=row_model,
                table=table,
            )
        except CFBDDataFrameConversionError:
            raise
        except Exception as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDDataFrameConversionError(
            endpoint=endpoint,
            backend="polars",
        ) from safe_cause

    def from_table(
        self,
        *,
        endpoint: str,
        row_model: type[BaseModel],
        table: pa.Table,
    ) -> pl.DataFrame:
        """Return a Polars frame from a canonical Arrow table.

        :param endpoint: Endpoint associated with the table.
        :param row_model: Authoritative Pydantic row model.
        :param table: Canonical Arrow table in source row order.
        :return: DataFrame with Arrow-native nesting and decoded mixed scalars.
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
            _assert_canonical_arrow_table(row_model=row_model, table=table)
            frame = pl.from_arrow(table, rechunk=True)
            if not isinstance(frame, pl.DataFrame):
                raise TypeError("Arrow table did not produce a Polars DataFrame")
            scalar_fields = [
                (index, field)
                for index, field in enumerate(schema.fields)
                if field.type.kind == "scalar"
            ]
            if scalar_fields:
                records = _logical_records_from_arrow_table(
                    row_model=row_model,
                    table=table,
                )
                for index, field in scalar_fields:
                    frame.replace_column(
                        index,
                        pl.Series(
                            field.name,
                            [record[field.name] for record in records],
                            dtype=pl.Object,
                            strict=True,
                        ),
                    )
            _assert_frame_shape(
                columns=frame.columns,
                row_count=frame.height,
                expected_columns=[field.name for field in schema.fields],
                expected_rows=table.num_rows,
            )
            return frame
        except CFBDOptionalDependencyError:
            raise
        except Exception as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDDataFrameConversionError(
            endpoint=endpoint,
            backend="polars",
        ) from safe_cause

    @staticmethod
    def _require_polars() -> None:
        """Fail with install guidance before doing backend-independent work."""
        try:
            import polars  # noqa: F401
        except ModuleNotFoundError as exc:
            if exc.name == "polars":
                raise CFBDOptionalDependencyError(
                    'Polars support requires pip install "cfb-data[polars]"'
                ) from exc
            raise


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
    if logical_type.kind in {"scalar", "struct", "list"}:
        return object
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
