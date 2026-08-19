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
from typing import Final, Literal, cast

from platformdirs import user_data_path

from ._artifacts import (
    _ArtifactManifest,
    _canonical_json_bytes,
    _read_manifest,
    _StagedArtifact,
    _verify_directory_members,
)
from ._compiler import _digest
from ._sqlite_sql import AnalyticsSQLiteSQL
from .config import AnalyticsConfig
from .errors import (
    CFBDArtifactCorruptionError,
    CFBDAttemptBudgetExceeded,
    CFBDPersistenceError,
)

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
    max_http_attempts: int
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
    checkpoint_eligible: bool
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class _CheckpointCandidate:
    """Identify one compatible previously committed node output."""

    binding: _NodeArtifactBinding
    manifest: _ArtifactManifest


@dataclass(frozen=True, slots=True)
class _PruneCandidate:
    """Describe one unreferenced and unpinned immutable object."""

    content_digest: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _PrunePlan:
    """Bind a dry-run candidate snapshot to validation evidence."""

    candidates: tuple[_PruneCandidate, ...]
    validation_digest: str


@dataclass(frozen=True, slots=True)
class _OrphanCleanupPlan:
    """Bind unregistered immutable objects to validation evidence."""

    candidates: tuple[_PruneCandidate, ...]
    validation_digest: str


@dataclass(frozen=True, slots=True)
class _AttemptReservationRecord:
    """Expose safe durable evidence for one actual transport attempt."""

    run_id: str
    node_id: str
    endpoint: str
    retry_number: int
    ordinal: int
    reserved_at: datetime


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

    def __init__(self, root: Path, *, create: bool = True) -> None:
        """Open the object store, optionally creating execution directories."""
        self._root = root
        self._objects = root / "objects" / "sha256"
        if create:
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

    def remove(self, content_digest: str) -> None:
        """Remove one validated immutable object through a recoverable rename."""
        source = self.directory(content_digest)
        trash = (
            self._objects / "staging" / f".trash-{content_digest}-{uuid.uuid4().hex}"
        )
        _make_private_directory(trash.parent)
        try:
            os.rename(source, trash)
            _flush_directory(source.parent)
            _flush_directory(trash.parent)
            shutil.rmtree(trash)
            _flush_directory(trash.parent)
        except OSError as exc:
            raise CFBDPersistenceError(category="artifact_remove") from exc

    def published_artifacts(self) -> tuple[_StoredArtifact, ...]:
        """Return every validated published object in deterministic order."""
        if not self._objects.exists():
            return ()
        artifacts: list[_StoredArtifact] = []
        for bucket in sorted(self._objects.iterdir(), key=lambda path: path.name):
            if bucket.name == "staging":
                continue
            if (
                bucket.is_symlink()
                or not bucket.is_dir()
                or len(bucket.name) != 2
                or any(character not in _DIGEST_CHARACTERS for character in bucket.name)
            ):
                raise CFBDArtifactCorruptionError(
                    content_digest=None,
                    category="object_layout",
                )
            for directory in sorted(bucket.iterdir(), key=lambda path: path.name):
                if (
                    directory.is_symlink()
                    or not directory.is_dir()
                    or len(directory.name) != 64
                    or not directory.name.startswith(bucket.name)
                    or any(
                        character not in _DIGEST_CHARACTERS
                        for character in directory.name
                    )
                ):
                    raise CFBDArtifactCorruptionError(
                        content_digest=None,
                        category="object_layout",
                    )
                artifacts.append(
                    _StoredArtifact(
                        content_digest=directory.name,
                        manifest=self.load_manifest(directory.name),
                    )
                )
        return tuple(artifacts)

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


