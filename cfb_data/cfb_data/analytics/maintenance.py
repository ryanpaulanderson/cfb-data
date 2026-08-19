"""Inspect and maintain durable analytics state without a manager resource."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from ._compiler import _digest
from ._persistence import (
    _analytics_root,
    _ArtifactObjectStore,
    _orphan_validation_digest,
    _OrphanCleanupPlan,
    _prune_validation_digest,
    _PruneCandidate,
    _PrunePlan,
    _RunDatabase,
    _RunDatabaseReader,
    _RunRecord,
)
from .config import AnalyticsConfig
from .errors import CFBDPersistenceError
from .results import ArtifactDescriptor, _artifact_descriptor

type RunState = Literal["created", "running", "completed", "failed", "cancelled"]
type RecipeKind = Literal["dataset", "workflow"]
type RetentionState = Literal["active", "retired"]
type Placement = Literal["coordinator", "local", "dask"]
type SourceBehavior = Literal["preserve_snapshot", "normal_freshness", "refresh"]


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Summarize one immutable run without parameters or credentials."""

    run_id: str
    recipe_id: str
    recipe_revision: int | None
    recipe_kind: RecipeKind
    state: RunState
    retention: RetentionState
    parent_run_id: str | None
    source_behavior: SourceBehavior
    created_at: datetime
    actual_http_attempts: int
    artifact_count: int


@dataclass(frozen=True, slots=True)
class RunArtifactSummary:
    """Describe one durable output binding without exposing its path."""

    node_id: str
    output_name: str
    placement: Placement
    committed_at: datetime
    descriptor: ArtifactDescriptor


@dataclass(frozen=True, slots=True)
class RunInspection:
    """Expose validated run and artifact evidence for an analyst."""

    summary: RunSummary
    artifacts: tuple[RunArtifactSummary, ...]


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    """Expose validated artifact metadata, pins, and immutable references."""

    descriptor: ArtifactDescriptor
    active_pins: tuple[str, ...]
    referenced_run_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PruneCandidate:
    """Describe one registered object eligible for safe pruning."""

    content_digest: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class PrunePlan:
    """Bind a read-only prune preview to its store and candidate snapshot."""

    candidates: tuple[PruneCandidate, ...]
    total_bytes: int
    _validation_digest: str = field(repr=False)
    _root_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PruneResult:
    """Report content removed by execution of a validated prune plan."""

    removed_digests: tuple[str, ...]
    removed_bytes: int


@dataclass(frozen=True, slots=True)
class OrphanCandidate:
    """Describe one validated immutable object absent from run state."""

    content_digest: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class OrphanCleanupPlan:
    """Bind a read-only orphan preview to its store and object snapshot."""

    candidates: tuple[OrphanCandidate, ...]
    total_bytes: int
    _validation_digest: str = field(repr=False)
    _root_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class OrphanCleanupResult:
    """Report validated unregistered objects removed from the store."""

    removed_digests: tuple[str, ...]
    removed_bytes: int


async def list_runs(
    config: AnalyticsConfig | None = None,
    *,
    limit: int = 100,
) -> tuple[RunSummary, ...]:
    """Return recent analytics runs without creating durable state.

    :param config: Analytics storage configuration.
    :param limit: Maximum number of recent runs, from one through one thousand.
    :return: Recent safe summaries, or an empty tuple when no store exists.
    :raises ValueError: If the limit is outside the supported range.
    :raises CFBDPersistenceError: If existing durable state is incompatible.
    """
    return await asyncio.to_thread(_list_runs_sync, _config(config), limit)


async def inspect_run(
    run_id: str,
    config: AnalyticsConfig | None = None,
) -> RunInspection:
    """Return validated immutable evidence for one run.

    :param run_id: Safe run identifier returned by recipe execution.
    :param config: Analytics storage configuration.
    :return: Run summary and ordered artifact bindings.
    :raises CFBDPersistenceError: If the run database or run is unavailable.
    :raises CFBDArtifactCorruptionError: If bound content fails validation.
    """
    return await asyncio.to_thread(_inspect_run_sync, _config(config), run_id)


async def inspect_artifact(
    content_digest: str,
    config: AnalyticsConfig | None = None,
) -> ArtifactInspection:
    """Return validated metadata for one registered immutable object.

    :param content_digest: Artifact content digest from a recipe run.
    :param config: Analytics storage configuration.
    :return: Stable descriptor, active pins, and referencing run IDs.
    :raises CFBDPersistenceError: If the database or artifact is unavailable.
    :raises CFBDArtifactCorruptionError: If durable content fails validation.
    """
    return await asyncio.to_thread(
        _inspect_artifact_sync,
        _config(config),
        content_digest,
    )


