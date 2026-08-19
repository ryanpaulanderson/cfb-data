"""Validate statically expanded first-party program history."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sized
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    ExecutionPolicy,
    RecipeRun,
    WorkflowOutputs,
)
from cfb_data_recipes.program_history import program_history

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]

_OUTPUTS = (
    "game_summaries",
    "team_games",
    "team_seasons",
    "recruiting_classes",
    "coach_seasons",
    "poll_rankings",
)
_PER_SEASON_SOURCES = {
    "/games",
    "/records",
    "/stats/season",
    "/stats/season/advanced",
    "/recruiting/teams",
    "/recruiting/players",
    "/rankings",
}


def _frame_length(value: object) -> int:
    """Return a frame length after narrowing the generic public value."""
    if not isinstance(value, Sized):
        raise AssertionError("Workflow output must be a sized eager frame")
    return len(value)


@pytest.mark.asyncio
async def test_workflow_expands_a_finite_range_and_deduplicates_games(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Compile two seasons and dispatch each exact source only once."""
    calls: dict[str, int] = {
        **{path: 0 for path in _PER_SEASON_SOURCES},
        "/coaches/seasons": 0,
    }

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "program-history-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            plan = await program_history.plan(
                client,
                team="Penn State",
                start_season=2023,
                end_season=2024,
            )
            outputs: WorkflowOutputs[object] = await program_history(
                client,
                team="Penn State",
                start_season=2023,
                end_season=2024,
            )

    assert tuple(outputs) == _OUTPUTS
    assert all(_frame_length(frame) == 0 for frame in outputs.values())
    assert calls == {
        **{path: 2 for path in _PER_SEASON_SOURCES},
        "/coaches/seasons": 1,
    }
    assert plan.worst_case_http_attempts == sum(calls.values())
    assert any(len(node.dependencies) == 2 for node in plan.nodes)


@pytest.mark.asyncio
async def test_workflow_rejects_unbounded_or_reversed_ranges() -> None:
    """Fail invalid expansion during pure compilation before I/O."""
    client = CFBDClient("program-history-key")

    with pytest.raises(CFBDRecipeCompilationError, match="builder failed"):
        await program_history.plan(
            client,
            team="Penn State",
            start_season=2024,
            end_season=2023,
        )
    with pytest.raises(CFBDRecipeCompilationError, match="builder failed"):
        await program_history.plan(
            client,
            team="Penn State",
            start_season=1900,
            end_season=1950,
            policy=ExecutionPolicy(max_http_attempts=10_000),
        )


@pytest.mark.asyncio
async def test_history_enrichments_expand_only_the_static_plan() -> None:
    """Expose dataset options without operational work during planning."""
    client = CFBDClient("program-history-key")

    base = await program_history.plan(
        client,
        team="Penn State",
        start_season=2024,
        end_season=2024,
    )
    enriched = await program_history.plan(
        client,
        team="Penn State",
        start_season=2024,
        end_season=2024,
        include_game_media=True,
        include_game_weather=True,
        include_team_game_stats=True,
        include_advanced_game_stats=True,
        include_game_havoc=True,
        include_game_ppa=True,
        include_team_season_ppa=True,
        include_team_talent=True,
        include_team_ats=True,
        include_returning_production=True,
        include_core_rating=True,
        include_sp_rating=True,
        include_srs_rating=True,
        include_elo_rating=True,
        include_fpi_rating=True,
        include_adjusted_team_metrics=True,
        include_coach_tenure=True,
        exclude_garbage_time=True,
    )

    node_ids = "\n".join(node.node_id for node in enriched.nodes)
    assert enriched.worst_case_http_attempts > base.worst_case_http_attempts
    assert "cfbd.games.media" in node_ids
    assert "cfbd.games.weather" in node_ids
    assert "cfbd.games.team_stats" in node_ids
    assert "cfbd.stats.advanced_game" in node_ids
    assert "cfbd.stats.game_havoc" in node_ids
    assert "cfbd.metrics.team_game_ppa" in node_ids
    assert "cfbd.metrics.team_season_ppa" in node_ids
    assert "cfbd.teams.talent" in node_ids
    assert "cfbd.teams.ats" in node_ids
    assert "cfbd.players.returning_production" in node_ids
    assert "cfbd.ratings.core" in node_ids
    assert "cfbd.ratings.sp" in node_ids
    assert "cfbd.ratings.srs" in node_ids
    assert "cfbd.ratings.elo" in node_ids
    assert "cfbd.ratings.fpi" in node_ids
    assert "cfbd.adjusted_metrics.team_season" in node_ids
    assert "cfbd.coaches.tenures" in node_ids


@pytest.mark.asyncio
async def test_workflow_has_four_way_artifact_and_graph_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce identical historical artifacts through every supported option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {
        **{path: 0 for path in _PER_SEASON_SOURCES},
        "/coaches/seasons": 0,
    }

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response([])

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    artifact_digests: list[dict[str, str]] = []
    graph_fingerprints: list[str] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "program-history-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                policy = ExecutionPolicy(executor=executor, dask_max_workers=1)
                plan = await program_history.plan(
                    client,
                    team="Penn State",
                    start_season=2024,
                    end_season=2024,
                    policy=policy,
                )
                run: RecipeRun[WorkflowOutputs[object]] = await program_history.run(
                    client,
                    team="Penn State",
                    start_season=2024,
                    end_season=2024,
                    policy=policy,
                )
            graph_fingerprints.append(plan.graph_fingerprint)
            artifact_digests.append(
                {
                    name: artifact.descriptor.content_digest
                    for name, artifact in run.artifacts.items()
                }
            )

    assert len(set(graph_fingerprints)) == 1
    assert all(result == artifact_digests[0] for result in artifact_digests[1:])
    assert calls == {
        **{path: 4 for path in _PER_SEASON_SOURCES},
        "/coaches/seasons": 4,
    }