class _RunDatabaseQueries:
    """Share non-mutating run queries across reader and writer connections."""

    _connection: sqlite3.Connection
    _lock: threading.RLock
    _sql: AnalyticsSQLiteSQL

    def get_run(self, run_id: str) -> _RunRecord:
        """Return one safe immutable run with its derived latest state."""
        with self._lock:
            row = self._connection.execute(
                self._sql.render("runs/select_run.sql"),
                (run_id,),
            ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")
        return _run_record(row)

    def bindings(self, run_id: str) -> tuple[_NodeArtifactBinding, ...]:
        """Return successful artifact bindings in commit order."""
        self.get_run(run_id)
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("nodes/select_bindings.sql"),
                (run_id,),
            ).fetchall()
        return tuple(_binding(row) for row in rows)

    def attempt_count(self, run_id: str) -> int:
        """Return the exact durable actual-attempt count for one run."""
        self.get_run(run_id)
        with self._lock:
            row = self._connection.execute(
                self._sql.render("attempts/count_by_run.sql"),
                (run_id,),
            ).fetchone()
        if row is None:
            raise AssertionError("Attempt reservation count is missing")
        return int(row["count"])

    def plan_prune(self) -> _PrunePlan:
        """Return a non-mutating snapshot of eligible registered objects."""
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("artifacts/select_eligible_for_prune.sql")
            ).fetchall()
        candidates = tuple(
            _PruneCandidate(
                content_digest=str(row["content_digest"]),
                size_bytes=_manifest_size(str(row["manifest_json"])),
            )
            for row in rows
        )
        return _PrunePlan(
            candidates=candidates,
            validation_digest=_prune_validation_digest(candidates),
        )

    def registered_artifact_digests(self) -> frozenset[str]:
        """Return all registered object identities without filesystem access."""
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("artifacts/select_registered_digests.sql")
            ).fetchall()
        return frozenset(str(row["content_digest"]) for row in rows)

    def plan_orphan_cleanup(
        self,
        *,
        object_store: _ArtifactObjectStore,
    ) -> _OrphanCleanupPlan:
        """Return validated published objects absent from the run database."""
        registered = self.registered_artifact_digests()
        candidates = tuple(
            _PruneCandidate(
                content_digest=artifact.content_digest,
                size_bytes=sum(
                    part.size_bytes for part in artifact.manifest.body.parts
                ),
            )
            for artifact in object_store.published_artifacts()
            if artifact.content_digest not in registered
        )
        return _OrphanCleanupPlan(
            candidates=candidates,
            validation_digest=_orphan_validation_digest(candidates),
        )