async def retire_run(
    run_id: str,
    config: AnalyticsConfig | None = None,
) -> None:
    """Retire a run's retention claim without deleting audit evidence.

    :param run_id: Existing immutable run identifier.
    :param config: Analytics storage configuration.
    :raises CFBDPersistenceError: If the transition is invalid or unavailable.
    """
    await asyncio.to_thread(
        _mutate_run_retention,
        _config(config),
        run_id,
        "retired",
    )


async def retain_run(
    run_id: str,
    config: AnalyticsConfig | None = None,
) -> None:
    """Restore a retired run's claim while all bound content remains available.

    :param run_id: Existing immutable run identifier.
    :param config: Analytics storage configuration.
    :raises CFBDPersistenceError: If the transition or content is invalid.
    """
    await asyncio.to_thread(
        _mutate_run_retention,
        _config(config),
        run_id,
        "active",
    )


async def pin_artifact(
    content_digest: str,
    *,
    name: str,
    config: AnalyticsConfig | None = None,
) -> None:
    """Add a named retention pin to one registered immutable object.

    :param content_digest: Artifact content digest.
    :param name: Safe bounded pin label.
    :param config: Analytics storage configuration.
    :raises ValueError: If the pin label is invalid.
    :raises CFBDPersistenceError: If the artifact or transition is invalid.
    """
    await asyncio.to_thread(
        _mutate_artifact_pin,
        _config(config),
        content_digest,
        name,
        True,
    )


async def unpin_artifact(
    content_digest: str,
    *,
    name: str,
    config: AnalyticsConfig | None = None,
) -> None:
    """Remove one existing named artifact retention pin.

    :param content_digest: Artifact content digest.
    :param name: Existing safe pin label.
    :param config: Analytics storage configuration.
    :raises ValueError: If the pin label is invalid.
    :raises CFBDPersistenceError: If the artifact or transition is invalid.
    """
    await asyncio.to_thread(
        _mutate_artifact_pin,
        _config(config),
        content_digest,
        name,
        False,
    )


async def plan_artifact_prune(
    config: AnalyticsConfig | None = None,
) -> PrunePlan:
    """Preview unreferenced and unpinned objects without mutating the store.

    :param config: Analytics storage configuration.
    :return: Immutable candidate snapshot bound to this configured root.
    :raises CFBDPersistenceError: If existing durable state is incompatible.
    """
    return await asyncio.to_thread(_plan_artifact_prune_sync, _config(config))


async def execute_artifact_prune(
    plan: PrunePlan,
    config: AnalyticsConfig | None = None,
) -> PruneResult:
    """Execute an unchanged validated prune plan and recheck every candidate.

    :param plan: Exact plan returned by :func:`plan_artifact_prune`.
    :param config: Analytics storage configuration used to create the plan.
    :return: Removed digests and total payload bytes.
    :raises CFBDPersistenceError: If the plan is invalid, stale, or mismatched.
    :raises CFBDArtifactCorruptionError: If candidate content is corrupt.
    """
    return await asyncio.to_thread(
        _execute_artifact_prune_sync,
        _config(config),
        plan,
    )


async def plan_orphan_cleanup(
    config: AnalyticsConfig | None = None,
) -> OrphanCleanupPlan:
    """Preview validated unregistered objects without mutating durable state.

    Active staging directories are intentionally excluded because they are not
    immutable objects and may belong to a live codec write.

    :param config: Analytics storage configuration.
    :return: Immutable candidate snapshot bound to this configured root.
    :raises CFBDArtifactCorruptionError: If the published layout is invalid.
    :raises CFBDPersistenceError: If existing run state is incompatible.
    """
    return await asyncio.to_thread(_plan_orphan_cleanup_sync, _config(config))


async def clean_orphans(
    plan: OrphanCleanupPlan,
    config: AnalyticsConfig | None = None,
) -> OrphanCleanupResult:
    """Remove only unchanged validated objects absent from durable run state.

    :param plan: Exact plan returned by :func:`plan_orphan_cleanup`.
    :param config: Analytics storage configuration used to create the plan.
    :return: Removed digests and total payload bytes.
    :raises CFBDPersistenceError: If the plan is invalid, stale, or mismatched.
    :raises CFBDArtifactCorruptionError: If candidate content is corrupt.
    """
    return await asyncio.to_thread(
        _clean_orphans_sync,
        _config(config),
        plan,
    )


