"""Test public durable recipe execution through an owned client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    ArtifactRef,
    CFBDRecipeCompilationError,
    CFBDRunError,
    ExecutionPolicy,
    RecipeRef,
    RecipeRun,
    SourceContext,
    dataset,
    list_runs,
    source,
    step,
    workflow,
)
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games
from pydantic import BaseModel

from cfb_data import CFBDClient, RetryPolicy, SQLiteCacheConfig

ServerFactory = Callable[[Callable[[web.Request], object]], object]


@dataset(
    id="tests.runtime_games",
    revision=1,
    row=Game,
    grain="one game",
    keys=("id",),
    order_by=("season", "week", "id"),
)
def _runtime_games(*, year: int, team: str) -> RecipeRef[list[Game]]:
    """Build one source-faithful runtime test dataset."""
    return games(year=year, team=team)


@workflow(id="tests.runtime_workflow", revision=1)
def _runtime_workflow(*, year: int, team: str) -> dict[str, RecipeRef[list[Game]]]:
    """Build one named-output workflow through the public dataset object."""
    return {"games": _runtime_games(year=year, team=team)}


class _CustomSourceRow(BaseModel):
    """Represent one row emitted by a user-owned coordinator source."""

    game_id: int
    season: int


@source(id="tests.custom_source", revision=1, output=_CustomSourceRow, cost=0)
async def _custom_source(
    context: SourceContext[_CustomSourceRow], *, season: int
) -> list[_CustomSourceRow]:
    """Return validated rows without an endpoint operation descriptor."""
    del context
    await asyncio.sleep(0)
    return [_CustomSourceRow(game_id=401628515, season=season)]


@dataset(
    id="tests.custom_source_dataset",
    revision=1,
    row=_CustomSourceRow,
    grain="one custom game",
    keys=("game_id",),
    order_by=("season", "game_id"),
)
def _custom_source_dataset(*, season: int) -> RecipeRef[list[_CustomSourceRow]]:
    """Expose a custom source through the ordinary dataset path."""
    return _custom_source(season=season)


@pytest.mark.asyncio
async def test_custom_source_completes_through_public_dataset_execution(
    tmp_path: Path,
) -> None:
    """Validate, persist, and report a source without endpoint metadata."""
    async with CFBDClient(
        "custom-source-key",
        analytics=AnalyticsConfig(root=tmp_path / "analytics"),
    ) as client:
        run = await _custom_source_dataset.run(client, season=2024)

    assert run.value.to_dict(orient="records") == [
        {"game_id": 401628515, "season": 2024}
    ]
    assert run.actual_http_attempts == 0
    assert len(run.source_coverage) == 1
    assert run.source_coverage[0].operation_id == "tests.custom_source"
    assert run.source_coverage[0].access_tier == "custom"
    assert run.source_coverage[0].state == "present"


@pytest.mark.asyncio
async def test_dataset_direct_and_advanced_runs_share_durable_execution(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Return eager frames, durable evidence, and zero-work transform replay."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        assert request.path == "/games"
        return web.json_response([game_response])

    root = tmp_path / "analytics"
    cache = SQLiteCacheConfig(path=tmp_path / "responses.sqlite3")
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "runtime-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=cache,
            analytics=AnalyticsConfig(root=root),
        ) as client:
            direct = await _runtime_games(client, year=2024, team="Penn State")
            advanced = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )

        assert isinstance(direct, pd.DataFrame)
        assert isinstance(advanced, RecipeRun)
        assert direct.equals(advanced.value)
        assert advanced.actual_http_attempts == 0
        assert advanced.reused_nodes == 1
        assert isinstance(advanced.artifact, ArtifactRef)
        assert advanced.artifact.descriptor.row_count == 1
        assert advanced.artifact.descriptor.grain == "one game"
        assert advanced.artifact.descriptor.keys == ("id",)
        assert advanced.artifact.descriptor.order_by == (
            "season",
            "week",
            "id",
        )
        assert tuple(result.check for result in advanced.quality["value"]) == (
            "row_contract",
            "candidate_key_uniqueness",
            "deterministic_order",
        )
        assert len(advanced.source_coverage) == 1
        assert advanced.source_coverage[0].operation_id == "cfbd.games.list"
        assert advanced.source_coverage[0].state == "present"
        assert advanced.source_coverage[0].row_count == 1
        assert {node.node_kind for node in advanced.lineage} == {
            "source",
            "dataset",
        }
        restored = advanced.artifact.load()
        assert isinstance(restored, pd.DataFrame)
        assert restored.equals(advanced.value)
        exported = advanced.artifact.export_parquet(tmp_path / "games.parquet")
        assert exported.is_file()
        assert str(root) not in repr(advanced.artifact)
    assert calls == 1


@pytest.mark.asyncio
async def test_checkpoint_off_keeps_artifacts_but_never_publishes_reuse(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep lineage artifacts while preventing disabled bindings from memoizing."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "checkpoint-policy-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=SQLiteCacheConfig(path=tmp_path / "responses.sqlite3"),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            disabled = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
                policy=ExecutionPolicy(checkpoint_mode="off"),
            )
            first_enabled = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )
            replay = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )

    assert isinstance(disabled.artifact, ArtifactRef)
    assert disabled.reused_nodes == 0
    assert all(not node.checkpoint_eligible for node in disabled.lineage)
    assert first_enabled.reused_nodes == 0
    assert all(node.checkpoint_eligible for node in first_enabled.lineage)
    assert replay.reused_nodes == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_targeted_recompute_executes_selected_node_and_publishes_reuse(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Force one boundary without disabling its future checkpoint evidence."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "targeted-recompute-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=SQLiteCacheConfig(path=tmp_path / "responses.sqlite3"),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            plan = await _runtime_games.plan(
                client,
                year=2024,
                team="Penn State",
            )
            dataset_id = plan.nodes[-1].node_id
            initial = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )
            reused = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )
            forced = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
                policy=ExecutionPolicy(recompute_nodes=(dataset_id,)),
            )
            replay = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )

    assert initial.reused_nodes == 0
    assert reused.reused_nodes == 1
    assert forced.reused_nodes == 0
    assert all(node.checkpoint_eligible for node in forced.lineage)
    assert replay.reused_nodes == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_refresh_source_behavior_forces_response_cache_refresh(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Make the advanced refresh option consume a fresh transport attempt."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "source-refresh-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=SQLiteCacheConfig(path=tmp_path / "responses.sqlite3"),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            initial = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )
            refreshed = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
                source_behavior="refresh",
            )
            cached = await _runtime_games.run(
                client,
                year=2024,
                team="Penn State",
            )

    assert initial.actual_http_attempts == 1
    assert refreshed.actual_http_attempts == 1
    assert cached.actual_http_attempts == 0
    assert calls == 2


@pytest.mark.asyncio
async def test_outputs_only_checkpoints_final_workflow_values(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reuse an exported dataset boundary without memoizing its source node."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "outputs-only-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=SQLiteCacheConfig(path=tmp_path / "responses.sqlite3"),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            first = await _runtime_workflow.run(
                client,
                year=2024,
                team="Penn State",
                policy=ExecutionPolicy(checkpoint_mode="outputs_only"),
            )
            second = await _runtime_workflow.run(
                client,
                year=2024,
                team="Penn State",
            )

    assert first.reused_nodes == 0
    assert any(not node.checkpoint_eligible for node in first.lineage)
    assert any(node.checkpoint_eligible for node in first.lineage)
    assert second.reused_nodes == 1


@pytest.mark.asyncio
async def test_workflow_returns_named_frames_and_aliases_existing_content(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Expose named workflow results without duplicating their table object."""

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/games"
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "workflow-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            outputs = await _runtime_workflow(
                client,
                year=2024,
                team="Penn State",
            )

    assert tuple(outputs) == ("games",)
    assert isinstance(outputs["games"], pd.DataFrame)


