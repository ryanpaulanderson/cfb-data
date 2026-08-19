"""Persist immutable analytics objects and append-only run evidence."""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from platformdirs import user_data_path

from ._artifacts import (
    _ArtifactManifest,
    _canonical_json_bytes,
    _read_manifest,
    _StagedArtifact,
    _verify_directory_members,
)
from .config import AnalyticsConfig
from .errors import CFBDArtifactCorruptionError, CFBDPersistenceError

type _RecipeKind = Literal["dataset", "workflow"]
type _RunState = Literal["created", "running", "completed", "failed", "cancelled"]
type _NodeState = Literal[
    "ready", "running", "reused", "completed", "failed", "cancelled"
]
type _SourceBehavior = Literal["preserve_snapshot", "normal_freshness", "refresh"]
type _Placement = Literal["coordinator", "local", "dask"]
type _CheckpointScope = Literal["none", "parent", "parent_then_global", "global"]

_DIGEST_CHARACTERS: Final = frozenset("0123456789abcdef")
_RUN_TRANSITIONS: Final[dict[_RunState, frozenset[_RunState]]] = {
    "created": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
_NODE_TRANSITIONS: Final[dict[_NodeState | None, frozenset[_NodeState]]] = {
    None: frozenset({"ready"}),
    "ready": frozenset({"running", "reused", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "reused": frozenset(),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class _StoredArtifact:
    """Identify one validated immutable object without exposing its path."""

    content_digest: str
    manifest: _ArtifactManifest


@dataclass(frozen=True, slots=True)
class _RunRecord:
    """Expose safe immutable run identity and current derived state."""

    run_id: str
    recipe_id: str
    recipe_revision: int | None
    recipe_kind: _RecipeKind
    parameter_fingerprint: str
    graph_fingerprint: str
    credential_scope: str
    parent_run_id: str | None
    source_behavior: _SourceBehavior
    created_at: datetime
    state: _RunState


@dataclass(frozen=True, slots=True)
class _NodeArtifactBinding:
    """Bind one successful node output to immutable content."""

    run_id: str
    node_id: str
    output_name: str
    node_fingerprint: str
    content_digest: str
    placement: _Placement
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class _CheckpointCandidate:
    """Identify one compatible previously committed node output."""

    binding: _NodeArtifactBinding
    manifest: _ArtifactManifest


def _analytics_root(config: AnalyticsConfig) -> Path:
    """Resolve an analytics root without creating or inspecting it.

    :param config: Lazy analytics configuration.
    :return: Explicit root or the operating system's application-data location.
    """
    if config.root is not None:
        return config.root
    return user_data_path("cfb-data", appauthor=False) / "analytics"


class _ArtifactObjectStore:
    """Own immutable content-addressed filesystem objects."""

    def __init__(self, root: Path) -> None:
        """Create store directories only when execution opens persistence."""
        self._root = root
        self._objects = root / "objects" / "sha256"
        _make_private_directory(root)
        _make_private_directory(root / "objects")
        _make_private_directory(self._objects)

    @contextmanager
    def staging_directory(self) -> Iterator[Path]:
        """Yield one store-owned sibling staging directory.

        :return: Empty directory removed unless atomically published.
        """
        bucket = self._objects / "staging"
        _make_private_directory(bucket)
        directory = bucket / f".stage-{uuid.uuid4().hex}"
        directory.mkdir(mode=0o700)
        published = False
        try:
            yield directory
            published = not directory.exists()
        finally:
            if not published and directory.exists():
                _remove_owned_staging(directory, bucket)

    def publish(self, staged: _StagedArtifact) -> _StoredArtifact:
        """Atomically publish a fully validated staged artifact.

        :param staged: Codec-validated content in a store-owned staging path.
        :return: Opaque immutable object identity.
        :raises CFBDPersistenceError: If staging ownership or publication fails.
        :raises CFBDArtifactCorruptionError: If staged or existing content is invalid.
        """
        manifest = _read_manifest(staged.directory)
        if manifest != staged.manifest:
            raise CFBDArtifactCorruptionError(
                content_digest=staged.manifest.content_digest,
                category="manifest",
            )
        _verify_directory_members(staged.directory, manifest)
        self._require_owned_staging(staged.directory)
        digest = manifest.content_digest
        destination = self._object_path(digest)
        _make_private_directory(destination.parent)
        _restrict_object_permissions(staged.directory)
        _flush_directory(staged.directory)
        try:
            os.rename(staged.directory, destination)
            _flush_directory(destination.parent)
        except FileExistsError:
            existing = self.load_manifest(digest)
            if existing != manifest:
                raise CFBDArtifactCorruptionError(
                    content_digest=digest,
                    category="collision",
                ) from None
            _remove_owned_staging(staged.directory, staged.directory.parent)
        except OSError as exc:
            if destination.exists():
                existing = self.load_manifest(digest)
                if existing == manifest:
                    _remove_owned_staging(staged.directory, staged.directory.parent)
                else:
                    raise CFBDArtifactCorruptionError(
                        content_digest=digest,
                        category="collision",
                    ) from exc
            else:
                raise CFBDPersistenceError(category="artifact_publish") from exc
        restored = self.load_manifest(digest)
        if restored != manifest:
            raise CFBDArtifactCorruptionError(
                content_digest=digest,
                category="publish",
            )
        return _StoredArtifact(content_digest=digest, manifest=restored)

    def load_manifest(self, content_digest: str) -> _ArtifactManifest:
        """Read and validate one immutable object's canonical manifest."""
        directory = self._object_path(content_digest)
        manifest = _read_manifest(directory)
        if manifest.content_digest != content_digest:
            raise CFBDArtifactCorruptionError(
                content_digest=content_digest,
                category="identity",
            )
        _verify_directory_members(directory, manifest)
        return manifest

    def directory(self, content_digest: str) -> Path:
        """Return an internal codec path after validating the object identity."""
        self.load_manifest(content_digest)
        return self._object_path(content_digest)

    def _object_path(self, content_digest: str) -> Path:
        if len(content_digest) != 64 or any(
            character not in _DIGEST_CHARACTERS for character in content_digest
        ):
            raise CFBDArtifactCorruptionError(
                content_digest=None,
                category="identity",
            )
        return self._objects / content_digest[:2] / content_digest

    def _require_owned_staging(self, directory: Path) -> None:
        expected_parent = self._objects / "staging"
        if (
            directory.parent != expected_parent
            or not directory.name.startswith(".stage-")
            or not directory.is_dir()
        ):
            raise CFBDPersistenceError(category="staging_ownership")


class _RunDatabase:
    """Own append-only SQLite run, node, and artifact-binding evidence."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Open and migrate the run database with durable settings."""
        _make_private_directory(path.parent)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                path,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute("PRAGMA busy_timeout = 30000")
            self._migrate()
            os.chmod(path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise CFBDPersistenceError(category="database_open") from exc

    def close(self) -> None:
        """Close the owned database connection deterministically."""
        with self._lock:
            self._connection.close()

    def create_run(
        self,
        *,
        recipe_id: str,
        recipe_revision: int | None,
        recipe_kind: _RecipeKind,
        parameter_fingerprint: str,
        graph_fingerprint: str,
        credential_scope: str,
        parent_run_id: str | None = None,
        source_behavior: _SourceBehavior = "normal_freshness",
    ) -> _RunRecord:
        """Create one immutable run identity and initial transition."""
        run_id = uuid.uuid4().hex
        created_at = _as_utc(self._clock())
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, recipe_id, recipe_revision, recipe_kind,
                    parameter_fingerprint, graph_fingerprint, parent_run_id,
                    credential_scope, source_behavior, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    recipe_id,
                    recipe_revision,
                    recipe_kind,
                    parameter_fingerprint,
                    graph_fingerprint,
                    parent_run_id,
                    credential_scope,
                    source_behavior,
                    created_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO run_transitions (run_id, state, occurred_at)
                VALUES (?, 'created', ?)
                """,
                (run_id, created_at.isoformat()),
            )
        return self.get_run(run_id)

    def transition_run(
        self,
        run_id: str,
        state: _RunState,
        *,
        node_id: str | None = None,
        failure_category: str | None = None,
    ) -> _RunRecord:
        """Append one valid run state transition."""
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            current = self._current_run_state(connection, run_id)
            if state not in _RUN_TRANSITIONS[current]:
                raise CFBDPersistenceError(category="run_transition")
            connection.execute(
                """
                INSERT INTO run_transitions (
                    run_id, state, occurred_at, node_id, failure_category
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    state,
                    occurred_at.isoformat(),
                    node_id,
                    failure_category,
                ),
            )
        return self.get_run(run_id)

    def transition_node(
        self,
        run_id: str,
        node_id: str,
        state: _NodeState,
        *,
        failure_category: str | None = None,
    ) -> None:
        """Append one valid node state transition."""
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            row = connection.execute(
                """
                SELECT state FROM node_transitions
                WHERE run_id = ? AND node_id = ?
                ORDER BY transition_id DESC LIMIT 1
                """,
                (run_id, node_id),
            ).fetchone()
            current = None if row is None else _node_state(row["state"])
            if state not in _NODE_TRANSITIONS[current]:
                raise CFBDPersistenceError(category="node_transition")
            connection.execute(
                """
                INSERT INTO node_transitions (
                    run_id, node_id, state, occurred_at, failure_category
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    node_id,
                    state,
                    occurred_at.isoformat(),
                    failure_category,
                ),
            )

    def bind_completed_node(
        self,
        *,
        run_id: str,
        node_id: str,
        output_name: str,
        node_fingerprint: str,
        artifact: _StoredArtifact,
        placement: _Placement,
    ) -> _NodeArtifactBinding:
        """Commit artifact registration, binding, and node success last."""
        committed_at = _as_utc(self._clock())
        manifest_payload = _canonical_json_bytes(
            artifact.manifest.model_dump(mode="json")
        ).decode("utf-8")
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            row = connection.execute(
                "SELECT manifest_json FROM artifact_objects WHERE content_digest = ?",
                (artifact.content_digest,),
            ).fetchone()
            if row is not None and row["manifest_json"] != manifest_payload:
                raise CFBDArtifactCorruptionError(
                    content_digest=artifact.content_digest,
                    category="database_collision",
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO artifact_objects (
                    content_digest, kind, codec_id, codec_version,
                    manifest_json, first_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.content_digest,
                    artifact.manifest.body.kind,
                    artifact.manifest.body.codec_id,
                    artifact.manifest.body.codec_version,
                    manifest_payload,
                    committed_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO node_artifact_bindings (
                    run_id, node_id, output_name, node_fingerprint,
                    content_digest, placement, committed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    node_id,
                    output_name,
                    node_fingerprint,
                    artifact.content_digest,
                    placement,
                    committed_at.isoformat(),
                ),
            )
            current = connection.execute(
                """
                SELECT state FROM node_transitions
                WHERE run_id = ? AND node_id = ?
                ORDER BY transition_id DESC LIMIT 1
                """,
                (run_id, node_id),
            ).fetchone()
            if current is None or current["state"] != "running":
                raise CFBDPersistenceError(category="node_transition")
            connection.execute(
                """
                INSERT INTO node_transitions (
                    run_id, node_id, state, occurred_at
                ) VALUES (?, ?, 'completed', ?)
                """,
                (run_id, node_id, committed_at.isoformat()),
            )
        return _NodeArtifactBinding(
            run_id=run_id,
            node_id=node_id,
            output_name=output_name,
            node_fingerprint=node_fingerprint,
            content_digest=artifact.content_digest,
            placement=placement,
            committed_at=committed_at,
        )

    def get_run(self, run_id: str) -> _RunRecord:
        """Return one safe immutable run with its derived latest state."""
        with self._lock:
            row = self._connection.execute(
                """
                SELECT r.*, t.state
                FROM runs AS r
                JOIN run_transitions AS t
                  ON t.transition_id = (
                    SELECT MAX(t2.transition_id)
                    FROM run_transitions AS t2
                    WHERE t2.run_id = r.run_id
                  )
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")
        return _run_record(row)

    def bindings(self, run_id: str) -> tuple[_NodeArtifactBinding, ...]:
        """Return successful artifact bindings in commit order."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM node_artifact_bindings
                WHERE run_id = ? ORDER BY binding_id
                """,
                (run_id,),
            ).fetchall()
        return tuple(_binding(row) for row in rows)

    def find_checkpoint(
        self,
        *,
        node_fingerprint: str,
        output_name: str,
        scope: _CheckpointScope,
        parent_run_id: str | None,
        credential_scope: str,
    ) -> _CheckpointCandidate | None:
        """Find compatible content under an explicit freshness-safe scope."""
        if scope == "none":
            return None
        with self._lock:
            row: sqlite3.Row | None = None
            if scope in {"parent", "parent_then_global"}:
                if parent_run_id is None:
                    raise CFBDPersistenceError(category="checkpoint_scope")
                row = self._connection.execute(
                    """
                    WITH RECURSIVE ancestry(run_id, parent_run_id, depth) AS (
                        SELECT run_id, parent_run_id, 0
                        FROM runs WHERE run_id = ?
                        UNION ALL
                        SELECT parent.run_id, parent.parent_run_id, ancestry.depth + 1
                        FROM runs AS parent
                        JOIN ancestry ON parent.run_id = ancestry.parent_run_id
                    )
                    SELECT binding.*, object.manifest_json
                    FROM ancestry
                    JOIN runs AS run ON run.run_id = ancestry.run_id
                    JOIN node_artifact_bindings AS binding
                      ON binding.run_id = ancestry.run_id
                    JOIN artifact_objects AS object
                      ON object.content_digest = binding.content_digest
                    WHERE binding.node_fingerprint = ?
                      AND binding.output_name = ?
                      AND run.credential_scope = ?
                    ORDER BY ancestry.depth, binding.binding_id DESC
                    LIMIT 1
                    """,
                    (
                        parent_run_id,
                        node_fingerprint,
                        output_name,
                        credential_scope,
                    ),
                ).fetchone()
            if row is None and scope in {"global", "parent_then_global"}:
                row = self._connection.execute(
                    """
                    SELECT binding.*, object.manifest_json
                    FROM node_artifact_bindings AS binding
                    JOIN runs AS run ON run.run_id = binding.run_id
                    JOIN artifact_objects AS object
                      ON object.content_digest = binding.content_digest
                    WHERE binding.node_fingerprint = ?
                      AND binding.output_name = ?
                      AND run.credential_scope = ?
                    ORDER BY binding.binding_id DESC
                    LIMIT 1
                    """,
                    (node_fingerprint, output_name, credential_scope),
                ).fetchone()
        if row is None:
            return None
        try:
            manifest = _ArtifactManifest.model_validate_json(
                str(row["manifest_json"]),
                strict=True,
            )
        except ValueError as exc:
            raise CFBDArtifactCorruptionError(
                content_digest=str(row["content_digest"]),
                category="database_manifest",
            ) from exc
        return _CheckpointCandidate(binding=_binding(row), manifest=manifest)

    def node_state(self, run_id: str, node_id: str) -> _NodeState | None:
        """Return the latest node state without mutating durable evidence."""
        with self._lock:
            row = self._connection.execute(
                """
                SELECT state FROM node_transitions
                WHERE run_id = ? AND node_id = ?
                ORDER BY transition_id DESC LIMIT 1
                """,
                (run_id, node_id),
            ).fetchone()
        return None if row is None else _node_state(row["state"])

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _current_run_state(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> _RunState:
        row = connection.execute(
            """
            SELECT state FROM run_transitions
            WHERE run_id = ? ORDER BY transition_id DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")
        return _run_state(row["state"])

    def _require_run(self, connection: sqlite3.Connection, run_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")

    def _migrate(self) -> None:
        with self._lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1, 2}:
                raise CFBDPersistenceError(category="database_version")
            if version == 2:
                return
            migration = _SCHEMA_V1 if version == 0 else _SCHEMA_V2
            target_version = 1 if version == 0 else 2
            try:
                self._connection.executescript(
                    f"BEGIN IMMEDIATE;\n{migration}\n"
                    f"PRAGMA user_version = {target_version};\nCOMMIT;"
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            if target_version == 1:
                self._migrate()


def _run_record(row: sqlite3.Row) -> _RunRecord:
    """Validate one SQLite row into a safe run record."""
    revision_value = row["recipe_revision"]
    return _RunRecord(
        run_id=str(row["run_id"]),
        recipe_id=str(row["recipe_id"]),
        recipe_revision=None if revision_value is None else int(revision_value),
        recipe_kind=_recipe_kind(row["recipe_kind"]),
        parameter_fingerprint=str(row["parameter_fingerprint"]),
        graph_fingerprint=str(row["graph_fingerprint"]),
        credential_scope=str(row["credential_scope"]),
        parent_run_id=(
            None if row["parent_run_id"] is None else str(row["parent_run_id"])
        ),
        source_behavior=_source_behavior(row["source_behavior"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        state=_run_state(row["state"]),
    )


def _binding(row: sqlite3.Row) -> _NodeArtifactBinding:
    """Validate one SQLite row into an artifact binding."""
    return _NodeArtifactBinding(
        run_id=str(row["run_id"]),
        node_id=str(row["node_id"]),
        output_name=str(row["output_name"]),
        node_fingerprint=str(row["node_fingerprint"]),
        content_digest=str(row["content_digest"]),
        placement=_placement(row["placement"]),
        committed_at=datetime.fromisoformat(str(row["committed_at"])),
    )


def _run_state(value: object) -> _RunState:
    if value not in _RUN_TRANSITIONS:
        raise CFBDPersistenceError(category="database_value")
    return value


def _node_state(value: object) -> _NodeState:
    if value not in _NODE_TRANSITIONS or value is None:
        raise CFBDPersistenceError(category="database_value")
    return value


def _recipe_kind(value: object) -> _RecipeKind:
    if value not in {"dataset", "workflow"}:
        raise CFBDPersistenceError(category="database_value")
    return value


def _source_behavior(value: object) -> _SourceBehavior:
    if value not in {"preserve_snapshot", "normal_freshness", "refresh"}:
        raise CFBDPersistenceError(category="database_value")
    return value


def _placement(value: object) -> _Placement:
    if value not in {"coordinator", "local", "dask"}:
        raise CFBDPersistenceError(category="database_value")
    return value


def _as_utc(value: datetime) -> datetime:
    """Require an aware clock value and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise CFBDPersistenceError(category="clock")
    return value.astimezone(UTC)


def _make_private_directory(path: Path) -> None:
    """Create one private directory and tighten existing permissions."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _restrict_object_permissions(directory: Path) -> None:
    """Apply private immutable-object permissions before publication."""
    for path in directory.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
        else:
            raise CFBDPersistenceError(category="artifact_member")
    os.chmod(directory, 0o700)


def _flush_directory(path: Path) -> None:
    """Flush directory entry changes to durable storage."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_owned_staging(directory: Path, expected_parent: Path) -> None:
    """Remove only a validated store-owned staging directory."""
    if directory.parent != expected_parent or not directory.name.startswith(".stage-"):
        raise CFBDPersistenceError(category="staging_ownership")
    shutil.rmtree(directory)


_SCHEMA_V1: Final = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL,
    recipe_revision INTEGER,
    recipe_kind TEXT NOT NULL CHECK (recipe_kind IN ('dataset', 'workflow')),
    parameter_fingerprint TEXT NOT NULL,
    graph_fingerprint TEXT NOT NULL,
    parent_run_id TEXT REFERENCES runs(run_id),
    source_behavior TEXT NOT NULL CHECK (
        source_behavior IN ('preserve_snapshot', 'normal_freshness', 'refresh')
    ),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE run_transitions (
    transition_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    state TEXT NOT NULL CHECK (
        state IN ('created', 'running', 'completed', 'failed', 'cancelled')
    ),
    occurred_at TEXT NOT NULL,
    node_id TEXT,
    failure_category TEXT
) STRICT;
CREATE INDEX run_transitions_by_run
    ON run_transitions(run_id, transition_id);

CREATE TABLE node_transitions (
    transition_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('ready', 'running', 'reused', 'completed', 'failed', 'cancelled')
    ),
    occurred_at TEXT NOT NULL,
    failure_category TEXT
) STRICT;
CREATE INDEX node_transitions_by_node
    ON node_transitions(run_id, node_id, transition_id);

CREATE TABLE artifact_objects (
    content_digest TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    codec_id TEXT NOT NULL,
    codec_version INTEGER NOT NULL,
    manifest_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
) STRICT;

CREATE TABLE node_artifact_bindings (
    binding_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    node_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    node_fingerprint TEXT NOT NULL,
    content_digest TEXT NOT NULL REFERENCES artifact_objects(content_digest),
    placement TEXT NOT NULL CHECK (placement IN ('coordinator', 'local', 'dask')),
    committed_at TEXT NOT NULL,
    UNIQUE (run_id, node_id, output_name)
) STRICT;
CREATE INDEX bindings_by_content
    ON node_artifact_bindings(content_digest);

CREATE TRIGGER runs_are_immutable_update
BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable'); END;
CREATE TRIGGER runs_are_immutable_delete
BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'runs are immutable'); END;
CREATE TRIGGER run_transitions_are_immutable_update
BEFORE UPDATE ON run_transitions
BEGIN SELECT RAISE(ABORT, 'run transitions are immutable'); END;
CREATE TRIGGER run_transitions_are_immutable_delete
BEFORE DELETE ON run_transitions
BEGIN SELECT RAISE(ABORT, 'run transitions are immutable'); END;
CREATE TRIGGER node_transitions_are_immutable_update
BEFORE UPDATE ON node_transitions
BEGIN SELECT RAISE(ABORT, 'node transitions are immutable'); END;
CREATE TRIGGER node_transitions_are_immutable_delete
BEFORE DELETE ON node_transitions
BEGIN SELECT RAISE(ABORT, 'node transitions are immutable'); END;
CREATE TRIGGER artifact_objects_are_immutable_update
BEFORE UPDATE ON artifact_objects
BEGIN SELECT RAISE(ABORT, 'artifact objects are immutable'); END;
CREATE TRIGGER artifact_objects_are_immutable_delete
BEFORE DELETE ON artifact_objects
BEGIN SELECT RAISE(ABORT, 'artifact objects are immutable'); END;
CREATE TRIGGER bindings_are_immutable_update
BEFORE UPDATE ON node_artifact_bindings
BEGIN SELECT RAISE(ABORT, 'bindings are immutable'); END;
CREATE TRIGGER bindings_are_immutable_delete
BEFORE DELETE ON node_artifact_bindings
BEGIN SELECT RAISE(ABORT, 'bindings are immutable'); END;
"""

_SCHEMA_V2: Final = """
ALTER TABLE runs ADD COLUMN credential_scope TEXT NOT NULL DEFAULT '';
"""


__all__: Sequence[str] = ()