def _config(config: AnalyticsConfig | None) -> AnalyticsConfig:
    return config if config is not None else AnalyticsConfig()


def _list_runs_sync(config: AnalyticsConfig, limit: int) -> tuple[RunSummary, ...]:
    root = _analytics_root(config)
    path = root / "runs.sqlite3"
    if not path.is_file():
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be an integer between 1 and 1000")
        return ()
    reader = _RunDatabaseReader(path)
    try:
        return tuple(_run_summary(reader, run) for run in reader.list_runs(limit=limit))
    finally:
        reader.close()


def _inspect_run_sync(config: AnalyticsConfig, run_id: str) -> RunInspection:
    root = _analytics_root(config)
    reader = _RunDatabaseReader(root / "runs.sqlite3")
    try:
        run = reader.get_run(run_id)
        summary = _run_summary(reader, run)
        store = _ArtifactObjectStore(root, create=False)
        artifacts: list[RunArtifactSummary] = []
        for binding in reader.bindings(run_id):
            database_manifest = reader.manifest(binding.content_digest)
            object_manifest = store.load_manifest(binding.content_digest)
            if database_manifest != object_manifest:
                raise CFBDPersistenceError(category="artifact_manifest_mismatch")
            artifacts.append(
                RunArtifactSummary(
                    node_id=binding.node_id,
                    output_name=binding.output_name,
                    placement=binding.placement,
                    committed_at=binding.committed_at,
                    descriptor=_artifact_descriptor(object_manifest),
                )
            )
        return RunInspection(summary=summary, artifacts=tuple(artifacts))
    finally:
        reader.close()


def _inspect_artifact_sync(
    config: AnalyticsConfig,
    content_digest: str,
) -> ArtifactInspection:
    root = _analytics_root(config)
    reader = _RunDatabaseReader(root / "runs.sqlite3")
    try:
        database_manifest = reader.manifest(content_digest)
        object_manifest = _ArtifactObjectStore(root, create=False).load_manifest(
            content_digest
        )
        if database_manifest != object_manifest:
            raise CFBDPersistenceError(category="artifact_manifest_mismatch")
        return ArtifactInspection(
            descriptor=_artifact_descriptor(object_manifest),
            active_pins=reader.active_pins(content_digest),
            referenced_run_ids=reader.referenced_runs(content_digest),
        )
    finally:
        reader.close()


def _run_summary(reader: _RunDatabaseReader, run: _RunRecord) -> RunSummary:
    bindings = reader.bindings(run.run_id)
    return RunSummary(
        run_id=run.run_id,
        recipe_id=run.recipe_id,
        recipe_revision=run.recipe_revision,
        recipe_kind=run.recipe_kind,
        state=run.state,
        retention=reader.retention_state(run.run_id),
        parent_run_id=run.parent_run_id,
        source_behavior=run.source_behavior,
        created_at=run.created_at,
        actual_http_attempts=reader.attempt_count(run.run_id),
        artifact_count=len(bindings),
    )


def _require_database(config: AnalyticsConfig) -> tuple[Path, Path]:
    root = _analytics_root(config)
    path = root / "runs.sqlite3"
    if not path.is_file():
        raise CFBDPersistenceError(category="database_missing")
    return root, path


def _mutate_run_retention(
    config: AnalyticsConfig,
    run_id: str,
    state: RetentionState,
) -> None:
    _, path = _require_database(config)
    database = _RunDatabase(path)
    try:
        if state == "active":
            database.retain_run(run_id)
        else:
            database.retire_run(run_id)
    finally:
        database.close()


def _mutate_artifact_pin(
    config: AnalyticsConfig,
    content_digest: str,
    name: str,
    pin: bool,
) -> None:
    _, path = _require_database(config)
    database = _RunDatabase(path)
    try:
        if pin:
            database.pin_artifact(content_digest, name=name)
        else:
            database.unpin_artifact(content_digest, name=name)
    finally:
        database.close()


def _plan_artifact_prune_sync(config: AnalyticsConfig) -> PrunePlan:
    root = _analytics_root(config)
    path = root / "runs.sqlite3"
    if not path.is_file():
        return PrunePlan(
            candidates=(),
            total_bytes=0,
            _validation_digest=_prune_validation_digest(()),
            _root_token=_root_token(root),
        )
    reader = _RunDatabaseReader(path)
    try:
        internal = reader.plan_prune()
    finally:
        reader.close()
    candidates = tuple(
        PruneCandidate(
            content_digest=candidate.content_digest,
            size_bytes=candidate.size_bytes,
        )
        for candidate in internal.candidates
    )
    return PrunePlan(
        candidates=candidates,
        total_bytes=sum(candidate.size_bytes for candidate in candidates),
        _validation_digest=internal.validation_digest,
        _root_token=_root_token(root),
    )


