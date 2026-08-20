"""Encode and validate immutable analytics artifact payloads."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from cfb_data._tabular import (
    _analytics_logical_records_from_arrow_table,
    _AnalyticsTableIdentity,
    _assert_analytics_arrow_table,
    _logical_schema,
    _logical_schema_digest,
)

from ._artifact_contract import (
    _artifact_columns,
    _DatasetContractEvidence,
    _table_artifact_contract,
    _TableArtifactContract,
)
from .errors import CFBDArtifactCodecError, CFBDArtifactCorruptionError

_MANIFEST_NAME: Final = "manifest.json"
_MAX_MANIFEST_BYTES: Final = 1024 * 1024
_DEFAULT_JSON_BYTES: Final = 32 * 1024 * 1024
_DEFAULT_ROWS_PER_PART: Final = 250_000
_DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"
_TABLE_CODEC_ID: Final = "cfb_data.analytics.parquet"
_TABLE_CODEC_VERSION: Final = 2
_JSON_CODEC_ID: Final = "cfb_data.analytics.json"
_JSON_CODEC_VERSION: Final = 1


class _ArtifactPart(BaseModel):
    """Describe one immutable artifact part."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1, max_length=128)
    media_type: str = Field(min_length=1, max_length=128)
    digest: str = Field(pattern=_DIGEST_PATTERN)
    size_bytes: int = Field(ge=0)
    row_count: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject paths and ambiguous dot components in part names."""
        if Path(value).name != value or value in {".", ".."}:
            raise ValueError("Artifact part names must be safe basenames")
        if any(character not in _SAFE_PART_CHARACTERS for character in value):
            raise ValueError("Artifact part names contain unsafe characters")
        return value


_SAFE_PART_CHARACTERS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


class _ArtifactManifestBody(BaseModel):
    """Describe stable content identity without run-specific audit evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[2] = 2
    kind: str = Field(min_length=1, max_length=128)
    codec_id: str = Field(min_length=1, max_length=256)
    codec_version: int = Field(ge=1)
    media_type: str = Field(min_length=1, max_length=128)
    output_id: str = Field(min_length=3, max_length=256)
    output_revision: int = Field(ge=1)
    schema_digest: str = Field(pattern=_DIGEST_PATTERN)
    row_count: int | None = Field(default=None, ge=0)
    table: _TableArtifactContract | None = None
    parts: tuple[_ArtifactPart, ...] = Field(min_length=1)

    @field_validator("output_id")
    @classmethod
    def validate_output_id(cls, value: str) -> str:
        """Require a namespaced durable output identity."""
        namespace, separator, name = value.partition(".")
        if not separator or not namespace or not name:
            raise ValueError("Artifact output IDs must be namespaced")
        return value

    @model_validator(mode="after")
    def validate_parts(self) -> _ArtifactManifestBody:
        """Require coherent kind metadata and deterministically ordered parts."""
        if (self.kind == "table") != (self.table is not None):
            raise ValueError("Only table artifacts may contain table metadata")
        names = tuple(part.name for part in self.parts)
        if len(set(names)) != len(names):
            raise ValueError("Artifact part names must be unique")
        if names != tuple(sorted(names)):
            raise ValueError("Artifact parts must be ordered by name")
        return self


