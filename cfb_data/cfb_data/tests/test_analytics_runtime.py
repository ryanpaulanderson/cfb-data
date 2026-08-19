"""Test public durable recipe execution through an owned client."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    ArtifactRef,
    CFBDRecipeCompilationError,
    ExecutionPolicy,
    RecipeRef,
    RecipeRun,
    dataset,
    workflow,
)
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games

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
async def test_literal_endpoint_requirements_fail_during_pure_compilation() -> None:
    """Reject an invalid registered source request before opening persistence."""
    client = CFBDClient("runtime-key")

    with pytest.raises(CFBDRecipeCompilationError, match="endpoint contract"):
        await _runtime_games.plan(client, year=1800, team="Penn State")