def _execute_artifact_prune_sync(
    config: AnalyticsConfig,
    plan: PrunePlan,
) -> PruneResult:
    root, path = _require_database(config)
    if plan._root_token != _root_token(root):
        raise CFBDPersistenceError(category="prune_plan_root")
    internal = _PrunePlan(
        candidates=tuple(
            _PruneCandidate(
                content_digest=candidate.content_digest,
                size_bytes=candidate.size_bytes,
            )
            for candidate in plan.candidates
        ),
        validation_digest=plan._validation_digest,
    )
    if plan.total_bytes != sum(candidate.size_bytes for candidate in plan.candidates):
        raise CFBDPersistenceError(category="prune_plan")
    database = _RunDatabase(path)
    try:
        removed = database.execute_prune(
            internal,
            object_store=_ArtifactObjectStore(root),
        )
    finally:
        database.close()
    size_by_digest = {
        candidate.content_digest: candidate.size_bytes for candidate in plan.candidates
    }
    return PruneResult(
        removed_digests=removed,
        removed_bytes=sum(size_by_digest[digest] for digest in removed),
    )


def _plan_orphan_cleanup_sync(config: AnalyticsConfig) -> OrphanCleanupPlan:
    root = _analytics_root(config)
    path = root / "runs.sqlite3"
    store = _ArtifactObjectStore(root, create=False)
    if path.is_file():
        reader = _RunDatabaseReader(path)
        try:
            internal = reader.plan_orphan_cleanup(object_store=store)
        finally:
            reader.close()
    else:
        internal_candidates = tuple(
            _PruneCandidate(
                content_digest=artifact.content_digest,
                size_bytes=sum(
                    part.size_bytes for part in artifact.manifest.body.parts
                ),
            )
            for artifact in store.published_artifacts()
        )
        internal = _OrphanCleanupPlan(
            candidates=internal_candidates,
            validation_digest=_orphan_validation_digest(internal_candidates),
        )
    public_candidates = tuple(
        OrphanCandidate(
            content_digest=candidate.content_digest,
            size_bytes=candidate.size_bytes,
        )
        for candidate in internal.candidates
    )
    return OrphanCleanupPlan(
        candidates=public_candidates,
        total_bytes=sum(candidate.size_bytes for candidate in public_candidates),
        _validation_digest=internal.validation_digest,
        _root_token=_root_token(root),
    )


def _clean_orphans_sync(
    config: AnalyticsConfig,
    plan: OrphanCleanupPlan,
) -> OrphanCleanupResult:
    root = _analytics_root(config)
    if plan._root_token != _root_token(root):
        raise CFBDPersistenceError(category="orphan_plan_root")
    if plan.total_bytes != sum(candidate.size_bytes for candidate in plan.candidates):
        raise CFBDPersistenceError(category="orphan_plan")
    internal = _OrphanCleanupPlan(
        candidates=tuple(
            _PruneCandidate(
                content_digest=candidate.content_digest,
                size_bytes=candidate.size_bytes,
            )
            for candidate in plan.candidates
        ),
        validation_digest=plan._validation_digest,
    )
    if not internal.candidates:
        return OrphanCleanupResult(removed_digests=(), removed_bytes=0)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        removed = database.execute_orphan_cleanup(
            internal,
            object_store=_ArtifactObjectStore(root),
        )
    finally:
        database.close()
    size_by_digest = {
        candidate.content_digest: candidate.size_bytes for candidate in plan.candidates
    }
    return OrphanCleanupResult(
        removed_digests=removed,
        removed_bytes=sum(size_by_digest[digest] for digest in removed),
    )


def _root_token(root: Path) -> str:
    return _digest({"analytics_root": str(root.expanduser().resolve())})


__all__ = [
    "ArtifactInspection",
    "OrphanCandidate",
    "OrphanCleanupPlan",
    "OrphanCleanupResult",
    "PruneCandidate",
    "PrunePlan",
    "PruneResult",
    "RunArtifactSummary",
    "RunInspection",
    "RunSummary",
    "clean_orphans",
    "execute_artifact_prune",
    "inspect_artifact",
    "inspect_run",
    "list_runs",
    "pin_artifact",
    "plan_artifact_prune",
    "plan_orphan_cleanup",
    "retain_run",
    "retire_run",
    "unpin_artifact",
]
