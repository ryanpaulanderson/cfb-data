"""Test the canonical Arrow table and internal versioned Parquet codec."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from cfb_data._dataframes import _PandasAdapter, _PolarsAdapter
from cfb_data._parquet import _ParquetCodecError, _read_parquet, _write_parquet
from cfb_data._tabular import (
    _arrow_table_from_models,
    _expected_arrow_schema,
    _logical_records_from_arrow_table,
    _models_from_arrow_table,
)
from cfb_data.rankings.models.pydantic.responses import PollWeek
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

_STORAGE_VERSION_KEY = b"cfb_data.storage_version"
_ROW_MODEL_KEY = b"cfb_data.row_model"
_SCHEMA_DIGEST_KEY = b"cfb_data.logical_schema_sha256"
_WRITER_VERSION_KEY = b"cfb_data.writer_version"


class _NestedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    scores: list[float | None] | None


class _NestedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float | None


class _Status(StrEnum):
    active = "active"
    inactive = "inactive"


class _StorageRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    status: _Status
    occurred_at: datetime
    context: _NestedContext | None
    items: list[_NestedItem]
    stat_value: str | int | float

    @field_validator("occurred_at", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("stat_value", mode="before")
    @classmethod
    def reject_boolean_scalar(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise ValueError("stat_value must be a string or number")
        return value


class _SameShapeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    status: _Status
    occurred_at: datetime
    context: _NestedContext | None
    items: list[_NestedItem]
    stat_value: str | int | float


_ROWS = TypeAdapter(list[_StorageRow])
_SAME_SHAPE_ROWS = TypeAdapter(list[_SameShapeRow])
_POLL_WEEK_ROWS = TypeAdapter(list[PollWeek])
_GOLDEN_PATH = Path(__file__).parent / "fixtures" / "parquet" / "poll-week-v1.parquet"


def _models() -> list[_StorageRow]:
    source_zone = timezone(timedelta(hours=-4))
    return [
        _StorageRow(
            id=1,
            status=_Status.active,
            occurred_at=datetime(2024, 8, 31, 19, 30, tzinfo=source_zone),
            context=_NestedContext(label="first", scores=[1.5, None, 2.5]),
            items=[_NestedItem(name="a", value=3.5)],
            stat_value=1,
        ),
        _StorageRow(
            id=2,
            status=_Status.inactive,
            occurred_at=datetime(2024, 9, 1, 0, 0, tzinfo=UTC),
            context=None,
            items=[],
            stat_value=1.0,
        ),
        _StorageRow(
            id=3,
            status=_Status.active,
            occurred_at=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
            context=_NestedContext(label="third", scores=None),
            items=[_NestedItem(name="b", value=None)],
            stat_value="1",
        ),
    ]


def _table() -> pa.Table:
    return _arrow_table_from_models(row_model=_StorageRow, models=_models())


def _golden_poll_week() -> PollWeek:
    return PollWeek.model_validate(
        {
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "polls": [
                {
                    "poll": "AP Top 25",
                    "isFinal": False,
                    "ranks": [
                        {
                            "rank": 1,
                            "teamId": 333,
                            "school": "Alabama",
                            "conference": "SEC",
                            "firstPlaceVotes": 42,
                            "points": 1500,
                        }
                    ],
                }
            ],
        }
    )


def _replace_metadata(
    table: pa.Table,
    *,
    updates: dict[bytes, bytes] | None = None,
    remove: set[bytes] | None = None,
) -> pa.Table:
    metadata = dict(table.schema.metadata or {})
    metadata.update(updates or {})
    for key in remove or set():
        metadata.pop(key, None)
    return table.replace_schema_metadata(metadata)


def _write_unchecked(path: Path, table: pa.Table) -> None:
    pq.write_table(
        table,
        path,
        version="1.0",
        compression="snappy",
        write_statistics=True,
        use_compliant_nested_type=True,
        store_schema=True,
    )


def test_arrow_table_preserves_recursive_schema_values_and_metadata() -> None:
    table = _table()
    records = _logical_records_from_arrow_table(row_model=_StorageRow, table=table)

    assert table.schema.equals(_expected_arrow_schema(_StorageRow), check_metadata=True)
    assert table.column_names == list(_StorageRow.model_fields)
    assert table.num_rows == 3
    assert table.schema.field("id").nullable is False
    assert table.schema.field("context").nullable is True
    assert table.schema.field("items").nullable is False
    assert table.schema.field("occurred_at").type == pa.timestamp("us", tz="UTC")
    assert table.schema.field("items").type.value_field.name == "element"
    assert table.schema.metadata is not None
    assert table.schema.metadata[_STORAGE_VERSION_KEY] == b"1"
    assert table.schema.metadata[_ROW_MODEL_KEY].endswith(b":_StorageRow")
    assert len(table.schema.metadata[_SCHEMA_DIGEST_KEY]) == 64
    assert table.schema.metadata[_WRITER_VERSION_KEY]
    assert records[0]["occurred_at"] == datetime(2024, 8, 31, 23, 30, tzinfo=UTC)
    assert records[0]["context"] == {
        "label": "first",
        "scores": [1.5, None, 2.5],
    }
    assert records[1]["context"] is None
    assert records[1]["items"] == []
    assert [type(record["stat_value"]) for record in records] == [int, float, str]


def test_empty_arrow_table_retains_the_populated_physical_schema() -> None:
    populated = _table()
    empty = _arrow_table_from_models(row_model=_StorageRow, models=[])

    assert empty.num_rows == 0
    assert empty.schema.equals(populated.schema, check_metadata=True)
    assert empty.schema.field("context").type == populated.schema.field("context").type
    assert empty.schema.field("items").type == populated.schema.field("items").type
    assert (
        empty.schema.field("stat_value").type
        == populated.schema.field("stat_value").type
    )


def test_all_null_nested_column_retains_the_declared_struct_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "all-null-nested.parquet"
    models = [model.model_copy(update={"context": None}) for model in _models()]
    table = _arrow_table_from_models(row_model=_StorageRow, models=models)

    _write_parquet(path, row_model=_StorageRow, table=table)
    restored = _read_parquet(
        path,
        row_model=_StorageRow,
        response_adapter=_ROWS,
    )

    assert restored.column("context").to_pylist() == [None, None, None]
    assert restored.schema.field("context") == _table().schema.field("context")


def test_tagged_scalars_preserve_exact_python_types() -> None:
    table = _table()
    stored = table.column("stat_value").to_pylist()
    restored = _models_from_arrow_table(
        row_model=_StorageRow,
        response_adapter=_ROWS,
        table=table,
    )

    assert stored == [
        {
            "kind": "integer",
            "string_value": None,
            "integer_value": 1,
            "float_value": None,
        },
        {
            "kind": "float",
            "string_value": None,
            "integer_value": None,
            "float_value": 1.0,
        },
        {
            "kind": "string",
            "string_value": "1",
            "integer_value": None,
            "float_value": None,
        },
    ]
    assert [type(model.stat_value) for model in restored] == [int, float, str]
    assert [model.stat_value for model in restored] == [1, 1.0, "1"]


def test_model_to_arrow_rejects_boolean_heterogeneous_scalars() -> None:
    invalid = _models()[0].model_copy(update={"stat_value": True})

    with pytest.raises(TypeError, match="Heterogeneous scalar"):
        _arrow_table_from_models(row_model=_StorageRow, models=[invalid])


def test_parquet_round_trip_preserves_format_schema_and_models(tmp_path: Path) -> None:
    path = tmp_path / "nested.parquet"
    table = _table()

    _write_parquet(path, row_model=_StorageRow, table=table)
    restored = _read_parquet(
        path,
        row_model=_StorageRow,
        response_adapter=_ROWS,
    )
    restored_models = _models_from_arrow_table(
        row_model=_StorageRow,
        response_adapter=_ROWS,
        table=restored,
    )
    file_metadata = pq.read_metadata(path)

    assert restored.schema.equals(table.schema, check_metadata=True)
    assert restored_models == _models()
    assert file_metadata.format_version == "1.0"
    assert file_metadata.num_rows == 3
    assert file_metadata.row_group(0).column(0).compression == "SNAPPY"
    assert file_metadata.row_group(0).column(0).statistics is not None


def test_empty_parquet_round_trip_preserves_exact_schema(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    table = _arrow_table_from_models(row_model=_StorageRow, models=[])

    _write_parquet(path, row_model=_StorageRow, table=table)
    restored = _read_parquet(
        path,
        row_model=_StorageRow,
        response_adapter=_ROWS,
    )

    assert restored.num_rows == 0
    assert restored.schema.equals(table.schema, check_metadata=True)


def test_same_table_materializes_with_backend_native_nested_values() -> None:
    table = _table()

    pandas_frame = _PandasAdapter().from_table(
        endpoint="/storage-test",
        row_model=_StorageRow,
        table=table,
    )
    polars_frame = _PolarsAdapter().from_table(
        endpoint="/storage-test",
        row_model=_StorageRow,
        table=table,
    )

    assert isinstance(pandas_frame, pd.DataFrame)
    assert pandas_frame["context"].dtype == object
    assert pandas_frame["items"].dtype == object
    assert pandas_frame["stat_value"].dtype == object
    assert pandas_frame.loc[0, "context"]["scores"] == [1.5, None, 2.5]
    assert [type(value) for value in pandas_frame["stat_value"]] == [int, float, str]
    assert isinstance(polars_frame, pl.DataFrame)
    assert isinstance(polars_frame.schema["context"], pl.Struct)
    assert isinstance(polars_frame.schema["items"], pl.List)
    assert polars_frame.schema["stat_value"] == pl.Object
    assert polars_frame["context"][0]["scores"] == [1.5, None, 2.5]
    assert [type(value) for value in polars_frame["stat_value"]] == [int, float, str]
    assert pandas_frame.to_dict(orient="records") == polars_frame.to_dicts()


def test_full_validation_rejects_domain_invalid_data_while_trusted_accepts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "domain-invalid.parquet"
    table = _table()
    invalid = table.set_column(
        table.schema.get_field_index("id"),
        table.schema.field("id"),
        pa.array([0, 2, 3], type=pa.int64()),
    )
    _write_unchecked(path, invalid)

    with pytest.raises(_ParquetCodecError) as exc_info:
        _read_parquet(path, row_model=_StorageRow, response_adapter=_ROWS)
    trusted = _read_parquet(
        path,
        row_model=_StorageRow,
        response_adapter=_ROWS,
        validation="trusted_schema",
    )

    assert exc_info.value.operation == "read"
    assert exc_info.value.category == "validation"
    assert trusted.column("id").to_pylist() == [0, 2, 3]


def test_full_validation_rejects_invalid_enum_while_trusted_accepts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "enum-invalid.parquet"
    table = _table()
    invalid = table.set_column(
        table.schema.get_field_index("status"),
        table.schema.field("status"),
        pa.array(["unknown", "inactive", "active"], type=pa.string()),
    )
    _write_unchecked(path, invalid)

    with pytest.raises(_ParquetCodecError) as exc_info:
        _read_parquet(path, row_model=_StorageRow, response_adapter=_ROWS)
    trusted = _read_parquet(
        path,
        row_model=_StorageRow,
        response_adapter=_ROWS,
        validation="trusted_schema",
    )

    assert exc_info.value.category == "validation"
    assert trusted.column("status").to_pylist() == ["unknown", "inactive", "active"]


@pytest.mark.parametrize(
    "invalid_scalar",
    [
        {
            "kind": "unknown",
            "string_value": "1",
            "integer_value": None,
            "float_value": None,
        },
        {
            "kind": "integer",
            "string_value": "1",
            "integer_value": None,
            "float_value": None,
        },
        {
            "kind": "integer",
            "string_value": None,
            "integer_value": None,
            "float_value": None,
        },
        {
            "kind": "integer",
            "string_value": "1",
            "integer_value": 1,
            "float_value": None,
        },
    ],
)
def test_malformed_tagged_scalars_are_rejected_before_write_and_on_read(
    tmp_path: Path,
    invalid_scalar: dict[str, object],
) -> None:
    path = tmp_path / "invalid-scalar.parquet"
    table = _table()
    stored_scalars = table.column("stat_value").to_pylist()
    malformed = table.set_column(
        table.schema.get_field_index("stat_value"),
        table.schema.field("stat_value"),
        pa.array(
            [invalid_scalar, *stored_scalars[1:]],
            type=table.schema.field("stat_value").type,
        ),
    )

    with pytest.raises(_ParquetCodecError) as write_error:
        _write_parquet(path, row_model=_StorageRow, table=malformed)
    assert write_error.value.category == "format"
    assert not path.exists()

    _write_unchecked(path, malformed)
    with pytest.raises(_ParquetCodecError) as read_error:
        _read_parquet(
            path,
            row_model=_StorageRow,
            response_adapter=_ROWS,
            validation="trusted_schema",
        )
    assert read_error.value.category == "format"


@pytest.mark.parametrize(
    ("table_transform", "expected_category"),
    [
        (lambda table: table.replace_schema_metadata(None), "metadata"),
        (
            lambda table: _replace_metadata(
                table,
                updates={_STORAGE_VERSION_KEY: b"999"},
            ),
            "metadata",
        ),
        (
            lambda table: _replace_metadata(
                table,
                updates={_SCHEMA_DIGEST_KEY: b"0" * 64},
            ),
            "metadata",
        ),
        (
            lambda table: _replace_metadata(
                table,
                remove={_WRITER_VERSION_KEY},
            ),
            "metadata",
        ),
        (lambda table: table.select(list(reversed(table.column_names))), "schema"),
        (
            lambda table: table.set_column(
                table.schema.get_field_index("id"),
                pa.field("id", pa.float64(), nullable=False),
                pa.array([1.0, 2.0, 3.0], type=pa.float64()),
            ),
            "schema",
        ),
    ],
)
def test_reader_rejects_incompatible_metadata_and_physical_schemas(
    tmp_path: Path,
    table_transform: object,
    expected_category: str,
) -> None:
    path = tmp_path / "incompatible.parquet"
    assert callable(table_transform)
    transformed = table_transform(_table())
    assert isinstance(transformed, pa.Table)
    _write_unchecked(path, transformed)

    with pytest.raises(_ParquetCodecError) as exc_info:
        _read_parquet(path, row_model=_StorageRow, response_adapter=_ROWS)

    assert exc_info.value.category == expected_category


def test_reader_rejects_an_unexpected_same_shape_row_model(tmp_path: Path) -> None:
    path = tmp_path / "wrong-model.parquet"
    _write_unchecked(path, _table())

    with pytest.raises(_ParquetCodecError) as exc_info:
        _read_parquet(
            path,
            row_model=_SameShapeRow,
            response_adapter=_SAME_SHAPE_ROWS,
        )

    assert exc_info.value.category == "metadata"


def test_atomic_write_preserves_existing_target_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "atomic.parquet"
    original = b"existing-target"
    path.write_bytes(original)

    def fail_write(*args: object, **kwargs: object) -> None:
        raise RuntimeError("source failure containing sensitive values")

    monkeypatch.setattr("cfb_data._parquet.pq.write_table", fail_write)
    with pytest.raises(_ParquetCodecError) as exc_info:
        _write_parquet(path, row_model=_StorageRow, table=_table())

    assert path.read_bytes() == original
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))
    assert exc_info.value.operation == "write"
    assert exc_info.value.category == "format"
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is not None
    assert str(exc_info.value.__cause__) == "RuntimeError"
    assert "sensitive" not in str(exc_info.value.__cause__)


def test_failed_atomic_replacement_preserves_target_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "replace-failure.parquet"
    original = b"existing-target"
    path.write_bytes(original)

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("replacement failure with unsafe paths")

    monkeypatch.setattr("cfb_data._parquet.os.replace", fail_replace)
    with pytest.raises(_ParquetCodecError) as exc_info:
        _write_parquet(path, row_model=_StorageRow, table=_table())

    assert path.read_bytes() == original
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))
    assert exc_info.value.category == "io"
    assert str(exc_info.value.__cause__) == "OSError"


def test_codec_reports_missing_parent_and_corrupt_file_without_paths(
    tmp_path: Path,
) -> None:
    missing_target = tmp_path / "missing" / "target.parquet"
    with pytest.raises(_ParquetCodecError) as write_error:
        _write_parquet(missing_target, row_model=_StorageRow, table=_table())

    corrupt_path = tmp_path / "corrupt.parquet"
    corrupt_path.write_bytes(b"not a parquet file")
    with pytest.raises(_ParquetCodecError) as read_error:
        _read_parquet(
            corrupt_path,
            row_model=_StorageRow,
            response_adapter=_ROWS,
        )

    assert write_error.value.category == "io"
    assert read_error.value.category == "format"
    for error in (write_error.value, read_error.value):
        assert error.__context__ is None
        assert error.__cause__ is not None
        assert str(tmp_path) not in str(error)
        assert str(tmp_path) not in str(error.__cause__)


def test_reader_rejects_a_truncated_parquet_file(tmp_path: Path) -> None:
    path = tmp_path / "truncated.parquet"
    _write_parquet(path, row_model=_StorageRow, table=_table())
    complete = path.read_bytes()
    path.write_bytes(complete[: len(complete) // 2])

    with pytest.raises(_ParquetCodecError) as exc_info:
        _read_parquet(path, row_model=_StorageRow, response_adapter=_ROWS)

    assert exc_info.value.category == "format"
    assert str(tmp_path) not in str(exc_info.value)
    assert str(tmp_path) not in str(exc_info.value.__cause__)


def test_reader_rejects_unknown_validation_mode_before_io(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="validation must be"):
        _read_parquet(
            tmp_path / "does-not-exist.parquet",
            row_model=_StorageRow,
            response_adapter=_ROWS,
            validation="unknown",  # type: ignore[arg-type]
        )


def test_checked_in_version_one_fixture_remains_readable() -> None:
    restored = _read_parquet(
        _GOLDEN_PATH,
        row_model=PollWeek,
        response_adapter=_POLL_WEEK_ROWS,
    )
    models = _models_from_arrow_table(
        row_model=PollWeek,
        response_adapter=_POLL_WEEK_ROWS,
        table=restored,
    )

    assert models == [_golden_poll_week()]
    assert restored.schema.equals(_expected_arrow_schema(PollWeek))
