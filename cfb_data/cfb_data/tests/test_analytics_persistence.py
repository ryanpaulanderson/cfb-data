"""Test immutable analytics objects and append-only run evidence."""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pytest
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _AnalyticsTableIdentity,
)
from cfb_data.analytics._artifacts import _TableArtifactCodec
from cfb_data.analytics._persistence import (
    _analytics_root,
    _ArtifactObjectStore,
    _PruneCandidate,
    _RunDatabase,
    _StoredArtifact,
)
from cfb_data.analytics.config import AnalyticsConfig
from cfb_data.analytics.errors import (
    CFBDArtifactCorruptionError,
    CFBDAttemptBudgetExceeded,
    CFBDPersistenceError,
)
from cfb_data.analytics.maintenance import (
    execute_artifact_prune,
    inspect_artifact,
    inspect_run,
    list_runs,
    pin_artifact,
    plan_artifact_prune,
    retire_run,
    unpin_artifact,
)
from pydantic import BaseModel, ConfigDict


class _ArtifactRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    score: int | None


_IDENTITY = _AnalyticsTableIdentity(output_id="cfbd.persistence_test", revision=1)
_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _table() -> pa.Table:
    return _analytics_arrow_table_from_models(
        row_model=_ArtifactRow,
        models=[_ArtifactRow(game_id=1, score=28)],
        identity=_IDENTITY,
    )


def _publish(store: _ArtifactObjectStore) -> _StoredArtifact:
    with store.staging_directory() as directory:
        staged = _TableArtifactCodec().stage(
            directory=directory,
            table=_table(),
            row_model=_ArtifactRow,
            identity=_IDENTITY,
        )
        return store.publish(staged)


def _run_with_artifact(
    database: _RunDatabase,
    artifact: _StoredArtifact,
    *,
    credential_scope: str = "scope-a",
) -> str:
    run = database.create_run(
        recipe_id="cfbd.game_summaries",
        recipe_revision=1,
        recipe_kind="dataset",
        parameter_fingerprint="a" * 64,
        graph_fingerprint="b" * 64,
        credential_scope=credential_scope,
    )
    database.transition_node(run.run_id, "step", "ready")
    database.transition_node(run.run_id, "step", "running")
    database.bind_completed_node(
        run_id=run.run_id,
        node_id="step",
        output_name="value",
        node_fingerprint="c" * 64,
        artifact=artifact,
        placement="local",
    )
    return run.run_id


def test_root_resolution_does_not_create_files(tmp_path: Path) -> None:
    root = tmp_path / "not-created"

    resolved = _analytics_root(AnalyticsConfig(root=root))

    assert resolved == root
    assert not root.exists()


@pytest.mark.asyncio
async def test_public_listing_without_a_store_does_not_create_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "not-created"

    runs = await list_runs(AnalyticsConfig(root=root))

    assert runs == ()
    assert not root.exists()


def test_object_store_publishes_and_deduplicates_content(tmp_path: Path) -> None:
    store = _ArtifactObjectStore(tmp_path / "analytics")

    first = _publish(store)
    second = _publish(store)
    directory = store.directory(first.content_digest)

    assert first == second
    assert store.load_manifest(first.content_digest) == first.manifest
    assert sorted(path.name for path in directory.iterdir()) == [
        "manifest.json",
        "part-00000.parquet",
    ]
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir()
    )
    staging = tmp_path / "analytics" / "objects" / "sha256" / "staging"
    assert not any(staging.iterdir())


def test_object_store_cleans_abandoned_staging(tmp_path: Path) -> None:
    store = _ArtifactObjectStore(tmp_path / "analytics")

    with store.staging_directory() as directory:
        abandoned = directory
        (directory / "partial").write_bytes(b"partial")

    assert not abandoned.exists()


@pytest.mark.parametrize(
    "content_digest",
    ["../escape", "g" * 64, "0" * 63, "/" + "0" * 64],
)
def test_object_store_rejects_unsafe_content_identities(
    tmp_path: Path,
    content_digest: str,
) -> None:
    store = _ArtifactObjectStore(tmp_path / "analytics")

    with pytest.raises(CFBDArtifactCorruptionError) as exc_info:
        store.load_manifest(content_digest)

    assert exc_info.value.category == "identity"


