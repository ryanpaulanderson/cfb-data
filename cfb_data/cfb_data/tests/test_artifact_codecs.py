"""Test deterministic validating analytics artifact codecs."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _AnalyticsTableIdentity,
)
from cfb_data.analytics._artifacts import (
    _canonical_json_bytes,
    _JsonArtifactCodec,
    _read_manifest,
    _TableArtifactCodec,
)
from cfb_data.analytics.errors import (
    CFBDArtifactCodecError,
    CFBDArtifactCorruptionError,
)
from pydantic import BaseModel, ConfigDict, TypeAdapter


class _TableRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    score: int | None
    tags: list[str]


class _ControlValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    count: int
    ratio: float | None = None


class _OtherControlValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


_IDENTITY = _AnalyticsTableIdentity(output_id="cfbd.test_output", revision=1)
_CONTROL = TypeAdapter(_ControlValue)
_OTHER_CONTROL = TypeAdapter(_OtherControlValue)


def _table(row_count: int = 3) -> pa.Table:
    return _analytics_arrow_table_from_models(
        row_model=_TableRow,
        models=[
            _TableRow(game_id=index, score=index * 7, tags=[str(index)])
            for index in range(row_count)
        ],
        identity=_IDENTITY,
    )


def test_table_codec_round_trips_deterministic_multipart_content(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    codec = _TableArtifactCodec(max_rows_per_part=2)

    first_staged = codec.stage(
        directory=first,
        table=_table(),
        row_model=_TableRow,
        identity=_IDENTITY,
    )
    second_staged = codec.stage(
        directory=second,
        table=_table(),
        row_model=_TableRow,
        identity=_IDENTITY,
    )
    restored = codec.load(
        directory=first,
        manifest=None,
        row_model=_TableRow,
        identity=_IDENTITY,
    )

    assert [part.name for part in first_staged.manifest.body.parts] == [
        "part-00000.parquet",
        "part-00001.parquet",
    ]
    assert first_staged.manifest == second_staged.manifest
    assert (first / "manifest.json").read_bytes() == (
        second / "manifest.json"
    ).read_bytes()
    assert restored.to_pylist() == _table().to_pylist()


def test_table_codec_preserves_empty_schema(tmp_path: Path) -> None:
    directory = tmp_path / "empty"
    directory.mkdir()
    codec = _TableArtifactCodec(max_rows_per_part=2)

    staged = codec.stage(
        directory=directory,
        table=_table(row_count=0),
        row_model=_TableRow,
        identity=_IDENTITY,
    )
    restored = codec.load(
        directory=directory,
        manifest=staged.manifest,
        row_model=_TableRow,
        identity=_IDENTITY,
    )

    assert staged.manifest.body.row_count == 0
    assert len(staged.manifest.body.parts) == 1
    assert restored.num_rows == 0
    assert restored.schema.equals(_table(row_count=0).schema, check_metadata=True)


def test_table_codec_rejects_corrupt_part(tmp_path: Path) -> None:
    directory = tmp_path / "corrupt"
    directory.mkdir()
    codec = _TableArtifactCodec()
    staged = codec.stage(
        directory=directory,
        table=_table(),
        row_model=_TableRow,
        identity=_IDENTITY,
    )
    part = directory / staged.manifest.body.parts[0].name
    part.write_bytes(part.read_bytes() + b"corruption")

    with pytest.raises(CFBDArtifactCorruptionError) as exc_info:
        codec.load(
            directory=directory,
            manifest=staged.manifest,
            row_model=_TableRow,
            identity=_IDENTITY,
        )

    assert exc_info.value.category == "table"


def test_table_codec_rejects_unexpected_object_member(tmp_path: Path) -> None:
    directory = tmp_path / "unexpected"
    directory.mkdir()
    codec = _TableArtifactCodec()
    staged = codec.stage(
        directory=directory,
        table=_table(),
        row_model=_TableRow,
        identity=_IDENTITY,
    )
    (directory / "extra.bin").write_bytes(b"unexpected")

    with pytest.raises(CFBDArtifactCorruptionError, match="invalid"):
        codec.load(
            directory=directory,
            manifest=staged.manifest,
            row_model=_TableRow,
            identity=_IDENTITY,
        )


def test_codec_requires_caller_owned_empty_staging_directory(tmp_path: Path) -> None:
    directory = tmp_path / "occupied"
    directory.mkdir()
    (directory / "existing").touch()

    with pytest.raises(CFBDArtifactCodecError) as exc_info:
        _TableArtifactCodec().stage(
            directory=directory,
            table=_table(),
            row_model=_TableRow,
            identity=_IDENTITY,
        )

    assert exc_info.value.category == "ownership"


def test_json_codec_writes_canonical_bounded_content(tmp_path: Path) -> None:
    directory = tmp_path / "json"
    directory.mkdir()
    codec = _JsonArtifactCodec()
    value = _ControlValue(reason="complete", count=2)

    staged = codec.stage(
        directory=directory,
        value=value,
        adapter=_CONTROL,
        identity=_IDENTITY,
    )
    restored = codec.load(
        directory=directory,
        manifest=None,
        adapter=_CONTROL,
        identity=_IDENTITY,
    )

    assert (directory / "value.json").read_bytes() == (
        b'{"count":2,"ratio":null,"reason":"complete"}'
    )
    assert staged.manifest.body.row_count is None
    assert restored == value


def test_json_codec_rejects_non_finite_values(tmp_path: Path) -> None:
    directory = tmp_path / "non-finite"
    directory.mkdir()

    with pytest.raises(CFBDArtifactCodecError) as exc_info:
        _JsonArtifactCodec().stage(
            directory=directory,
            value=_ControlValue(reason="bad", count=1, ratio=float("nan")),
            adapter=_CONTROL,
            identity=_IDENTITY,
        )

    assert exc_info.value.category == "validation"
    assert not any(directory.iterdir())


def test_json_codec_enforces_encoded_size_on_write_and_read(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "large"
    directory.mkdir()
    roomy = _JsonArtifactCodec()
    staged = roomy.stage(
        directory=directory,
        value=_ControlValue(reason="a" * 100, count=1),
        adapter=_CONTROL,
        identity=_IDENTITY,
    )

    with pytest.raises(CFBDArtifactCorruptionError):
        _JsonArtifactCodec(max_bytes=16).load(
            directory=directory,
            manifest=staged.manifest,
            adapter=_CONTROL,
            identity=_IDENTITY,
        )


def test_json_codec_rejects_wrong_output_schema(tmp_path: Path) -> None:
    directory = tmp_path / "wrong-schema"
    directory.mkdir()
    staged = _JsonArtifactCodec().stage(
        directory=directory,
        value=_ControlValue(reason="done", count=1),
        adapter=_CONTROL,
        identity=_IDENTITY,
    )

    with pytest.raises(CFBDArtifactCorruptionError):
        _JsonArtifactCodec().load(
            directory=directory,
            manifest=staged.manifest,
            adapter=_OTHER_CONTROL,
            identity=_IDENTITY,
        )


def test_manifest_rejects_noncanonical_or_modified_content(tmp_path: Path) -> None:
    directory = tmp_path / "manifest"
    directory.mkdir()
    _JsonArtifactCodec().stage(
        directory=directory,
        value=_ControlValue(reason="done", count=1),
        adapter=_CONTROL,
        identity=_IDENTITY,
    )
    manifest_path = directory / "manifest.json"
    parsed = json.loads(manifest_path.read_bytes())
    parsed["body"]["output_revision"] = 2
    manifest_path.write_bytes(_canonical_json_bytes(parsed))

    with pytest.raises(CFBDArtifactCorruptionError) as exc_info:
        _read_manifest(directory)

    assert exc_info.value.category == "manifest"
