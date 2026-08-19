"""Test stable analytics-v2 Arrow table identity and validation."""

from __future__ import annotations

import pyarrow as pa
import pytest
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _analytics_expected_arrow_schema,
    _analytics_logical_records_from_arrow_table,
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
    _CanonicalTableMetadataError,
    _CanonicalTableSchemaError,
)
from pydantic import BaseModel, ConfigDict, TypeAdapter

_STORAGE_VERSION_KEY = b"cfb_data.storage_version"
_ROW_MODEL_KEY = b"cfb_data.row_model"
_OUTPUT_ID_KEY = b"cfb_data.analytics.output_id"
_OUTPUT_REVISION_KEY = b"cfb_data.analytics.output_revision"
_SCHEMA_DIGEST_KEY = b"cfb_data.logical_schema_sha256"


class _OriginalGameRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    score: int | None


class _RelocatedGameRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    score: int | None


class _DifferentGameRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    points: int | None


_IDENTITY = _AnalyticsTableIdentity(output_id="cfbd.game_summaries", revision=1)
_RELOCATED_ROWS = TypeAdapter(list[_RelocatedGameRow])


def _table() -> pa.Table:
    return _analytics_arrow_table_from_models(
        row_model=_OriginalGameRow,
        models=[_OriginalGameRow(game_id=1, score=28)],
        identity=_IDENTITY,
    )


def test_analytics_table_uses_stable_output_identity() -> None:
    table = _table()
    metadata = table.schema.metadata

    assert metadata is not None
    assert metadata[_STORAGE_VERSION_KEY] == b"2"
    assert metadata[_OUTPUT_ID_KEY] == b"cfbd.game_summaries"
    assert metadata[_OUTPUT_REVISION_KEY] == b"1"
    assert len(metadata[_SCHEMA_DIGEST_KEY]) == 64
    assert _ROW_MODEL_KEY not in metadata


def test_model_relocation_does_not_change_analytics_compatibility() -> None:
    original = _table()
    relocated = _analytics_arrow_table_from_models(
        row_model=_RelocatedGameRow,
        models=[_RelocatedGameRow(game_id=1, score=28)],
        identity=_IDENTITY,
    )
    restored = _analytics_models_from_arrow_table(
        row_model=_RelocatedGameRow,
        response_adapter=_RELOCATED_ROWS,
        table=original,
        identity=_IDENTITY,
    )

    assert original.schema.equals(relocated.schema, check_metadata=True)
    assert original.to_pylist() == relocated.to_pylist()
    assert restored == [_RelocatedGameRow(game_id=1, score=28)]


def test_analytics_table_rejects_wrong_output_identity() -> None:
    with pytest.raises(_CanonicalTableMetadataError, match="incompatible"):
        _analytics_logical_records_from_arrow_table(
            row_model=_OriginalGameRow,
            table=_table(),
            identity=_AnalyticsTableIdentity(
                output_id="cfbd.team_games",
                revision=1,
            ),
        )


def test_analytics_table_rejects_wrong_output_revision() -> None:
    with pytest.raises(_CanonicalTableMetadataError, match="incompatible"):
        _analytics_logical_records_from_arrow_table(
            row_model=_OriginalGameRow,
            table=_table(),
            identity=_AnalyticsTableIdentity(
                output_id="cfbd.game_summaries",
                revision=2,
            ),
        )


def test_analytics_table_rejects_wrong_logical_schema() -> None:
    with pytest.raises(_CanonicalTableSchemaError, match="physical schema"):
        _analytics_logical_records_from_arrow_table(
            row_model=_DifferentGameRow,
            table=_table(),
            identity=_IDENTITY,
        )


def test_empty_analytics_table_preserves_the_declared_schema() -> None:
    table = _analytics_arrow_table_from_models(
        row_model=_OriginalGameRow,
        models=[],
        identity=_IDENTITY,
    )

    assert table.num_rows == 0
    assert table.schema.equals(
        _analytics_expected_arrow_schema(
            _OriginalGameRow,
            identity=_IDENTITY,
        ),
        check_metadata=True,
    )


@pytest.mark.parametrize(
    ("output_id", "revision", "error_type"),
    [
        ("unqualified", 1, ValueError),
        ("cfbd.games", 0, ValueError),
        ("cfbd.games", True, TypeError),
    ],
)
def test_analytics_table_identity_rejects_invalid_values(
    output_id: str,
    revision: int,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        _AnalyticsTableIdentity(output_id=output_id, revision=revision)