class _ArtifactManifest(BaseModel):
    """Bind a canonical manifest body to its content digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    content_digest: str = Field(pattern=_DIGEST_PATTERN)
    body: _ArtifactManifestBody

    @model_validator(mode="after")
    def validate_content_digest(self) -> _ArtifactManifest:
        """Reject manifests whose digest does not bind the stable body."""
        if self.content_digest != _manifest_body_digest(self.body):
            raise ValueError("Artifact content digest is invalid")
        return self


@dataclass(frozen=True, slots=True)
class _StagedArtifact:
    """Return a fully validated staged artifact to the owning store."""

    directory: Path
    manifest: _ArtifactManifest


class _TableArtifactCodec:
    """Encode canonical analytics tables as deterministic Parquet parts."""

    codec_id: Final = _TABLE_CODEC_ID
    codec_version: Final = _TABLE_CODEC_VERSION
    media_type: Final = "application/vnd.apache.parquet"

    def __init__(self, *, max_rows_per_part: int = _DEFAULT_ROWS_PER_PART) -> None:
        """Configure deterministic row slicing.

        :param max_rows_per_part: Maximum rows written to each ordered part.
        :raises ValueError: If the part bound is not positive.
        """
        if max_rows_per_part < 1:
            raise ValueError("max_rows_per_part must be positive")
        self._max_rows_per_part = max_rows_per_part

    def stage(
        self,
        *,
        directory: Path,
        table: pa.Table,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        dataset: _DatasetContractEvidence | None = None,
    ) -> _StagedArtifact:
        """Write, reread, and validate deterministic Parquet parts.

        :param directory: Existing empty staging directory owned by the caller.
        :param table: Canonical analytics Parquet codec 2 Arrow table.
        :param row_model: Authoritative row model for full logical validation.
        :param identity: Stable output identity and semantic revision.
        :return: Validated staged artifact and content manifest.
        :raises CFBDArtifactCodecError: If staging ownership is invalid.
        :raises CFBDArtifactCorruptionError: If encoded content does not validate.
        """
        _require_empty_staging_directory(directory)
        try:
            _assert_analytics_arrow_table(
                row_model=row_model,
                table=table,
                identity=identity,
            )
            _analytics_logical_records_from_arrow_table(
                row_model=row_model,
                table=table,
                identity=identity,
            )
        except (TypeError, ValueError) as exc:
            raise CFBDArtifactCodecError(
                codec_id=self.codec_id,
                category="validation",
            ) from exc

        part_count = max(1, math.ceil(table.num_rows / self._max_rows_per_part))
        parts: list[_ArtifactPart] = []
        for ordinal in range(part_count):
            offset = ordinal * self._max_rows_per_part
            part_table = table.slice(offset, self._max_rows_per_part)
            name = f"part-{ordinal:05d}.parquet"
            path = directory / name
            pq.write_table(
                part_table,
                path,
                version="2.6",
                compression="zstd",
                write_statistics=True,
                use_compliant_nested_type=True,
                store_schema=True,
                row_group_size=65_536,
                data_page_version="1.0",
            )
            _flush_file(path)
            parts.append(
                _ArtifactPart(
                    name=name,
                    media_type=self.media_type,
                    digest=_file_digest(path),
                    size_bytes=path.stat().st_size,
                    row_count=part_table.num_rows,
                )
            )

        schema_digest = _logical_schema_digest(_logical_schema(row_model))
        body = _ArtifactManifestBody(
            kind="table",
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            media_type=self.media_type,
            output_id=identity.output_id,
            output_revision=identity.revision,
            schema_digest=schema_digest,
            row_count=table.num_rows,
            table=_table_artifact_contract(
                row_model,
                row_count=table.num_rows,
                dataset=dataset,
            ),
            parts=tuple(parts),
        )
        manifest = _write_manifest(directory, body)
        self.load(
            directory=directory,
            manifest=manifest,
            row_model=row_model,
            identity=identity,
            dataset=dataset,
        )
        return _StagedArtifact(directory=directory, manifest=manifest)

    def load(
        self,
        *,
        directory: Path,
        manifest: _ArtifactManifest | None,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        dataset: _DatasetContractEvidence | None = None,
    ) -> pa.Table:
        """Load and validate all ordered Parquet parts.

        :param directory: Artifact object directory.
        :param manifest: Previously inspected manifest, or ``None`` to read it.
        :param row_model: Authoritative expected row model.
        :param identity: Expected stable output identity and revision.
        :return: Canonical analytics Parquet codec 2 Arrow table.
        :raises CFBDArtifactCorruptionError: If any durable invariant fails.
        """
        try:
            checked = manifest or _read_manifest(directory)
            _verify_manifest_codec(
                checked,
                kind="table",
                codec_id=self.codec_id,
                codec_version=self.codec_version,
                identity=identity,
            )
            _verify_directory_members(directory, checked)
            tables: list[pa.Table] = []
            total_rows = 0
            for part in checked.body.parts:
                path = directory / part.name
                _verify_part(path, part)
                table = pq.read_table(path)
                _assert_analytics_arrow_table(
                    row_model=row_model,
                    table=table,
                    identity=identity,
                )
                _analytics_logical_records_from_arrow_table(
                    row_model=row_model,
                    table=table,
                    identity=identity,
                )
                if part.row_count != table.num_rows:
                    raise ValueError("Artifact part row count is invalid")
                total_rows += table.num_rows
                tables.append(table)
            if checked.body.row_count != total_rows:
                raise ValueError("Artifact total row count is invalid")
            if checked.body.schema_digest != _logical_schema_digest(
                _logical_schema(row_model)
            ):
                raise ValueError("Artifact logical schema digest is invalid")
            metadata = checked.body.table
            if metadata is None or metadata.columns != _artifact_columns(row_model):
                raise ValueError("Artifact column metadata is invalid")
            if any(result.rows_checked != total_rows for result in metadata.quality):
                raise ValueError("Artifact quality evidence has an invalid row count")
            if dataset is not None and metadata != _table_artifact_contract(
                row_model,
                row_count=total_rows,
                dataset=dataset,
            ):
                raise ValueError("Artifact table contract is incompatible")
            if len(tables) == 1:
                return tables[0]
            return pa.concat_tables(tables, promote_options="none")
        except CFBDArtifactCorruptionError:
            raise
        except Exception as exc:
            raise CFBDArtifactCorruptionError(
                content_digest=(manifest.content_digest if manifest else None),
                category="table",
            ) from exc


class _JsonArtifactCodec:
    """Encode bounded Pydantic-validated control values as canonical JSON."""

    codec_id: Final = _JSON_CODEC_ID
    codec_version: Final = _JSON_CODEC_VERSION
    media_type: Final = "application/json"

    def __init__(self, *, max_bytes: int = _DEFAULT_JSON_BYTES) -> None:
        """Configure the encoded-size boundary.

        :param max_bytes: Largest accepted canonical JSON payload.
        :raises ValueError: If the size boundary is not positive.
        """
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes

    def stage[ValueT](
        self,
        *,
        directory: Path,
        value: ValueT,
        adapter: TypeAdapter[ValueT],
        identity: _AnalyticsTableIdentity,
    ) -> _StagedArtifact:
        """Write and validate one canonical modeled-JSON artifact."""
        _require_empty_staging_directory(directory)
        try:
            validated = adapter.validate_python(value)
            logical = adapter.dump_python(validated, mode="json")
            _validate_json_value(logical)
            payload = _canonical_json_bytes(logical)
            if len(payload) > self._max_bytes:
                raise ValueError("Modeled JSON exceeds its configured size limit")
            adapter.validate_json(payload)
        except (TypeError, ValueError) as exc:
            raise CFBDArtifactCodecError(
                codec_id=self.codec_id,
                category="validation",
            ) from exc

        path = directory / "value.json"
        path.write_bytes(payload)
        _flush_file(path)
        schema_digest = _json_schema_digest(adapter)
        body = _ArtifactManifestBody(
            kind="json",
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            media_type=self.media_type,
            output_id=identity.output_id,
            output_revision=identity.revision,
            schema_digest=schema_digest,
            row_count=None,
            parts=(
                _ArtifactPart(
                    name=path.name,
                    media_type=self.media_type,
                    digest=_file_digest(path),
                    size_bytes=path.stat().st_size,
                    row_count=None,
                ),
            ),
        )
        manifest = _write_manifest(directory, body)
        self.load(
            directory=directory,
            manifest=manifest,
            adapter=adapter,
            identity=identity,
        )
        return _StagedArtifact(directory=directory, manifest=manifest)

    def load[ValueT](
        self,
        *,
        directory: Path,
        manifest: _ArtifactManifest | None,
        adapter: TypeAdapter[ValueT],
        identity: _AnalyticsTableIdentity,
    ) -> ValueT:
        """Load one bounded modeled-JSON artifact with full validation."""
        try:
            checked = manifest or _read_manifest(directory)
            _verify_manifest_codec(
                checked,
                kind="json",
                codec_id=self.codec_id,
                codec_version=self.codec_version,
                identity=identity,
            )
            _verify_directory_members(directory, checked)
            if len(checked.body.parts) != 1:
                raise ValueError("Modeled JSON artifacts require exactly one part")
            part = checked.body.parts[0]
            path = directory / part.name
            _verify_part(path, part)
            payload = path.read_bytes()
            if len(payload) > self._max_bytes:
                raise ValueError("Modeled JSON exceeds its configured size limit")
            value = adapter.validate_json(payload)
            logical = adapter.dump_python(value, mode="json")
            _validate_json_value(logical)
            if payload != _canonical_json_bytes(logical):
                raise ValueError("Modeled JSON is not canonically encoded")
            if checked.body.schema_digest != _json_schema_digest(adapter):
                raise ValueError("Modeled JSON schema digest is invalid")
            return value
        except CFBDArtifactCorruptionError:
            raise
        except Exception as exc:
            raise CFBDArtifactCorruptionError(
                content_digest=(manifest.content_digest if manifest else None),
                category="json",
            ) from exc


def _write_manifest(
    directory: Path,
    body: _ArtifactManifestBody,
) -> _ArtifactManifest:
    """Write a canonical content-bound manifest into a staging directory."""
    manifest = _ArtifactManifest(
        content_digest=_manifest_body_digest(body),
        body=body,
    )
    payload = _canonical_json_bytes(manifest.model_dump(mode="json"))
    path = directory / _MANIFEST_NAME
    path.write_bytes(payload)
    _flush_file(path)
    restored = _read_manifest(directory)
    if restored != manifest:
        raise CFBDArtifactCorruptionError(
            content_digest=manifest.content_digest,
            category="manifest",
        )
    return manifest


def _read_manifest(directory: Path) -> _ArtifactManifest:
    """Read one bounded strict manifest without loading artifact payloads."""
    path = directory / _MANIFEST_NAME
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Artifact object directory is invalid")
        if path.is_symlink() or not path.is_file():
            raise ValueError("Artifact manifest is not a regular file")
        size = path.stat().st_size
        if size > _MAX_MANIFEST_BYTES:
            raise ValueError("Artifact manifest exceeds its size limit")
        payload = path.read_bytes()
        manifest = _ArtifactManifest.model_validate_json(payload, strict=True)
        if payload != _canonical_json_bytes(manifest.model_dump(mode="json")):
            raise ValueError("Artifact manifest is not canonically encoded")
        return manifest
    except CFBDArtifactCorruptionError:
        raise
    except Exception as exc:
        raise CFBDArtifactCorruptionError(
            content_digest=None,
            category="manifest",
        ) from exc


def _verify_manifest_codec(
    manifest: _ArtifactManifest,
    *,
    kind: str,
    codec_id: str,
    codec_version: int,
    identity: _AnalyticsTableIdentity,
) -> None:
    """Verify codec and stable output identity before reading payloads."""
    body = manifest.body
    if (
        body.kind != kind
        or body.codec_id != codec_id
        or body.codec_version != codec_version
        or body.output_id != identity.output_id
        or body.output_revision != identity.revision
    ):
        raise CFBDArtifactCorruptionError(
            content_digest=manifest.content_digest,
            category="compatibility",
        )


def _verify_directory_members(
    directory: Path,
    manifest: _ArtifactManifest,
) -> None:
    """Reject missing or unexpected files in an immutable object directory."""
    expected = {_MANIFEST_NAME, *(part.name for part in manifest.body.parts)}
    members = tuple(directory.iterdir())
    actual = {path.name for path in members}
    if actual != expected:
        raise ValueError("Artifact object members do not match its manifest")
    if any(path.is_symlink() or not path.is_file() for path in members):
        raise ValueError("Artifact object members must be regular files")


def _verify_part(path: Path, part: _ArtifactPart) -> None:
    """Verify one part's existence, byte count, and content digest."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("Artifact part is missing")
    if path.stat().st_size != part.size_bytes:
        raise ValueError("Artifact part size is invalid")
    if _file_digest(path) != part.digest:
        raise ValueError("Artifact part digest is invalid")


