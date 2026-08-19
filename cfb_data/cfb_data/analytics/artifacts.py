"""Persist immutable analytics artifacts and transactional run manifests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from platform import system
from types import MappingProxyType
from typing import Self

import aiosqlite
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _PandasAdapter, _PolarsAdapter
from cfb_data._parquet import _read_parquet, _write_parquet
from cfb_data._tabular import _assert_canonical_arrow_table
from cfb_data.analytics.contracts import (
    ColumnMetadata,
    CoverageState,
    QualityResult,
    SourceCoverage,
    TableContract,
    canonical_json,
)
from cfb_data.errors import CFBDArtifactError, CFBDClientStateError

_ANALYTICS_FORMAT_VERSION = 1
_TABLE_CODEC_ID = "cfbd.parquet.table"
_TABLE_CODEC_VERSION = 1
_MODEL_CODEC_ID = "cfbd.json.model"
_MODEL_CODEC_VERSION = 1
_MAX_JSON_BYTES = 32 * 1024 * 1024
_CONTRACT_ID_KEY = b"cfb_data.analytics.contract_id"
_CONTRACT_REVISION_KEY = b"cfb_data.analytics.contract_revision"
_CONTRACT_SCHEMA_KEY = b"cfb_data.analytics.contract_schema_sha256"


@dataclass(frozen=True, slots=True)
class ArtifactPart:
    """Describe one immutable ordered artifact part."""

    name: str
    digest: str
    byte_count: int
    row_count: int | None


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Describe a versioned immutable artifact without exposing its path."""

    format_version: int
    artifact_id: str
    kind: str
    codec_id: str
    codec_version: int
    media_type: str
    content_digest: str
    byte_count: int
    row_count: int | None
    contract_id: str
    contract_revision: int
    schema_digest: str
    grain: str | None
    keys: tuple[str, ...]
    order_by: tuple[str, ...]
    partition_by: tuple[str, ...]
    event_time: str | None
    columns: Mapping[str, ColumnMetadata]
    parts: tuple[ArtifactPart, ...]
    producer_definition_id: str
    producer_definition_revision: int
    producer_step_id: str
    upstream_digests: tuple[str, ...]
    created_at: datetime
    source_fetched_at: datetime | None
    source_validated_at: datetime | None
    quality: tuple[QualityResult, ...]
    coverage: tuple[SourceCoverage, ...]
    dependency_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", MappingProxyType(dict(self.columns)))
        object.__setattr__(
            self,
            "dependency_versions",
            MappingProxyType(dict(self.dependency_versions)),
        )


@dataclass(frozen=True, slots=True)
class StoredNode:
    """Describe one successful node persisted in a run manifest."""

    run_id: str
    step_id: str
    fingerprint: str
    artifact_id: str
    reused: bool