class _RunDatabase(_RunDatabaseQueries):
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
        self._sql = AnalyticsSQLiteSQL()
        try:
            self._connection = sqlite3.connect(
                path,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute(self._sql.render("config/enable_foreign_keys.sql"))
            self._connection.execute(self._sql.render("config/set_journal_delete.sql"))
            self._connection.execute(
                self._sql.render("config/set_synchronous_full.sql")
            )
            self._connection.execute(self._sql.render("config/set_busy_timeout.sql"))
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
        max_http_attempts: int = 100,
        parent_run_id: str | None = None,
        source_behavior: _SourceBehavior = "normal_freshness",
    ) -> _RunRecord:
        """Create one immutable run identity and initial transition."""
        if (
            not isinstance(max_http_attempts, int)
            or isinstance(max_http_attempts, bool)
            or max_http_attempts < 1
        ):
            raise ValueError("max_http_attempts must be a positive integer")
        run_id = uuid.uuid4().hex
        created_at = _as_utc(self._clock())
        with self._transaction() as connection:
            connection.execute(
                self._sql.render("runs/insert_run.sql"),
                (
                    run_id,
                    recipe_id,
                    recipe_revision,
                    recipe_kind,
                    parameter_fingerprint,
                    graph_fingerprint,
                    parent_run_id,
                    credential_scope,
                    max_http_attempts,
                    source_behavior,
                    created_at.isoformat(),
                ),
            )
            connection.execute(
                self._sql.render("runs/insert_transition.sql"),
                (run_id, "created", created_at.isoformat(), None, None),
            )
            connection.execute(
                self._sql.render("runs/insert_retention_transition.sql"),
                (run_id, "active", created_at.isoformat()),
            )
        return self.get_run(run_id)

    def reserve_attempt(
        self,
        *,
        run_id: str,
        node_id: str,
        endpoint: str,
        retry_number: int,
    ) -> _AttemptReservationRecord:
        """Durably reserve one actual attempt before transport dispatch."""
        if retry_number < 1:
            raise ValueError("retry_number must be positive")
        reserved_at = _as_utc(self._clock())
        with self._transaction() as connection:
            current = self._current_run_state(connection, run_id)
            if current != "running":
                raise CFBDPersistenceError(category="attempt_run_state")
            run = connection.execute(
                self._sql.render("runs/select_attempt_limit.sql"),
                (run_id,),
            ).fetchone()
            if run is None:
                raise CFBDPersistenceError(category="run_missing")
            limit = int(run["max_http_attempts"])
            count_row = connection.execute(
                self._sql.render("attempts/count_by_run.sql"),
                (run_id,),
            ).fetchone()
            if count_row is None:
                raise AssertionError("Attempt reservation count is missing")
            ordinal = int(count_row["count"]) + 1
            if ordinal > limit:
                raise CFBDAttemptBudgetExceeded(
                    run_id=run_id,
                    node_id=node_id,
                    limit=limit,
                )
            connection.execute(
                self._sql.render("attempts/insert_reservation.sql"),
                (
                    run_id,
                    node_id,
                    endpoint,
                    retry_number,
                    ordinal,
                    reserved_at.isoformat(),
                ),
            )
        return _AttemptReservationRecord(
            run_id=run_id,
            node_id=node_id,
            endpoint=endpoint,
            retry_number=retry_number,
            ordinal=ordinal,
            reserved_at=reserved_at,
        )

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
                self._sql.render("runs/insert_transition.sql"),
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
                self._sql.render("nodes/select_current_state.sql"),
                (run_id, node_id),
            ).fetchone()
            current = None if row is None else _node_state(row["state"])
            if state not in _NODE_TRANSITIONS[current]:
                raise CFBDPersistenceError(category="node_transition")
            connection.execute(
                self._sql.render("nodes/insert_transition.sql"),
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
        checkpoint_eligible: bool = True,
    ) -> _NodeArtifactBinding:
        """Commit artifact registration, binding, and node success last."""
        return self.bind_completed_outputs(
            run_id=run_id,
            node_id=node_id,
            outputs=((output_name, node_fingerprint, artifact, placement),),
            checkpoint_eligible=checkpoint_eligible,
        )[0]

    def publish_completed_node(
        self,
        *,
        run_id: str,
        node_id: str,
        output_name: str,
        node_fingerprint: str,
        staged: _StagedArtifact,
        object_store: _ArtifactObjectStore,
        placement: _Placement,
        checkpoint_eligible: bool = True,
    ) -> tuple[_StoredArtifact, _NodeArtifactBinding]:
        """Publish content and commit its successful node binding atomically.

        The database write reservation is acquired before filesystem publication.
        A crash can leave an unregistered immutable object, but no concurrent
        cleanup can mistake the publish-to-bind interval for an abandoned object.
        """
        committed_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            current = connection.execute(
                self._sql.render("nodes/select_current_state.sql"),
                (run_id, node_id),
            ).fetchone()
            if current is None or current["state"] != "running":
                raise CFBDPersistenceError(category="node_transition")
            artifact = object_store.publish(staged)
            binding = self._bind_completed_outputs(
                connection,
                run_id=run_id,
                node_id=node_id,
                outputs=((output_name, node_fingerprint, artifact, placement),),
                committed_at=committed_at,
                checkpoint_eligible=checkpoint_eligible,
            )[0]
        return artifact, binding

    def bind_completed_outputs(
        self,
        *,
        run_id: str,
        node_id: str,
        outputs: Sequence[tuple[str, str, _StoredArtifact, _Placement]],
        checkpoint_eligible: bool = True,
    ) -> tuple[_NodeArtifactBinding, ...]:
        """Commit named artifact bindings and node success in one transaction."""
        _validate_completed_outputs(outputs)
        committed_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            current = connection.execute(
                self._sql.render("nodes/select_current_state.sql"),
                (run_id, node_id),
            ).fetchone()
            if current is None or current["state"] != "running":
                raise CFBDPersistenceError(category="node_transition")
            return self._bind_completed_outputs(
                connection,
                run_id=run_id,
                node_id=node_id,
                outputs=outputs,
                committed_at=committed_at,
                checkpoint_eligible=checkpoint_eligible,
            )

    def _bind_completed_outputs(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        node_id: str,
        outputs: Sequence[tuple[str, str, _StoredArtifact, _Placement]],
        committed_at: datetime,
        checkpoint_eligible: bool,
    ) -> tuple[_NodeArtifactBinding, ...]:
        """Bind validated outputs and append success inside one owned transaction."""
        _validate_completed_outputs(outputs)
        for output_name, node_fingerprint, artifact, placement in outputs:
            manifest_payload = _canonical_json_bytes(
                artifact.manifest.model_dump(mode="json")
            ).decode("utf-8")
            self._require_artifact_not_retired(
                connection,
                artifact.content_digest,
            )
            row = connection.execute(
                self._sql.render("artifacts/select_manifest.sql"),
                (artifact.content_digest,),
            ).fetchone()
            if row is not None and row["manifest_json"] != manifest_payload:
                raise CFBDArtifactCorruptionError(
                    content_digest=artifact.content_digest,
                    category="database_collision",
                )
            connection.execute(
                self._sql.render("artifacts/insert_object.sql"),
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
                self._sql.render("nodes/insert_binding.sql"),
                (
                    run_id,
                    node_id,
                    output_name,
                    node_fingerprint,
                    artifact.content_digest,
                    placement,
                    int(checkpoint_eligible),
                    committed_at.isoformat(),
                ),
            )
        connection.execute(
            self._sql.render("nodes/insert_transition.sql"),
            (run_id, node_id, "completed", committed_at.isoformat(), None),
        )
        return tuple(
            _NodeArtifactBinding(
                run_id=run_id,
                node_id=node_id,
                output_name=output_name,
                node_fingerprint=node_fingerprint,
                content_digest=artifact.content_digest,
                placement=placement,
                checkpoint_eligible=checkpoint_eligible,
                committed_at=committed_at,
            )
            for output_name, node_fingerprint, artifact, placement in outputs
        )

    def bind_reused_node(
        self,
        *,
        run_id: str,
        node_id: str,
        output_name: str,
        node_fingerprint: str,
        candidate: _CheckpointCandidate,
        checkpoint_eligible: bool = True,
    ) -> _NodeArtifactBinding:
        """Bind compatible existing content and record terminal reuse."""
        committed_at = _as_utc(self._clock())
        binding = candidate.binding
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            self._require_registered_artifact(connection, binding.content_digest)
            self._require_artifact_not_retired(connection, binding.content_digest)
            current = connection.execute(
                self._sql.render("nodes/select_current_state.sql"),
                (run_id, node_id),
            ).fetchone()
            if current is None or current["state"] != "ready":
                raise CFBDPersistenceError(category="node_transition")
            connection.execute(
                self._sql.render("nodes/insert_binding.sql"),
                (
                    run_id,
                    node_id,
                    output_name,
                    node_fingerprint,
                    binding.content_digest,
                    binding.placement,
                    int(checkpoint_eligible),
                    committed_at.isoformat(),
                ),
            )
            connection.execute(
                self._sql.render("nodes/insert_transition.sql"),
                (run_id, node_id, "reused", committed_at.isoformat(), None),
            )
        return _NodeArtifactBinding(
            run_id=run_id,
            node_id=node_id,
            output_name=output_name,
            node_fingerprint=node_fingerprint,
            content_digest=binding.content_digest,
            placement=binding.placement,
            checkpoint_eligible=checkpoint_eligible,
            committed_at=committed_at,
        )

    def retire_run(self, run_id: str) -> None:
        """Retire a run's retention claim without deleting its audit record."""
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            state = self._run_retention_state(connection, run_id)
            if state != "active":
                raise CFBDPersistenceError(category="retention_transition")
            connection.execute(
                self._sql.render("runs/insert_retention_transition.sql"),
                (run_id, "retired", occurred_at.isoformat()),
            )

    def retain_run(self, run_id: str) -> None:
        """Restore a retired run's retention claim if its objects still exist."""
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            if self._run_retention_state(connection, run_id) != "retired":
                raise CFBDPersistenceError(category="retention_transition")
            unavailable = connection.execute(
                self._sql.render("runs/select_unavailable_retained_content.sql"),
                (run_id,),
            ).fetchone()
            if unavailable is not None:
                raise CFBDPersistenceError(category="retention_content_missing")
            connection.execute(
                self._sql.render("runs/insert_retention_transition.sql"),
                (run_id, "active", occurred_at.isoformat()),
            )

    def pin_artifact(self, content_digest: str, *, name: str) -> None:
        """Append an explicit named pin for an available artifact."""
        _validate_pin_name(name)
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            self._require_registered_artifact(connection, content_digest)
            self._require_artifact_not_retired(connection, content_digest)
            if self._pin_state(connection, content_digest, name) == "pinned":
                raise CFBDPersistenceError(category="pin_transition")
            connection.execute(
                self._sql.render("artifacts/insert_pin_transition.sql"),
                (content_digest, name, "pinned", occurred_at.isoformat()),
            )

    def unpin_artifact(self, content_digest: str, *, name: str) -> None:
        """Append removal of an existing named artifact pin."""
        _validate_pin_name(name)
        occurred_at = _as_utc(self._clock())
        with self._transaction() as connection:
            if self._pin_state(connection, content_digest, name) != "pinned":
                raise CFBDPersistenceError(category="pin_transition")
            connection.execute(
                self._sql.render("artifacts/insert_pin_transition.sql"),
                (content_digest, name, "unpinned", occurred_at.isoformat()),
            )

    def execute_prune(
        self,
        plan: _PrunePlan,
        *,
        object_store: _ArtifactObjectStore,
    ) -> tuple[str, ...]:
        """Execute a validated plan while rechecking every safety condition."""
        if plan.validation_digest != _prune_validation_digest(plan.candidates):
            raise CFBDPersistenceError(category="prune_plan")
        current = self.plan_prune()
        if current != plan:
            raise CFBDPersistenceError(category="prune_plan_stale")
        removed: list[str] = []
        for candidate in plan.candidates:
            object_store.load_manifest(candidate.content_digest)
            occurred_at = _as_utc(self._clock())
            with self._transaction() as connection:
                eligible = {
                    str(row["content_digest"])
                    for row in self._eligible_artifacts(connection)
                }
                if candidate.content_digest not in eligible:
                    raise CFBDPersistenceError(category="prune_plan_stale")
                connection.execute(
                    self._sql.render("artifacts/insert_gc_transition.sql"),
                    (candidate.content_digest, "deleting", occurred_at.isoformat()),
                )
            object_store.remove(candidate.content_digest)
            deleted_at = _as_utc(self._clock())
            with self._transaction() as connection:
                connection.execute(
                    self._sql.render("artifacts/insert_gc_transition.sql"),
                    (candidate.content_digest, "deleted", deleted_at.isoformat()),
                )
            removed.append(candidate.content_digest)
        return tuple(removed)

    def execute_orphan_cleanup(
        self,
        plan: _OrphanCleanupPlan,
        *,
        object_store: _ArtifactObjectStore,
    ) -> tuple[str, ...]:
        """Remove unchanged unregistered objects under the publication lock."""
        if plan.validation_digest != _orphan_validation_digest(plan.candidates):
            raise CFBDPersistenceError(category="orphan_plan")
        with self._transaction() as connection:
            current = self.plan_orphan_cleanup(object_store=object_store)
            if current != plan:
                raise CFBDPersistenceError(category="orphan_plan_stale")
            registered = {
                str(row["content_digest"])
                for row in connection.execute(
                    self._sql.render("artifacts/select_registered_digests.sql")
                ).fetchall()
            }
            for candidate in plan.candidates:
                if candidate.content_digest in registered:
                    raise CFBDPersistenceError(category="orphan_plan_stale")
                object_store.remove(candidate.content_digest)
        return tuple(candidate.content_digest for candidate in plan.candidates)

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
                    self._sql.render("checkpoints/select_parent.sql"),
                    (
                        parent_run_id,
                        node_fingerprint,
                        output_name,
                        credential_scope,
                    ),
                ).fetchone()
            if row is None and scope in {"global", "parent_then_global"}:
                row = self._connection.execute(
                    self._sql.render("checkpoints/select_global.sql"),
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
                self._sql.render("nodes/select_current_state.sql"),
                (run_id, node_id),
            ).fetchone()
        return None if row is None else _node_state(row["state"])

    def _eligible_artifacts(
        self,
        connection: sqlite3.Connection,
    ) -> Sequence[sqlite3.Row]:
        return connection.execute(
            self._sql.render("artifacts/select_eligible_for_prune.sql")
        ).fetchall()

    def _run_retention_state(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> str:
        row = connection.execute(
            self._sql.render("runs/select_retention_state.sql"),
            (run_id,),
        ).fetchone()
        if row is None or row["state"] not in {"active", "retired"}:
            raise CFBDPersistenceError(category="retention_state")
        return str(row["state"])

    def _pin_state(
        self,
        connection: sqlite3.Connection,
        content_digest: str,
        name: str,
    ) -> str | None:
        row = connection.execute(
            self._sql.render("artifacts/select_pin_state.sql"),
            (content_digest, name),
        ).fetchone()
        return None if row is None else str(row["state"])

    def _require_registered_artifact(
        self,
        connection: sqlite3.Connection,
        content_digest: str,
    ) -> None:
        row = connection.execute(
            self._sql.render("artifacts/require_registered.sql"),
            (content_digest,),
        ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="artifact_missing")

    def _require_artifact_not_retired(
        self,
        connection: sqlite3.Connection,
        content_digest: str,
    ) -> None:
        row = connection.execute(
            self._sql.render("artifacts/select_gc_state.sql"),
            (content_digest,),
        ).fetchone()
        if row is not None and row["state"] in {"deleting", "deleted"}:
            raise CFBDPersistenceError(category="artifact_retired")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute(
                    self._sql.render("transaction/begin_immediate.sql")
                )
                yield self._connection
                self._connection.execute(self._sql.render("transaction/commit.sql"))
            except Exception:
                self._connection.execute(self._sql.render("transaction/rollback.sql"))
                raise

    def _current_run_state(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> _RunState:
        row = connection.execute(
            self._sql.render("runs/select_current_state.sql"),
            (run_id,),
        ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")
        return _run_state(row["state"])

    def _require_run(self, connection: sqlite3.Connection, run_id: str) -> None:
        row = connection.execute(
            self._sql.render("runs/require_run.sql"),
            (run_id,),
        ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="run_missing")

    def _migrate(self) -> None:
        with self._lock:
            version = self._connection.execute(
                self._sql.render("migrations/get_user_version.sql")
            ).fetchone()[0]
            if version not in {0, 1, 2, 3, 4, 5}:
                raise CFBDPersistenceError(category="database_version")
            if version == 5:
                return
            migrations = {
                0: ("migrations/001_initial.sql", 1),
                1: ("migrations/002_credential_scope.sql", 2),
                2: ("migrations/003_retention.sql", 3),
                3: ("migrations/004_attempt_reservations.sql", 4),
                4: ("migrations/005_checkpoint_eligibility.sql", 5),
            }
            migration_name, target_version = migrations[version]
            try:
                self._connection.executescript(self._sql.render(migration_name))
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute(
                        self._sql.render("transaction/rollback.sql")
                    )
                raise
            if target_version < 5:
                self._migrate()


class _RunDatabaseReader(_RunDatabaseQueries):
    """Own a non-mutating SQLite connection for public inspection."""

    def __init__(self, path: Path) -> None:
        """Open an existing analytics database in SQLite read-only mode.

        :param path: Existing analytics run database.
        :raises CFBDPersistenceError: If the database is absent or incompatible.
        """
        if not path.is_file():
            raise CFBDPersistenceError(category="database_missing")
        self._lock = threading.RLock()
        self._sql = AnalyticsSQLiteSQL()
        try:
            self._connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute(self._sql.render("config/set_query_only.sql"))
            version_row = self._connection.execute(
                self._sql.render("migrations/get_user_version.sql")
            ).fetchone()
            if version_row is None or int(version_row[0]) != 5:
                raise CFBDPersistenceError(category="database_version")
        except CFBDPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise CFBDPersistenceError(category="database_open") from exc

    def close(self) -> None:
        """Close the owned read-only connection."""
        with self._lock:
            self._connection.close()

    def list_runs(self, *, limit: int) -> tuple[_RunRecord, ...]:
        """Return recent runs without exposing parameters or credentials."""
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be an integer between 1 and 1000")
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("runs/select_runs.sql"),
                (limit,),
            ).fetchall()
        return tuple(_run_record(row) for row in rows)

    def retention_state(self, run_id: str) -> Literal["active", "retired"]:
        """Return the latest append-only retention state for one run."""
        self.get_run(run_id)
        with self._lock:
            row = self._connection.execute(
                self._sql.render("runs/select_retention_state.sql"),
                (run_id,),
            ).fetchone()
        if row is None or row["state"] not in {"active", "retired"}:
            raise CFBDPersistenceError(category="database_value")
        return cast(Literal["active", "retired"], row["state"])

    def manifest(self, content_digest: str) -> _ArtifactManifest:
        """Return one strictly validated registered artifact manifest."""
        with self._lock:
            row = self._connection.execute(
                self._sql.render("artifacts/select_manifest.sql"),
                (content_digest,),
            ).fetchone()
        if row is None:
            raise CFBDPersistenceError(category="artifact_missing")
        try:
            return _ArtifactManifest.model_validate_json(
                str(row["manifest_json"]),
                strict=True,
            )
        except ValueError as exc:
            raise CFBDArtifactCorruptionError(
                content_digest=content_digest,
                category="database_manifest",
            ) from exc

    def active_pins(self, content_digest: str) -> tuple[str, ...]:
        """Return active safe pin names in deterministic order."""
        self.manifest(content_digest)
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("artifacts/select_active_pins.sql"),
                (content_digest,),
            ).fetchall()
        return tuple(str(row["pin_name"]) for row in rows)

    def referenced_runs(self, content_digest: str) -> tuple[str, ...]:
        """Return immutable run identities referencing an artifact."""
        self.manifest(content_digest)
        with self._lock:
            rows = self._connection.execute(
                self._sql.render("artifacts/select_referenced_runs.sql"),
                (content_digest,),
            ).fetchall()
        return tuple(str(row["run_id"]) for row in rows)


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
        max_http_attempts=int(row["max_http_attempts"]),
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
        checkpoint_eligible=bool(row["checkpoint_eligible"]),
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


def _validate_pin_name(name: str) -> None:
    """Require a bounded safe label rather than an arbitrary path or secret."""
    if (
        not name
        or len(name) > 128
        or any(character not in _SAFE_PIN_CHARACTERS for character in name)
    ):
        raise ValueError("Artifact pin names must be safe non-empty slugs")


def _validate_completed_outputs(
    outputs: Sequence[tuple[str, str, _StoredArtifact, _Placement]],
) -> None:
    """Require one or more uniquely named outputs before publication."""
    if not outputs:
        raise ValueError("Completed nodes require at least one output")
    names = tuple(output[0] for output in outputs)
    if len(set(names)) != len(names):
        raise ValueError("Completed node output names must be unique")


_SAFE_PIN_CHARACTERS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _manifest_size(payload: str) -> int:
    """Return total payload bytes from a validated stored manifest."""
    try:
        manifest = _ArtifactManifest.model_validate_json(payload, strict=True)
    except ValueError as exc:
        raise CFBDArtifactCorruptionError(
            content_digest=None,
            category="database_manifest",
        ) from exc
    return sum(part.size_bytes for part in manifest.body.parts)


def _prune_validation_digest(candidates: Sequence[_PruneCandidate]) -> str:
    """Bind a prune plan to ordered candidate identity and size evidence."""
    return _digest(
        {
            "prune_plan": 1,
            "candidates": [
                {
                    "content_digest": candidate.content_digest,
                    "size_bytes": candidate.size_bytes,
                }
                for candidate in candidates
            ],
        }
    )


def _orphan_validation_digest(candidates: Sequence[_PruneCandidate]) -> str:
    """Bind an orphan cleanup plan to ordered validated object evidence."""
    return _digest(
        {
            "orphan_cleanup_plan": 1,
            "candidates": [
                {
                    "content_digest": candidate.content_digest,
                    "size_bytes": candidate.size_bytes,
                }
                for candidate in candidates
            ],
        }
    )


__all__: Sequence[str] = ()
