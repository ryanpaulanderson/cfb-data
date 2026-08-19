"""Validate the independently composed team-season workflow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sized
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    ExecutionPolicy,
    RecipeRun,
    WorkflowOutputs,
)
from cfb_data_recipes.team_season_analysis import team_season_analysis

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]

_OUTPUTS = (
    "game_summaries",
    "team_games",
    "player_game_stats",
    "rosters",
    "team_seasons",
    "player_seasons",
    "coach_seasons",
)
_SOURCES = {
    "/games",
    "/games/players",
    "/roster",
    "/teams",
    "/records",
    "/stats/season",
    "/stats/season/advanced",
    "/stats/player/season",
    "/coaches/seasons",
}


def _frame_length(value: object) -> int:
    """Return a frame length after narrowing the generic public value."""
    if not isinstance(value, Sized):
        raise AssertionError("Workflow output must be a sized eager frame")
    return len(value)


@pytest.mark.asyncio
async def test_workflow_returns_named_outputs_and_deduplicates_sources(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Use ordinary dataset composition with one request per exact source."""
    calls: dict[str, int] = {path: 0 for path in _SOURCES}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-season-workflow-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            outputs: WorkflowOutputs[object] = await team_season_analysis(
                client,
                season=2024,
                team="Penn State",
            )

    assert tuple(outputs) == _OUTPUTS
    assert all(_frame_length(frame) == 0 for frame in outputs.values())
    assert calls == {path: 1 for path in _SOURCES}


@pytest.mark.asyncio
async def test_workflow_has_four_way_plan_and_artifact_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce identical named artifacts through every supported option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {path: 0 for path in _SOURCES}

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
    plan_fingerprints: list[str] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "team-season-workflow-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                policy = ExecutionPolicy(executor=executor, dask_max_workers=1)
                plan = await team_season_analysis.plan(
                    client,
                    season=2024,
                    team="Penn State",
                    policy=policy,
                )
                run: RecipeRun[
                    WorkflowOutputs[object]
                ] = await team_season_analysis.run(
                    client,
                    season=2024,
                    team="Penn State",
                    policy=policy,
                )
            plan_fingerprints.append(plan.graph_fingerprint)
            artifact_digests.append(
                {
                    name: artifact.descriptor.content_digest
                    for name, artifact in run.artifacts.items()
                }
            )

    assert len(set(plan_fingerprints)) == 1
    assert all(result == artifact_digests[0] for result in artifact_digests[1:])
    assert calls == {path: 4 for path in _SOURCES}