@dataclass(frozen=True, slots=True)
class RunDescriptor:
    """Describe one immutable analytics run without exposing parameters."""

    run_id: str
    definition_id: str
    definition_revision: int
    parameter_fingerprint: str
    parent_run_id: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    failure_step_id: str | None
    failure_category: str | None


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Reference one validated artifact independently of client lifetime."""

    descriptor: ArtifactDescriptor
    _root: Path
    _row_model: type[BaseModel] | None = None

    def load_table(self) -> pa.Table:
        """Load and fully validate a table artifact.

        :return: Canonical Arrow table in declared row order.
        :raises CFBDArtifactError: If content is missing or invalid.
        """
        if self.descriptor.kind != "table" or self._row_model is None:
            raise CFBDArtifactError("Artifact is not a loadable table")
        row_model = self._row_model
        try:
            tables: list[pa.Table] = []
            for part in self.descriptor.parts:
                path = self._object_path() / part.name
                if _sha256_file(path) != part.digest:
                    raise CFBDArtifactError("Artifact part digest does not match")
                stored_table = pq.read_table(path)
                _assert_analytics_metadata(stored_table, self.descriptor)
                # Pydantic accepts a runtime model in this generic alias.
                adapter = TypeAdapter(list[row_model])  # type: ignore[valid-type]
                table = _read_parquet(
                    path,
                    row_model=row_model,
                    response_adapter=adapter,
                    validation="full",
                )
                if table.num_rows != part.row_count:
                    raise CFBDArtifactError("Artifact part row count does not match")
                tables.append(
                    table.replace_schema_metadata(stored_table.schema.metadata)
                )
            if not tables:
                raise CFBDArtifactError("Table artifact contains no parts")
            combined = pa.concat_tables(tables)
            if combined.num_rows != self.descriptor.row_count:
                raise CFBDArtifactError("Artifact row count does not match")
            return combined
        except CFBDArtifactError:
            raise
        except Exception as exc:
            raise CFBDArtifactError("Artifact table validation failed") from exc

    def load(self, *, dataframe_backend: str = "pandas") -> object:
        """Load a table as one eager pandas or Polars DataFrame.

        :param dataframe_backend: ``pandas`` or ``polars``.
        :return: Validated eager DataFrame.
        :raises ValueError: If the backend name is unsupported.
        """
        if self._row_model is None:
            raise CFBDArtifactError("Artifact is not a loadable table")
        table = self.load_table()
        if dataframe_backend == "pandas":
            return _PandasAdapter().from_table(
                endpoint=self.descriptor.contract_id,
                row_model=self._row_model,
                table=table,
            )
        if dataframe_backend == "polars":
            return _PolarsAdapter().from_table(
                endpoint=self.descriptor.contract_id,
                row_model=self._row_model,
                table=table,
            )
        raise ValueError("dataframe_backend must be either 'pandas' or 'polars'")

    def load_model[ModelT: BaseModel](self, model: type[ModelT]) -> ModelT:
        """Load and validate one bounded canonical JSON model artifact.

        :param model: Authoritative Pydantic model for the stored contract.
        :return: Fully validated model value.
        :raises CFBDArtifactError: If kind, digest, schema, size, or data is invalid.
        """
        if self.descriptor.kind != "model" or len(self.descriptor.parts) != 1:
            raise CFBDArtifactError("Artifact is not a loadable model")
        expected_schema = hashlib.sha256(
            canonical_json(model.model_json_schema())
        ).hexdigest()
        if expected_schema != self.descriptor.schema_digest:
            raise CFBDArtifactError("Model artifact schema is incompatible")
        part = self.descriptor.parts[0]
        path = self._object_path() / part.name
        try:
            if (
                part.byte_count > _MAX_JSON_BYTES
                or path.stat().st_size > _MAX_JSON_BYTES
            ):
                raise CFBDArtifactError("JSON artifact exceeds the 32 MiB limit")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != part.digest:
                raise CFBDArtifactError("Artifact part digest does not match")
            return model.model_validate_json(payload, strict=True)
        except CFBDArtifactError:
            raise
        except Exception as exc:
            raise CFBDArtifactError("Artifact model validation failed") from exc

    def export_parquet(
        self,
        destination: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Export canonical Parquet without exposing checkpoint layout.

        :param destination: Explicit destination file for a single-part table.
        :param overwrite: Replace an existing file only when true.
        :return: Exported destination path.
        :raises FileExistsError: If the destination exists and overwrite is false.
        :raises CFBDArtifactError: If the artifact is not a table.
        """
        if self.descriptor.kind != "table" or self._row_model is None:
            raise CFBDArtifactError("Artifact is not a loadable table")
        target = Path(destination)
        if target.exists() and not overwrite:
            raise FileExistsError("Parquet export destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        table = self.load_table()
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            _write_parquet(temporary, row_model=self._row_model, table=table)
            os.replace(temporary, target)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()
        return target

    def _object_path(self) -> Path:
        digest = self.descriptor.content_digest
        return self._root / "objects" / digest[:2] / digest


class LocalArtifactStore:
    """Own transactional run state and immutable local artifact objects."""

    def __init__(self, path: Path | None = None) -> None:
        self._root = path or _default_path()
        self._database_path = self._root / "runs.sqlite3"
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        """Return the configured root without opening the store."""
        return self._root

    async def open(self) -> Self:
        """Open and initialize the local store exactly once."""
        if self._connection is not None:
            raise CFBDClientStateError("Analytics artifact store is already open")
        try:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
            (self._root / "objects").mkdir(mode=0o700, exist_ok=True)
            (self._root / "staging").mkdir(mode=0o700, exist_ok=True)
            connection = await aiosqlite.connect(
                self._database_path,
                timeout=5.0,
                isolation_level=None,
            )
            self._connection = connection
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA journal_mode = WAL")
            await connection.execute("PRAGMA synchronous = FULL")
            await connection.executescript(_SCHEMA_SQL)
            os.chmod(self._root, 0o700)
            os.chmod(self._database_path, 0o600)
            return self
        except Exception as exc:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None
            raise CFBDArtifactError(
                "Analytics artifact store initialization failed"
            ) from exc

    async def close(self) -> None:
        """Close the owned SQLite connection."""
        async with self._lock:
            connection = self._active_connection()
            self._connection = None
            await connection.close()

    async def begin_run(
        self,
        *,
        run_id: str,
        definition_id: str,
        definition_revision: int,
        parameter_fingerprint: str,
        parent_run_id: str | None,
    ) -> None:
        """Persist the immutable identity of a newly started run."""
        async with self._lock:
            connection = self._active_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT INTO analytics_runs (
                        run_id, definition_id, definition_revision,
                        parameter_fingerprint, parent_run_id, status, started_at
                    ) VALUES (?, ?, ?, ?, ?, 'running', ?)
                    """,
                    (
                        run_id,
                        definition_id,
                        definition_revision,
                        parameter_fingerprint,
                        parent_run_id,
                        _utc_now().isoformat(),
                    ),
                )
                await connection.commit()
            except Exception as exc:
                await connection.rollback()
                raise CFBDArtifactError("Analytics run creation failed") from exc

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        failure_step_id: str | None = None,
        failure_category: str | None = None,
    ) -> None:
        """Record one terminal immutable run state."""
        if status not in {"success", "error", "cancelled"}:
            raise ValueError("Unsupported analytics run status")
        async with self._lock:
            connection = self._active_connection()
            cursor = await connection.execute(
                """
                UPDATE analytics_runs
                SET status = ?, finished_at = ?, failure_step_id = ?,
                    failure_category = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (
                    status,
                    _utc_now().isoformat(),
                    failure_step_id,
                    failure_category,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                await cursor.close()
                raise CFBDArtifactError("Analytics run is not active")
            await cursor.close()

    async def latest_failed_run(
        self, *, definition_id: str, parameter_fingerprint: str
    ) -> str | None:
        """Return the newest failed compatible run for automatic recovery."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                """
                SELECT run_id FROM analytics_runs
                WHERE definition_id = ? AND parameter_fingerprint = ?
                  AND status IN ('error', 'cancelled')
                ORDER BY started_at DESC LIMIT 1
                """,
                (definition_id, parameter_fingerprint),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return str(row[0]) if row is not None else None

    async def write_table(
        self,
        *,
        run_id: str,
        step_id: str,
        fingerprint: str,
        definition_id: str,
        definition_revision: int,
        contract: TableContract[BaseModel],
        table: pa.Table,
        upstream_digests: tuple[str, ...],
        source_fetched_at: datetime | None,
        source_validated_at: datetime | None,
        quality: tuple[QualityResult, ...],
        coverage: tuple[SourceCoverage, ...],
    ) -> ArtifactRef:
        """Validate, atomically publish, and transactionally commit one table."""
        try:
            descriptor, manifest = await asyncio.to_thread(
                _publish_table_object,
                self._root,
                definition_id,
                definition_revision,
                step_id,
                contract,
                table,
                upstream_digests,
                source_fetched_at,
                source_validated_at,
                quality,
                coverage,
            )
            await self._commit_artifact_and_node(
                descriptor=descriptor,
                manifest=manifest,
                run_id=run_id,
                step_id=step_id,
                fingerprint=fingerprint,
            )
            return ArtifactRef(descriptor, self._root, contract.row_model)
        except Exception as exc:
            if isinstance(exc, CFBDArtifactError):
                raise
            raise CFBDArtifactError("Analytics artifact publication failed") from exc

    async def write_json(
        self,
        *,
        run_id: str,
        step_id: str,
        fingerprint: str,
        definition_id: str,
        definition_revision: int,
        contract_id: str,
        contract_revision: int,
        model: BaseModel,
        upstream_digests: tuple[str, ...] = (),
    ) -> ArtifactRef:
        """Persist one bounded schema-validated canonical JSON model."""
        try:
            descriptor, manifest = await asyncio.to_thread(
                _publish_model_object,
                self._root,
                definition_id,
                definition_revision,
                step_id,
                contract_id,
                contract_revision,
                model,
                upstream_digests,
            )
            await self._commit_artifact_and_node(
                descriptor=descriptor,
                manifest=manifest,
                run_id=run_id,
                step_id=step_id,
                fingerprint=fingerprint,
            )
            return ArtifactRef(descriptor, self._root)
        except Exception as exc:
            if isinstance(exc, CFBDArtifactError):
                raise
            raise CFBDArtifactError("JSON artifact publication failed") from exc

    async def compatible_artifact(
        self,
        *,
        fingerprint: str,
        contract: TableContract[BaseModel],
    ) -> ArtifactRef | None:
        """Return the newest fully compatible table artifact for a node key."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                """
                SELECT a.manifest_json
                FROM analytics_nodes n
                JOIN analytics_artifacts a ON a.artifact_id = n.artifact_id
                WHERE n.fingerprint = ? AND n.status = 'success'
                ORDER BY n.completed_at DESC LIMIT 1
                """,
                (fingerprint,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            return None
        descriptor = _descriptor_from_payload(json.loads(str(row[0])))
        if (
            descriptor.contract_id != contract.id
            or descriptor.contract_revision != contract.revision
            or descriptor.schema_digest != contract.schema_digest
        ):
            return None
        ref = ArtifactRef(descriptor, self._root, contract.row_model)
        await asyncio.to_thread(ref.load_table)
        return ref

    async def run_artifact(
        self,
        *,
        run_id: str,
        step_id: str,
        fingerprint: str,
        contract: TableContract[BaseModel],
    ) -> ArtifactRef | None:
        """Return one compatible completed artifact from a specific run."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                """
                SELECT a.manifest_json
                FROM analytics_nodes n
                JOIN analytics_artifacts a ON a.artifact_id = n.artifact_id
                WHERE n.run_id = ? AND n.step_id = ? AND n.fingerprint = ?
                  AND n.status = 'success'
                """,
                (run_id, step_id, fingerprint),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            return None
        descriptor = _descriptor_from_payload(json.loads(str(row[0])))
        if (
            descriptor.contract_id != contract.id
            or descriptor.contract_revision != contract.revision
            or descriptor.schema_digest != contract.schema_digest
        ):
            return None
        ref = ArtifactRef(descriptor, self._root, contract.row_model)
        await asyncio.to_thread(ref.load_table)
        return ref

    async def record_reuse(
        self,
        *,
        run_id: str,
        step_id: str,
        fingerprint: str,
        artifact_id: str,
    ) -> None:
        """Record that a child or compatible run reused one artifact."""
        async with self._lock:
            await self._active_connection().execute(
                """
                INSERT INTO analytics_nodes (
                    run_id, step_id, fingerprint, status, artifact_id,
                    reused, completed_at
                ) VALUES (?, ?, ?, 'success', ?, 1, ?)
                """,
                (run_id, step_id, fingerprint, artifact_id, _utc_now().isoformat()),
            )

    async def acquire_lease(
        self,
        *,
        fingerprint: str,
        owner: str,
        duration: timedelta = timedelta(seconds=30),
    ) -> bool:
        """Acquire one bounded cross-process node-computation lease."""
        now = _utc_now()
        expires = now + duration
        async with self._lock:
            connection = self._active_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    "DELETE FROM analytics_leases WHERE expires_at <= ?",
                    (now.isoformat(),),
                )
                await connection.execute(
                    """
                    INSERT INTO analytics_leases (fingerprint, owner, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (fingerprint, owner, expires.isoformat()),
                )
                await connection.commit()
                return True
            except sqlite3.IntegrityError:
                await connection.rollback()
                return False
            except Exception as exc:
                await connection.rollback()
                raise CFBDArtifactError("Analytics lease acquisition failed") from exc

    async def release_lease(self, *, fingerprint: str, owner: str) -> None:
        """Release a lease only when the caller still owns it."""
        async with self._lock:
            await self._active_connection().execute(
                "DELETE FROM analytics_leases WHERE fingerprint = ? AND owner = ?",
                (fingerprint, owner),
            )

    async def pin(self, artifact_id: str, *, pinned: bool = True) -> None:
        """Pin or unpin an artifact against explicit pruning."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                "UPDATE analytics_artifacts SET pinned = ? WHERE artifact_id = ?",
                (int(pinned), artifact_id),
            )
            if cursor.rowcount != 1:
                await cursor.close()
                raise CFBDArtifactError("Unknown analytics artifact")
            await cursor.close()

    async def list_artifacts(
        self, *, limit: int = 100
    ) -> tuple[ArtifactDescriptor, ...]:
        """List newest artifact descriptors without loading their content."""
        _validate_list_limit(limit)
        async with self._lock:
            cursor = await self._active_connection().execute(
                """
                SELECT manifest_json FROM analytics_artifacts
                ORDER BY created_at DESC, artifact_id LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return tuple(_descriptor_from_payload(json.loads(str(row[0]))) for row in rows)

    async def inspect_artifact(self, artifact_id: str) -> ArtifactDescriptor:
        """Return one artifact descriptor by its opaque identifier."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                "SELECT manifest_json FROM analytics_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise CFBDArtifactError("Unknown analytics artifact")
        return _descriptor_from_payload(json.loads(str(row[0])))

    async def list_runs(
        self,
        *,
        definition_id: str | None = None,
        limit: int = 100,
    ) -> tuple[RunDescriptor, ...]:
        """List newest safe run descriptors with optional definition filtering."""
        _validate_list_limit(limit)
        query = """
            SELECT run_id, definition_id, definition_revision,
                   parameter_fingerprint, parent_run_id, status, started_at,
                   finished_at, failure_step_id, failure_category
            FROM analytics_runs
        """
        parameters: tuple[object, ...]
        if definition_id is None:
            query += " ORDER BY started_at DESC, run_id LIMIT ?"
            parameters = (limit,)
        else:
            query += " WHERE definition_id = ? ORDER BY started_at DESC, run_id LIMIT ?"
            parameters = (definition_id, limit)
        async with self._lock:
            cursor = await self._active_connection().execute(query, parameters)
            rows = await cursor.fetchall()
            await cursor.close()
        return tuple(_run_descriptor(row) for row in rows)

    async def inspect_run(self, run_id: str) -> RunDescriptor:
        """Return one safe immutable run descriptor by ID."""
        async with self._lock:
            cursor = await self._active_connection().execute(
                """
                SELECT run_id, definition_id, definition_revision,
                       parameter_fingerprint, parent_run_id, status, started_at,
                       finished_at, failure_step_id, failure_category
                FROM analytics_runs WHERE run_id = ?
                """,
                (run_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise CFBDArtifactError("Unknown analytics run")
        return _run_descriptor(row)

    async def prune(self, *, dry_run: bool = True) -> tuple[str, ...]:
        """List or remove unreferenced, unpinned immutable artifacts."""
        async with self._lock:
            connection = self._active_connection()
            cursor = await connection.execute(
                """
                SELECT artifact_id, content_digest FROM analytics_artifacts a
                WHERE pinned = 0 AND NOT EXISTS (
                    SELECT 1 FROM analytics_nodes n
                    WHERE n.artifact_id = a.artifact_id
                )
                ORDER BY created_at
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            artifact_ids = tuple(str(row[0]) for row in rows)
            if not dry_run:
                await connection.execute("BEGIN IMMEDIATE")
                try:
                    for artifact_id, digest in rows:
                        await connection.execute(
                            "DELETE FROM analytics_artifacts WHERE artifact_id = ?",
                            (artifact_id,),
                        )
                        path = self._root / "objects" / str(digest)[:2] / str(digest)
                        if path.is_dir():
                            shutil.rmtree(path)
                    await connection.commit()
                except Exception as exc:
                    await connection.rollback()
                    raise CFBDArtifactError("Artifact pruning failed") from exc
        return artifact_ids

    async def cleanup_orphans(self, *, older_than: timedelta) -> int:
        """Remove stale staging directories left by interrupted writers."""
        if older_than.total_seconds() < 0:
            raise ValueError("Orphan age must not be negative")
        return await asyncio.to_thread(_cleanup_orphans, self._root, older_than)

    async def _commit_artifact_and_node(
        self,
        *,
        descriptor: ArtifactDescriptor,
        manifest: Mapping[str, object],
        run_id: str,
        step_id: str,
        fingerprint: str,
    ) -> None:
        async with self._lock:
            connection = self._active_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT OR IGNORE INTO analytics_artifacts (
                        artifact_id, content_digest, kind, codec_id,
                        contract_id, contract_revision, manifest_json,
                        byte_count, row_count, created_at, pinned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        descriptor.artifact_id,
                        descriptor.content_digest,
                        descriptor.kind,
                        descriptor.codec_id,
                        descriptor.contract_id,
                        descriptor.contract_revision,
                        canonical_json(dict(manifest)).decode(),
                        descriptor.byte_count,
                        descriptor.row_count,
                        descriptor.created_at.isoformat(),
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO analytics_nodes (
                        run_id, step_id, fingerprint, status, artifact_id,
                        reused, completed_at
                    ) VALUES (?, ?, ?, 'success', ?, 0, ?)
                    """,
                    (
                        run_id,
                        step_id,
                        fingerprint,
                        descriptor.artifact_id,
                        _utc_now().isoformat(),
                    ),
                )
                await connection.commit()
            except Exception as exc:
                await connection.rollback()
                raise CFBDArtifactError("Artifact manifest commit failed") from exc

    def _active_connection(self) -> aiosqlite.Connection:
        connection = self._connection
        if connection is None:
            raise CFBDClientStateError("Analytics artifact store is not open")
        return connection


def _publish_model_object(
    root: Path,
    definition_id: str,
    definition_revision: int,
    step_id: str,
    contract_id: str,
    contract_revision: int,
    model: BaseModel,
    upstream_digests: tuple[str, ...],
) -> tuple[ArtifactDescriptor, dict[str, object]]:
    """Publish one immutable bounded model object from a worker thread."""
    encoded = canonical_json(model.model_dump(mode="json", by_alias=False))
    if len(encoded) > _MAX_JSON_BYTES:
        raise CFBDArtifactError("JSON artifact exceeds the 32 MiB limit")
    digest = hashlib.sha256(encoded).hexdigest()
    staging = root / "staging" / uuid.uuid4().hex
    staging.mkdir(mode=0o700)
    try:
        data_path = staging / "model.json"
        with data_path.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        schema_digest = hashlib.sha256(
            canonical_json(model.__class__.model_json_schema())
        ).hexdigest()
        descriptor = ArtifactDescriptor(
            format_version=_ANALYTICS_FORMAT_VERSION,
            artifact_id=uuid.uuid4().hex,
            kind="model",
            codec_id=_MODEL_CODEC_ID,
            codec_version=_MODEL_CODEC_VERSION,
            media_type="application/json",
            content_digest=digest,
            byte_count=len(encoded),
            row_count=None,
            contract_id=contract_id,
            contract_revision=contract_revision,
            schema_digest=schema_digest,
            grain=None,
            keys=(),
            order_by=(),
            partition_by=(),
            event_time=None,
            columns={},
            parts=(ArtifactPart("model.json", digest, len(encoded), None),),
            producer_definition_id=definition_id,
            producer_definition_revision=definition_revision,
            producer_step_id=step_id,
            upstream_digests=upstream_digests,
            created_at=_utc_now(),
            source_fetched_at=None,
            source_validated_at=None,
            quality=(),
            coverage=(),
            dependency_versions=_dependency_versions(),
        )
        manifest = _descriptor_payload(descriptor)
        with (staging / "manifest.json").open("wb") as stream:
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(staging)
        _publish_staging_object(root, digest, staging)
        return descriptor, manifest
    except Exception:
        with suppress(FileNotFoundError):
            shutil.rmtree(staging)
        raise


def _publish_table_object(
    root: Path,
    definition_id: str,
    definition_revision: int,
    step_id: str,
    contract: TableContract[BaseModel],
    table: pa.Table,
    upstream_digests: tuple[str, ...],
    source_fetched_at: datetime | None,
    source_validated_at: datetime | None,
    quality: tuple[QualityResult, ...],
    coverage: tuple[SourceCoverage, ...],
) -> tuple[ArtifactDescriptor, dict[str, object]]:
    """Publish one immutable table object from a worker thread."""
    _assert_canonical_arrow_table(row_model=contract.row_model, table=table)
    stored_table = _with_analytics_metadata(table, contract)
    staging = root / "staging" / uuid.uuid4().hex
    staging.mkdir(mode=0o700)
    try:
        parts: list[ArtifactPart] = []
        for index, partition in enumerate(
            _partition_tables(stored_table, contract.partition_by)
        ):
            part_path = staging / f"part-{index:05d}.parquet"
            _write_parquet(
                part_path,
                row_model=contract.row_model,
                table=partition,
            )
            _fsync_file(part_path)
            parts.append(
                ArtifactPart(
                    name=part_path.name,
                    digest=_sha256_file(part_path),
                    byte_count=part_path.stat().st_size,
                    row_count=partition.num_rows,
                )
            )
        content_digest = hashlib.sha256(
            canonical_json(
                {
                    "codec": [_TABLE_CODEC_ID, _TABLE_CODEC_VERSION],
                    "contract": [
                        contract.id,
                        contract.revision,
                        contract.schema_digest,
                    ],
                    "parts": [
                        [part.name, part.digest, part.row_count] for part in parts
                    ],
                }
            )
        ).hexdigest()
        descriptor = ArtifactDescriptor(
            format_version=_ANALYTICS_FORMAT_VERSION,
            artifact_id=uuid.uuid4().hex,
            kind="table",
            codec_id=_TABLE_CODEC_ID,
            codec_version=_TABLE_CODEC_VERSION,
            media_type="application/vnd.apache.parquet",
            content_digest=content_digest,
            byte_count=sum(part.byte_count for part in parts),
            row_count=stored_table.num_rows,
            contract_id=contract.id,
            contract_revision=contract.revision,
            schema_digest=contract.schema_digest,
            grain=contract.grain,
            keys=contract.keys,
            order_by=contract.order_by,
            partition_by=contract.partition_by,
            event_time=contract.event_time,
            columns=contract.columns,
            parts=tuple(parts),
            producer_definition_id=definition_id,
            producer_definition_revision=definition_revision,
            producer_step_id=step_id,
            upstream_digests=upstream_digests,
            created_at=_utc_now(),
            source_fetched_at=source_fetched_at,
            source_validated_at=source_validated_at,
            quality=quality,
            coverage=coverage,
            dependency_versions=_dependency_versions(),
        )
        manifest = _descriptor_payload(descriptor)
        manifest_path = staging / "manifest.json"
        with manifest_path.open("wb") as stream:
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(staging)
        _publish_staging_object(root, content_digest, staging)
        return descriptor, manifest
    except Exception:
        with suppress(FileNotFoundError):
            shutil.rmtree(staging)
        raise


def _publish_staging_object(root: Path, digest: str, staging: Path) -> None:
    """Atomically publish one staged object while tolerating equal writers."""
    object_path = root / "objects" / digest[:2] / digest
    object_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if object_path.exists():
        shutil.rmtree(staging)
    else:
        try:
            os.replace(staging, object_path)
        except OSError:
            if not object_path.exists():
                raise
            shutil.rmtree(staging)
        _fsync_directory(object_path.parent)


def _cleanup_orphans(root: Path, older_than: timedelta) -> int:
    """Remove stale staging directories from a worker thread."""
    cutoff = _utc_now().timestamp() - older_than.total_seconds()
    count = 0
    for path in (root / "staging").iterdir():
        if path.is_dir() and path.stat().st_mtime <= cutoff:
            shutil.rmtree(path)
            count += 1
    return count


def _with_analytics_metadata(
    table: pa.Table, contract: TableContract[BaseModel]
) -> pa.Table:
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            _CONTRACT_ID_KEY: contract.id.encode(),
            _CONTRACT_REVISION_KEY: str(contract.revision).encode(),
            _CONTRACT_SCHEMA_KEY: contract.schema_digest.encode(),
        }
    )
    return table.replace_schema_metadata(metadata)


def _assert_analytics_metadata(table: pa.Table, descriptor: ArtifactDescriptor) -> None:
    metadata = table.schema.metadata or {}
    expected = {
        _CONTRACT_ID_KEY: descriptor.contract_id.encode(),
        _CONTRACT_REVISION_KEY: str(descriptor.contract_revision).encode(),
        _CONTRACT_SCHEMA_KEY: descriptor.schema_digest.encode(),
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise CFBDArtifactError("Artifact table contract metadata is incompatible")


def _descriptor_payload(descriptor: ArtifactDescriptor) -> dict[str, object]:
    return {
        "format_version": descriptor.format_version,
        "artifact_id": descriptor.artifact_id,
        "kind": descriptor.kind,
        "codec_id": descriptor.codec_id,
        "codec_version": descriptor.codec_version,
        "media_type": descriptor.media_type,
        "content_digest": descriptor.content_digest,
        "byte_count": descriptor.byte_count,
        "row_count": descriptor.row_count,
        "contract_id": descriptor.contract_id,
        "contract_revision": descriptor.contract_revision,
        "schema_digest": descriptor.schema_digest,
        "grain": descriptor.grain,
        "keys": list(descriptor.keys),
        "order_by": list(descriptor.order_by),
        "partition_by": list(descriptor.partition_by),
        "event_time": descriptor.event_time,
        "columns": {
            name: {
                "description": metadata.description,
                "units": metadata.units,
                "semantic_type": metadata.semantic_type,
            }
            for name, metadata in descriptor.columns.items()
        },
        "parts": [
            {
                "name": part.name,
                "digest": part.digest,
                "byte_count": part.byte_count,
                "row_count": part.row_count,
            }
            for part in descriptor.parts
        ],
        "producer_definition_id": descriptor.producer_definition_id,
        "producer_definition_revision": descriptor.producer_definition_revision,
        "producer_step_id": descriptor.producer_step_id,
        "upstream_digests": list(descriptor.upstream_digests),
        "created_at": descriptor.created_at.isoformat(),
        "source_fetched_at": (
            descriptor.source_fetched_at.isoformat()
            if descriptor.source_fetched_at is not None
            else None
        ),
        "source_validated_at": (
            descriptor.source_validated_at.isoformat()
            if descriptor.source_validated_at is not None
            else None
        ),
        "quality": [
            {
                "check": item.check,
                "passed": item.passed,
                "affected_rows": item.affected_rows,
            }
            for item in descriptor.quality
        ],
        "coverage": [
            {
                "source_id": item.source_id,
                "state": item.state.value,
                "row_count": item.row_count,
            }
            for item in descriptor.coverage
        ],
        "dependency_versions": dict(descriptor.dependency_versions),
    }


def _descriptor_from_payload(payload: object) -> ArtifactDescriptor:
    if not isinstance(payload, dict):
        raise CFBDArtifactError("Artifact manifest must be a JSON object")
    try:
        parts_value = payload["parts"]
        quality_value = payload["quality"]
        coverage_value = payload["coverage"]
        columns_value = payload["columns"]
        dependency_versions_value = payload["dependency_versions"]
        if not isinstance(parts_value, list):
            raise TypeError
        if not isinstance(quality_value, list):
            raise TypeError
        if not isinstance(coverage_value, list):
            raise TypeError
        if not isinstance(columns_value, dict):
            raise TypeError
        if not isinstance(dependency_versions_value, dict):
            raise TypeError
        parts = tuple(
            ArtifactPart(
                name=str(item["name"]),
                digest=str(item["digest"]),
                byte_count=int(item["byte_count"]),
                row_count=(
                    int(item["row_count"]) if item["row_count"] is not None else None
                ),
            )
            for item in parts_value
            if isinstance(item, dict)
        )
        quality = tuple(
            QualityResult(
                check=str(item["check"]),
                passed=bool(item["passed"]),
                affected_rows=int(item["affected_rows"]),
            )
            for item in quality_value
            if isinstance(item, dict)
        )
        coverage = tuple(
            SourceCoverage(
                source_id=str(item["source_id"]),
                state=CoverageState(str(item["state"])),
                row_count=int(item["row_count"]),
            )
            for item in coverage_value
            if isinstance(item, dict)
        )
        source_fetched_at = payload["source_fetched_at"]
        source_validated_at = payload["source_validated_at"]
        row_count = payload["row_count"]
        grain = payload["grain"]
        event_time = payload["event_time"]
        return ArtifactDescriptor(
            format_version=int(payload["format_version"]),
            artifact_id=str(payload["artifact_id"]),
            kind=str(payload["kind"]),
            codec_id=str(payload["codec_id"]),
            codec_version=int(payload["codec_version"]),
            media_type=str(payload["media_type"]),
            content_digest=str(payload["content_digest"]),
            byte_count=int(payload["byte_count"]),
            row_count=int(row_count) if row_count is not None else None,
            contract_id=str(payload["contract_id"]),
            contract_revision=int(payload["contract_revision"]),
            schema_digest=str(payload["schema_digest"]),
            grain=str(grain) if grain is not None else None,
            keys=tuple(str(item) for item in payload["keys"]),
            order_by=tuple(str(item) for item in payload["order_by"]),
            partition_by=tuple(str(item) for item in payload["partition_by"]),
            event_time=str(event_time) if event_time is not None else None,
            columns={
                str(name): ColumnMetadata(
                    description=str(item["description"]),
                    units=str(item["units"]) if item["units"] is not None else None,
                    semantic_type=(
                        str(item["semantic_type"])
                        if item["semantic_type"] is not None
                        else None
                    ),
                )
                for name, item in columns_value.items()
                if isinstance(item, dict)
            },
            parts=parts,
            producer_definition_id=str(payload["producer_definition_id"]),
            producer_definition_revision=int(payload["producer_definition_revision"]),
            producer_step_id=str(payload["producer_step_id"]),
            upstream_digests=tuple(str(item) for item in payload["upstream_digests"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            source_fetched_at=(
                datetime.fromisoformat(str(source_fetched_at))
                if source_fetched_at is not None
                else None
            ),
            source_validated_at=(
                datetime.fromisoformat(str(source_validated_at))
                if source_validated_at is not None
                else None
            ),
            quality=quality,
            coverage=coverage,
            dependency_versions={
                str(name): str(version)
                for name, version in dependency_versions_value.items()
            },
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBDArtifactError("Artifact manifest is invalid") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _partition_tables(
    table: pa.Table, partition_by: tuple[str, ...]
) -> tuple[pa.Table, ...]:
    """Split a sorted canonical table into deterministic opaque parts."""
    if not partition_by or table.num_rows == 0:
        return (table,)
    columns = [table.column(name).to_pylist() for name in partition_by]
    groups: dict[bytes, list[int]] = {}
    for index in range(table.num_rows):
        key = canonical_json([_partition_value(column[index]) for column in columns])
        groups.setdefault(key, []).append(index)
    return tuple(
        table.take(pa.array(indices, type=pa.int64())) for indices in groups.values()
    )


def _partition_value(value: object) -> object:
    """Normalize one scalar partition value for deterministic grouping."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    raise CFBDArtifactError("Partition fields must contain scalar values")


def _dependency_versions() -> Mapping[str, str]:
    """Return bounded dependency evidence needed to audit an artifact."""
    return {
        "python": sys.version.split()[0],
        "narwhals": _package_version("narwhals"),
        "pandas": _package_version("pandas"),
        "pydantic": _package_version("pydantic"),
        "pyarrow": pa.__version__,
    }


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def _validate_list_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 through 1000")


def _run_descriptor(row: Sequence[object]) -> RunDescriptor:
    if len(row) != 10:
        raise CFBDArtifactError("Analytics run record is invalid")
    finished = row[7]
    return RunDescriptor(
        run_id=str(row[0]),
        definition_id=str(row[1]),
        definition_revision=int(str(row[2])),
        parameter_fingerprint=str(row[3]),
        parent_run_id=str(row[4]) if row[4] is not None else None,
        status=str(row[5]),
        started_at=datetime.fromisoformat(str(row[6])),
        finished_at=(
            datetime.fromisoformat(str(finished)) if finished is not None else None
        ),
        failure_step_id=str(row[8]) if row[8] is not None else None,
        failure_category=str(row[9]) if row[9] is not None else None,
    )


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if system() == "Windows":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _default_path() -> Path:
    if system() == "Darwin":
        return (
            Path.home() / "Library" / "Application Support" / "cfb-data" / "analytics"
        )
    if system() == "Windows":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "cfb-data" / "analytics"
        return Path.home() / "AppData" / "Local" / "cfb-data" / "analytics"
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "cfb-data" / "analytics"
    return Path.home() / ".local" / "share" / "cfb-data" / "analytics"


def _utc_now() -> datetime:
    return datetime.now(UTC)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analytics_runs (
    run_id TEXT PRIMARY KEY,
    definition_id TEXT NOT NULL,
    definition_revision INTEGER NOT NULL,
    parameter_fingerprint TEXT NOT NULL,
    parent_run_id TEXT REFERENCES analytics_runs(run_id),
    status TEXT NOT NULL CHECK(status IN ('running', 'success', 'error', 'cancelled')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    failure_step_id TEXT,
    failure_category TEXT
);

CREATE INDEX IF NOT EXISTS analytics_runs_recovery
ON analytics_runs(definition_id, parameter_fingerprint, status, started_at);

CREATE TABLE IF NOT EXISTS analytics_artifacts (
    artifact_id TEXT PRIMARY KEY,
    content_digest TEXT NOT NULL,
    kind TEXT NOT NULL,
    codec_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    contract_revision INTEGER NOT NULL,
    manifest_json TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    row_count INTEGER,
    created_at TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0, 1))
);

CREATE INDEX IF NOT EXISTS analytics_artifacts_digest
ON analytics_artifacts(content_digest);

CREATE TABLE IF NOT EXISTS analytics_nodes (
    run_id TEXT NOT NULL REFERENCES analytics_runs(run_id),
    step_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'success'),
    artifact_id TEXT NOT NULL REFERENCES analytics_artifacts(artifact_id),
    reused INTEGER NOT NULL CHECK(reused IN (0, 1)),
    completed_at TEXT NOT NULL,
    PRIMARY KEY(run_id, step_id)
);

CREATE INDEX IF NOT EXISTS analytics_nodes_compatibility
ON analytics_nodes(fingerprint, completed_at);

CREATE TABLE IF NOT EXISTS analytics_leases (
    fingerprint TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


__all__ = [
    "ArtifactDescriptor",
    "ArtifactPart",
    "ArtifactRef",
    "LocalArtifactStore",
    "StoredNode",
]