def test_run_database_commits_artifact_binding_and_success_last(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
        )
        database.transition_run(run.run_id, "running")
        database.transition_node(run.run_id, "source:games", "ready")
        database.transition_node(run.run_id, "source:games", "running")

        binding = database.bind_completed_node(
            run_id=run.run_id,
            node_id="source:games",
            output_name="value",
            node_fingerprint="c" * 64,
            artifact=artifact,
            placement="coordinator",
        )
        completed = database.transition_run(run.run_id, "completed")

        assert binding.content_digest == artifact.content_digest
        assert database.bindings(run.run_id) == (binding,)
        assert database.node_state(run.run_id, "source:games") == "completed"
        assert completed.state == "completed"
        assert completed.created_at == _NOW
    finally:
        database.close()


def test_run_and_transition_rows_are_database_immutable(tmp_path: Path) -> None:
    path = tmp_path / "analytics" / "runs.sqlite3"
    database = _RunDatabase(path, clock=lambda: _NOW)
    run = database.create_run(
        recipe_id="cfbd.game_summaries",
        recipe_revision=1,
        recipe_kind="dataset",
        parameter_fingerprint="a" * 64,
        graph_fingerprint="b" * 64,
        credential_scope="scope-a",
    )
    database.close()

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE runs SET recipe_id = 'changed' WHERE run_id = ?",
                (run.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM run_transitions WHERE run_id = ?",
                (run.run_id,),
            )
    finally:
        connection.close()


def test_recovery_run_is_a_new_immutable_child(tmp_path: Path) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3", clock=lambda: _NOW)
    try:
        parent = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
        )
        database.transition_run(parent.run_id, "failed", node_id="step:clean")
        child = database.create_run(
            recipe_id=parent.recipe_id,
            recipe_revision=parent.recipe_revision,
            recipe_kind=parent.recipe_kind,
            parameter_fingerprint=parent.parameter_fingerprint,
            graph_fingerprint=parent.graph_fingerprint,
            credential_scope=parent.credential_scope,
            parent_run_id=parent.run_id,
            source_behavior="preserve_snapshot",
        )

        assert child.run_id != parent.run_id
        assert child.parent_run_id == parent.run_id
        assert child.source_behavior == "preserve_snapshot"
        assert database.get_run(parent.run_id).state == "failed"
    finally:
        database.close()


def test_invalid_state_transition_rolls_back_without_evidence(tmp_path: Path) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
        )

        with pytest.raises(CFBDPersistenceError) as exc_info:
            database.transition_run(run.run_id, "completed")

        assert exc_info.value.category == "run_transition"
        assert database.get_run(run.run_id).state == "created"
    finally:
        database.close()


def test_binding_failure_leaves_published_object_as_unbound_orphan(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
        )

        with pytest.raises(CFBDPersistenceError):
            database.bind_completed_node(
                run_id=run.run_id,
                node_id="step:never-started",
                output_name="value",
                node_fingerprint="c" * 64,
                artifact=artifact,
                placement="local",
            )

        assert database.bindings(run.run_id) == ()
        assert database.node_state(run.run_id, "step:never-started") is None
        assert store.load_manifest(artifact.content_digest) == artifact.manifest
    finally:
        database.close()


def test_database_file_uses_private_permissions(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    database = _RunDatabase(path)
    database.close()

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_actual_attempt_budget_is_durable_and_retry_inclusive(
    tmp_path: Path,
) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
            max_http_attempts=2,
        )
        database.transition_run(run.run_id, "running")

        first = database.reserve_attempt(
            run_id=run.run_id,
            node_id="source:games",
            endpoint="/games",
            retry_number=1,
        )
        second = database.reserve_attempt(
            run_id=run.run_id,
            node_id="source:games",
            endpoint="/games",
            retry_number=2,
        )

        with pytest.raises(CFBDAttemptBudgetExceeded) as exc_info:
            database.reserve_attempt(
                run_id=run.run_id,
                node_id="source:games",
                endpoint="/games",
                retry_number=3,
            )

        assert first.ordinal == 1
        assert second.ordinal == 2
        assert database.attempt_count(run.run_id) == 2
        assert exc_info.value.limit == 2
        assert exc_info.value.run_id == run.run_id
    finally:
        database.close()


def test_attempt_reservation_requires_running_run(tmp_path: Path) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run = database.create_run(
            recipe_id="cfbd.game_summaries",
            recipe_revision=1,
            recipe_kind="dataset",
            parameter_fingerprint="a" * 64,
            graph_fingerprint="b" * 64,
            credential_scope="scope-a",
        )

        with pytest.raises(CFBDPersistenceError) as exc_info:
            database.reserve_attempt(
                run_id=run.run_id,
                node_id="source:games",
                endpoint="/games",
                retry_number=1,
            )

        assert exc_info.value.category == "attempt_run_state"
        assert database.attempt_count(run.run_id) == 0
    finally:
        database.close()


