"""Test Merkle checkpoint identity and freshness-safe recovery lookup."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Literal

from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _AnalyticsTableIdentity,
)
from cfb_data.analytics._artifacts import _TableArtifactCodec
from cfb_data.analytics._checkpoints import (
    _checkpoint_scope,
    _node_fingerprint,
    _OutputContractIdentity,
    _UpstreamArtifactIdentity,
)
from cfb_data.analytics._declarations import RecipeKind, _RecipeDeclaration
from cfb_data.analytics._graph import _CompiledNode
from cfb_data.analytics._persistence import (
    _ArtifactObjectStore,
    _RunDatabase,
    _StoredArtifact,
)
from pydantic import BaseModel, ConfigDict


class _CheckpointRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int


def _node(
    *,
    kind: RecipeKind = "step",
    recipe_id: str | None = "cfbd.clean_games",
    revision: int | None = 1,
    deterministic: bool = True,
    backends: frozenset[str] = frozenset({"pandas", "polars"}),
) -> _CompiledNode:
    declaration = _RecipeDeclaration(
        kind=kind,
        recipe_id=recipe_id,
        revision=revision,
        output_type=_CheckpointRow,
        deterministic=deterministic,
        supported_backends=backends,
        dask_eligible=True,
    )
    return _CompiledNode(
        node_id=f"{kind}:{recipe_id}",
        kind=kind,
        declaration=declaration,
        recipe=object(),
        arguments=MappingProxyType({}),
        provided=frozenset(),
        dependencies=(),
    )


_OUTPUT = _OutputContractIdentity(
    name="value",
    output_id="cfbd.clean_games",
    revision=1,
    schema_digest="a" * 64,
    codec_id="cfb_data.analytics.parquet",
    codec_version=2,
)


def _fingerprint(
    node: _CompiledNode,
    *,
    parameters: dict[str, object] | None = None,
    upstream: tuple[_UpstreamArtifactIdentity, ...] = (),
    backend: Literal["pandas", "polars"] = "pandas",
) -> str | None:
    return _node_fingerprint(
        node,
        parameters=parameters or {"season": 2024},
        upstream=upstream,
        outputs=(_OUTPUT,),
        backend=backend,
    )


def _artifact(store: _ArtifactObjectStore) -> _StoredArtifact:
    identity = _AnalyticsTableIdentity(output_id="cfbd.clean_games", revision=1)
    table = _analytics_arrow_table_from_models(
        row_model=_CheckpointRow,
        models=[_CheckpointRow(game_id=1)],
        identity=identity,
    )
    with store.staging_directory() as directory:
        staged = _TableArtifactCodec().stage(
            directory=directory,
            table=table,
            row_model=_CheckpointRow,
            identity=identity,
        )
        return store.publish(staged)


def _commit_node(
    database: _RunDatabase,
    *,
    run_id: str,
    node_id: str,
    node_fingerprint: str,
    artifact: _StoredArtifact,
) -> None:
    database.transition_node(run_id, node_id, "ready")
    database.transition_node(run_id, node_id, "running")
    database.bind_completed_node(
        run_id=run_id,
        node_id=node_id,
        output_name="value",
        node_fingerprint=node_fingerprint,
        artifact=artifact,
        placement="local",
    )


def _run(
    database: _RunDatabase,
    *,
    credential_scope: str = "scope-a",
    parent_run_id: str | None = None,
) -> str:
    return database.create_run(
        recipe_id="cfbd.game_summaries",
        recipe_revision=1,
        recipe_kind="dataset",
        parameter_fingerprint="b" * 64,
        graph_fingerprint="c" * 64,
        credential_scope=credential_scope,
        parent_run_id=parent_run_id,
        source_behavior=(
            "preserve_snapshot" if parent_run_id is not None else "normal_freshness"
        ),
    ).run_id


def test_node_fingerprint_changes_only_for_semantic_inputs() -> None:
    node = _node()
    upstream = (
        _UpstreamArtifactIdentity(
            dependency="old/path",
            output_name="value",
            content_digest="d" * 64,
        ),
    )
    relocated = (
        _UpstreamArtifactIdentity(
            dependency="new/wrapper/path",
            output_name="value",
            content_digest="d" * 64,
        ),
    )

    baseline = _fingerprint(node, upstream=upstream)

    assert baseline == _fingerprint(node, upstream=relocated)
    assert baseline != _fingerprint(node, parameters={"season": 2025})
    assert baseline != _fingerprint(
        node,
        upstream=(
            _UpstreamArtifactIdentity(
                dependency="old/path",
                output_name="value",
                content_digest="e" * 64,
            ),
        ),
    )
    assert baseline != _fingerprint(_node(revision=2), upstream=upstream)


def test_portable_fingerprint_ignores_backend_but_specific_step_includes_it() -> None:
    portable = _node()
    pandas_only = _node(backends=frozenset({"pandas"}))

    assert _fingerprint(portable, backend="pandas") == _fingerprint(
        portable,
        backend="polars",
    )
    assert _fingerprint(pandas_only, backend="pandas") != _fingerprint(
        pandas_only,
        backend="polars",
    )


def test_unversioned_boundary_has_no_cross_run_fingerprint() -> None:
    assert _fingerprint(_node(recipe_id=None, revision=None)) is None


def test_checkpoint_scope_preserves_sources_only_during_recovery() -> None:
    source = _node(kind="source")
    deterministic_step = _node()
    nondeterministic_step = _node(deterministic=False)

    assert (
        _checkpoint_scope(
            source,
            parent_run_id=None,
            source_behavior="normal_freshness",
        )
        == "none"
    )
    assert (
        _checkpoint_scope(
            source,
            parent_run_id="parent",
            source_behavior="preserve_snapshot",
        )
        == "parent"
    )
    assert (
        _checkpoint_scope(
            source,
            parent_run_id="parent",
            source_behavior="refresh",
        )
        == "none"
    )
    assert (
        _checkpoint_scope(
            deterministic_step,
            parent_run_id=None,
            source_behavior="normal_freshness",
        )
        == "global"
    )
    assert (
        _checkpoint_scope(
            nondeterministic_step,
            parent_run_id=None,
            source_behavior="normal_freshness",
        )
        == "none"
    )


def test_checkpoint_lookup_prefers_parent_chain_then_global(tmp_path: Path) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _artifact(store)
    database = _RunDatabase(root / "runs.sqlite3")
    fingerprint = _fingerprint(_node())
    assert fingerprint is not None
    try:
        parent = _run(database)
        _commit_node(
            database,
            run_id=parent,
            node_id="parent-step",
            node_fingerprint=fingerprint,
            artifact=artifact,
        )
        child = _run(database, parent_run_id=parent)

        candidate = database.find_checkpoint(
            node_fingerprint=fingerprint,
            output_name="value",
            scope="parent_then_global",
            parent_run_id=parent,
            credential_scope="scope-a",
        )

        assert candidate is not None
        assert candidate.binding.run_id == parent
        assert candidate.manifest == artifact.manifest
        assert database.get_run(child).parent_run_id == parent
    finally:
        database.close()


def test_checkpoint_lookup_never_crosses_credential_scope(tmp_path: Path) -> None:
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    artifact = _artifact(store)
    database = _RunDatabase(root / "runs.sqlite3")
    fingerprint = _fingerprint(_node())
    assert fingerprint is not None
    try:
        other_scope = _run(database, credential_scope="scope-b")
        _commit_node(
            database,
            run_id=other_scope,
            node_id="step",
            node_fingerprint=fingerprint,
            artifact=artifact,
        )

        candidate = database.find_checkpoint(
            node_fingerprint=fingerprint,
            output_name="value",
            scope="global",
            parent_run_id=None,
            credential_scope="scope-a",
        )

        assert candidate is None
    finally:
        database.close()


def test_fresh_source_scope_performs_no_analytics_checkpoint_lookup(
    tmp_path: Path,
) -> None:
    database = _RunDatabase(tmp_path / "runs.sqlite3")
    try:
        assert (
            database.find_checkpoint(
                node_fingerprint="a" * 64,
                output_name="value",
                scope="none",
                parent_run_id=None,
                credential_scope="scope-a",
            )
            is None
        )
    finally:
        database.close()
