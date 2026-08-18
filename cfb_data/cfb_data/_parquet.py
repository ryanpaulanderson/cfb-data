"""Persist canonical tabular responses as versioned local Parquet files."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Final, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._tabular import (
    _arrow_table_from_models,
    _assert_canonical_arrow_table,
    _CanonicalTableMetadataError,
    _CanonicalTableSchemaError,
    _logical_records_from_arrow_table,
    _models_from_arrow_table,
    _ScalarEncodingError,
    _UnsupportedTableAnnotationError,
)
from cfb_data.errors import CFBDError

_ParquetOperation = Literal["read", "write"]
_ParquetErrorCategory = Literal[
    "io",
    "format",
    "metadata",
    "schema",
    "validation",
]
_ParquetValidation = Literal["full", "trusted_schema"]

_PARQUET_VERSION: Final = "1.0"
_PARQUET_COMPRESSION: Final = "snappy"


class _ParquetCodecError(CFBDError):
    """Report a categorized failure in the internal Parquet codec."""

    operation: _ParquetOperation
    category: _ParquetErrorCategory

    def __init__(
        self,
        *,
        operation: _ParquetOperation,
        category: _ParquetErrorCategory,
    ) -> None:
        """Initialize a categorized codec failure.

        :param operation: File operation that failed.
        :param category: Failure classification for internal policy.
        """
        self.operation = operation
        self.category = category
        super().__init__(f"Parquet {operation} failed ({category})")


def _write_parquet(
    path: str | os.PathLike[str],
    *,
    row_model: type[BaseModel],
    table: pa.Table,
) -> None:
    """Atomically write a canonical Arrow table to one local Parquet file.

    The destination parent must already exist. An existing destination is
    replaced only after the complete temporary Parquet file closes successfully.

    :param path: Local destination path.
    :param row_model: Expected authoritative row model for the table.
    :param table: Canonical Arrow table to persist.
    :raises _ParquetCodecError: If validation, writing, or replacement fails.
    """
    try:
        _write_parquet_file(Path(path), row_model=row_model, table=table)
        return
    except Exception as exc:
        raise _ParquetCodecError(
            operation="write",
            category=_codec_error_category(exc),
        ) from exc


def _read_parquet[ModelT: BaseModel](
    path: str | os.PathLike[str],
    *,
    row_model: type[ModelT],
    response_adapter: TypeAdapter[list[ModelT]],
    validation: _ParquetValidation = "full",
) -> pa.Table:
    """Read and verify one versioned cfb-data Parquet file.

    ``full`` validation decodes and revalidates every row through Pydantic.
    ``trusted_schema`` is an internal fast path only for integrity-controlled
    library caches; it still checks all metadata, Arrow types, and tagged scalar
    invariants.

    :param path: Local source path.
    :param row_model: Expected authoritative row model.
    :param response_adapter: Pydantic adapter for a list of expected rows.
    :param validation: Full domain validation or trusted schema validation.
    :return: Verified canonical Arrow table in stored row order.
    :raises ValueError: If ``validation`` is not a supported literal.
    :raises _ParquetCodecError: If reading or verification fails.
    """
    if validation not in {"full", "trusted_schema"}:
        raise ValueError("validation must be 'full' or 'trusted_schema'")
    try:
        table = _read_parquet_file(
            Path(path),
            row_model=row_model,
            response_adapter=response_adapter,
            validation=validation,
        )
        return table
    except Exception as exc:
        raise _ParquetCodecError(
            operation="read",
            category=_codec_error_category(exc),
        ) from exc


def _write_parquet_file(
    path: Path,
    *,
    row_model: type[BaseModel],
    table: pa.Table,
) -> None:
    """Validate and atomically replace a local Parquet destination."""
    _assert_canonical_arrow_table(row_model=row_model, table=table)
    _logical_records_from_arrow_table(row_model=row_model, table=table)
    if not path.parent.is_dir():
        raise FileNotFoundError("Parquet destination parent does not exist")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            pq.write_table(
                table,
                temporary_file,
                version=_PARQUET_VERSION,
                compression=_PARQUET_COMPRESSION,
                write_statistics=True,
                use_compliant_nested_type=True,
                store_schema=True,
            )
        os.replace(temporary_path, path)
    finally:
        with suppress(FileNotFoundError):
            temporary_path.unlink()


def _read_parquet_file[ModelT: BaseModel](
    path: Path,
    *,
    row_model: type[ModelT],
    response_adapter: TypeAdapter[list[ModelT]],
    validation: _ParquetValidation,
) -> pa.Table:
    """Read a table and apply the selected internal validation policy."""
    table = pq.read_table(path)
    _assert_canonical_arrow_table(row_model=row_model, table=table)
    if validation == "trusted_schema":
        _logical_records_from_arrow_table(row_model=row_model, table=table)
        return table

    models = _models_from_arrow_table(
        row_model=row_model,
        response_adapter=response_adapter,
        table=table,
    )
    return _arrow_table_from_models(row_model=row_model, models=models)


def _codec_error_category(source: Exception) -> _ParquetErrorCategory:
    """Classify a source exception for internal recovery policy."""
    if isinstance(source, _CanonicalTableMetadataError):
        return "metadata"
    if isinstance(source, _CanonicalTableSchemaError):
        return "schema"
    if isinstance(source, _UnsupportedTableAnnotationError):
        return "schema"
    if isinstance(source, ValidationError):
        return "validation"
    if isinstance(source, OSError):
        return "io"
    if isinstance(source, _ScalarEncodingError):
        return "format"
    return "format"