@pytest.mark.asyncio
async def test_explicit_recovery_reuses_sources_after_downstream_revision_change(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Use Merkle compatibility instead of requiring an identical whole graph."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    @step(id="tests.revised_recovery_step", revision=1, output=Game)
    def failing(rows: list[Game]) -> list[Game]:
        raise RuntimeError("injected downstream failure")

    @step(id="tests.revised_recovery_step", revision=2, output=Game)
    def fixed(rows: list[Game]) -> list[Game]:
        return rows

    selected_step = failing

    @dataset(
        id="tests.revised_recovery_dataset",
        revision=1,
        row=Game,
        grain="one game",
        keys=("id",),
        order_by=("season", "week", "id"),
    )
    def recoverable(*, year: int, team: str) -> RecipeRef[list[Game]]:
        return selected_step(games(year=year, team=team))

    root = tmp_path / "analytics"
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "revised-recovery-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=root),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await recoverable.run(client, year=2024, team="Penn State")

            selected_step = fixed
            recovered = await recoverable.run(
                client,
                year=2024,
                team="Penn State",
                resume_from=exc_info.value.run_id,
            )

    assert recovered.parent_run_id == exc_info.value.run_id
    assert recovered.actual_http_attempts == 0
    assert recovered.reused_nodes >= 1
    assert calls == 1


@pytest.mark.asyncio
async def test_recompute_source_bypasses_parent_snapshot_during_recovery(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Let an expert force retrieval while preserving normal cache policy."""
    calls = 0
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    @step(
        id="tests.forced_source_recovery_step",
        revision=1,
        output=Game,
        deterministic=False,
    )
    def intermittent(rows: list[Game]) -> list[Game]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected downstream failure")
        return rows

    @dataset(
        id="tests.forced_source_recovery_dataset",
        revision=1,
        row=Game,
        grain="one game",
        keys=("id",),
        order_by=("season", "week", "id"),
    )
    def recoverable(*, year: int, team: str) -> RecipeRef[list[Game]]:
        return intermittent(games(year=year, team=team))

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "forced-source-recovery-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            plan = await recoverable.plan(client, year=2024, team="Penn State")
            source_id = plan.nodes[0].node_id
            with pytest.raises(CFBDRunError) as exc_info:
                await recoverable.run(client, year=2024, team="Penn State")

            recovered = await recoverable.run(
                client,
                year=2024,
                team="Penn State",
                resume_from=exc_info.value.run_id,
                policy=ExecutionPolicy(recompute_nodes=(source_id,)),
            )

    assert recovered.actual_http_attempts == 1
    assert recovered.reused_nodes == 0
    assert calls == 2


@pytest.mark.asyncio
async def test_direct_call_recovers_from_newest_compatible_failed_run(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Make the simple path preserve a failed run's validated source snapshot."""
    calls = 0
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    @step(
        id="tests.intermittent_recovery_step",
        revision=1,
        output=Game,
        deterministic=False,
    )
    def intermittent(rows: list[Game]) -> list[Game]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("injected transient failure")
        return rows

    @dataset(
        id="tests.automatic_recovery_dataset",
        revision=1,
        row=Game,
        grain="one game",
        keys=("id",),
        order_by=("season", "week", "id"),
    )
    def recoverable(*, year: int, team: str) -> RecipeRef[list[Game]]:
        return intermittent(games(year=year, team=team))

    config = AnalyticsConfig(root=tmp_path / "analytics")
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "automatic-recovery-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=config,
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await recoverable(client, year=2024, team="Penn State")

            frame = await recoverable(client, year=2024, team="Penn State")
            fresh_frame = await recoverable(client, year=2024, team="Penn State")

    runs = await list_runs(config)
    assert isinstance(frame, pd.DataFrame)
    assert isinstance(fresh_frame, pd.DataFrame)
    assert runs[0].state == "completed"
    assert runs[0].parent_run_id is None
    assert runs[1].parent_run_id == exc_info.value.run_id
    assert calls == 2


@pytest.mark.asyncio
async def test_literal_endpoint_requirements_fail_during_pure_compilation() -> None:
    """Reject an invalid registered source request before opening persistence."""
    client = CFBDClient("runtime-key")

    with pytest.raises(CFBDRecipeCompilationError, match="endpoint contract"):
        await _runtime_games.plan(client, year=1800, team="Penn State")