def test_active_run_and_pin_both_protect_artifact_from_pruning(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run_id = _run_with_artifact(database, artifact)

        assert database.plan_prune().candidates == ()

        database.pin_artifact(artifact.content_digest, name="important")
        database.retire_run(run_id)
        assert database.plan_prune().candidates == ()

        database.unpin_artifact(artifact.content_digest, name="important")
        plan = database.plan_prune()
        assert [candidate.content_digest for candidate in plan.candidates] == [
            artifact.content_digest
        ]
    finally:
        database.close()


def test_shared_artifact_remains_while_any_run_claim_is_active(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        first = _run_with_artifact(database, artifact)
        second = _run_with_artifact(database, artifact)

        database.retire_run(first)
        assert database.plan_prune().candidates == ()

        database.retire_run(second)
        assert len(database.plan_prune().candidates) == 1
    finally:
        database.close()


def test_stale_prune_plan_fails_before_removing_content(tmp_path: Path) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run_id = _run_with_artifact(database, artifact)
        database.retire_run(run_id)
        plan = database.plan_prune()
        database.retain_run(run_id)

        with pytest.raises(CFBDPersistenceError) as exc_info:
            database.execute_prune(plan, object_store=store)

        assert exc_info.value.category == "prune_plan_stale"
        assert store.load_manifest(artifact.content_digest) == artifact.manifest
    finally:
        database.close()


def test_tampered_prune_plan_fails_validation(tmp_path: Path) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3", clock=lambda: _NOW)
    try:
        plan = database.plan_prune()
        tampered = replace(
            plan,
            candidates=(_PruneCandidate(content_digest="0" * 64, size_bytes=1),),
        )

        with pytest.raises(CFBDPersistenceError) as exc_info:
            database.execute_prune(
                tampered,
                object_store=_ArtifactObjectStore(tmp_path / "objects"),
            )

        assert exc_info.value.category == "prune_plan"
    finally:
        database.close()


def test_validated_prune_removes_only_retired_unpinned_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run_id = _run_with_artifact(database, artifact)
        database.retire_run(run_id)
        plan = database.plan_prune()

        removed = database.execute_prune(plan, object_store=store)

        assert removed == (artifact.content_digest,)
        assert database.bindings(run_id)[0].content_digest == artifact.content_digest
        assert database.plan_prune().candidates == ()
        with pytest.raises(CFBDArtifactCorruptionError):
            store.load_manifest(artifact.content_digest)
        with pytest.raises(CFBDPersistenceError) as exc_info:
            database.retain_run(run_id)
        assert exc_info.value.category == "retention_content_missing"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_public_maintenance_inspects_and_prunes_validated_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "analytics"
    config = AnalyticsConfig(root=root)
    store = _ArtifactObjectStore(root)
    artifact = _publish(store)
    database = _RunDatabase(root / "runs.sqlite3", clock=lambda: _NOW)
    try:
        run_id = _run_with_artifact(database, artifact)
    finally:
        database.close()

    before = {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }
    summaries = await list_runs(config)
    run = await inspect_run(run_id, config)
    inspected_artifact = await inspect_artifact(artifact.content_digest, config)
    after = {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }

    assert before == after
    assert summaries == (run.summary,)
    assert run.summary.artifact_count == 1
    assert run.artifacts[0].descriptor == inspected_artifact.descriptor
    assert inspected_artifact.active_pins == ()
    assert inspected_artifact.referenced_run_ids == (run_id,)

    await pin_artifact(artifact.content_digest, name="review", config=config)
    await retire_run(run_id, config)
    assert (await plan_artifact_prune(config)).candidates == ()

    await unpin_artifact(artifact.content_digest, name="review", config=config)
    plan = await plan_artifact_prune(config)
    assert plan.total_bytes == artifact.manifest.body.parts[0].size_bytes
    result = await execute_artifact_prune(plan, config)

    assert result.removed_digests == (artifact.content_digest,)
    assert result.removed_bytes == plan.total_bytes
    assert (await plan_artifact_prune(config)).candidates == ()


@pytest.mark.asyncio
async def test_public_prune_plan_is_bound_to_its_configured_root(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_database = _RunDatabase(first_root / "runs.sqlite3")
    first_database.close()
    second_database = _RunDatabase(second_root / "runs.sqlite3")
    second_database.close()

    plan = await plan_artifact_prune(AnalyticsConfig(root=first_root))

    with pytest.raises(CFBDPersistenceError) as exc_info:
        await execute_artifact_prune(plan, AnalyticsConfig(root=second_root))

    assert exc_info.value.category == "prune_plan_root"