def _require_empty_staging_directory(directory: Path) -> None:
    """Require caller-owned existing empty staging storage."""
    if not directory.is_dir():
        raise CFBDArtifactCodecError(
            codec_id="staging",
            category="ownership",
        )
    if any(directory.iterdir()):
        raise CFBDArtifactCodecError(
            codec_id="staging",
            category="ownership",
        )


def _manifest_body_digest(body: _ArtifactManifestBody) -> str:
    """Return the content digest over canonical stable manifest fields."""
    return hashlib.sha256(
        _canonical_json_bytes(body.model_dump(mode="json"))
    ).hexdigest()


def _json_schema_digest[ValueT](adapter: TypeAdapter[ValueT]) -> str:
    """Return a deterministic digest of a modeled JSON output schema."""
    return hashlib.sha256(_canonical_json_bytes(adapter.json_schema())).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    """Encode JSON with deterministic ordering and no non-finite numbers."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_json_value(value: object) -> None:
    """Reject non-JSON values and non-finite numbers recursively."""
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Modeled JSON cannot contain non-finite numbers")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Modeled JSON mapping keys must be strings")
            _validate_json_value(item)
        return
    raise TypeError("Modeled JSON contains an unsupported value")


def _file_digest(path: Path) -> str:
    """Return a streaming SHA-256 digest for one closed file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _flush_file(path: Path) -> None:
    """Flush one closed file's contents to durable storage."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__: Sequence[str] = ()
