"""Validate late-bound composition in the single-game workflow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sized
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    ExecutionPolicy,
    RecipeRun,
    WorkflowOutputs,
)
from cfb_data_recipes.single_game_analysis import single_game_analysis

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]

_OUTPUTS = (
    "game_summaries",
    "team_games",
    "player_game_stats",
    "drives",
    "plays",
    "betting_lines",
)
_SOURCES = {"/games", "/games/players", "/drives", "/plays", "/lines"}


def _required_game_value(game: dict[str, object], field: str) -> int | str:
    """Return a required scalar from a validated game fixture."""
    value = game[field]
    assert isinstance(value, int | str)
    return value


def _frame_length(value: object) -> int:
    """Return a frame length after narrowing the generic public value."""
    if not isinstance(value, Sized):
        raise AssertionError("Workflow output must be a sized eager frame")
    return len(value)


@pytest.mark.asyncio
async def test_workflow_binds_game_context_into_fixed_source_partitions(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Resolve source selectors from one validated upstream game."""
    calls: dict[str, int] = {path: 0 for path in _SOURCES}
    queries: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        queries[request.path] = dict(request.query)
        return web.json_response([game_response] if request.path == "/games" else [])

    game_id = _required_game_value(game_response, "id")
    assert isinstance(game_id, int)
    season = _required_game_value(game_response, "season")
    week = _required_game_value(game_response, "week")
    home_team = _required_game_value(game_response, "homeTeam")
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "single-game-workflow-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            plan = await single_game_analysis.plan(client, game_id=game_id)
            outputs: WorkflowOutputs[object] = await single_game_analysis(
                client,
                game_id=game_id,
            )

    assert tuple(outputs) == _OUTPUTS
    assert _frame_length(outputs["game_summaries"]) == 1
    assert _frame_length(outputs["team_games"]) == 2
    assert all(_frame_length(outputs[name]) == 0 for name in _OUTPUTS[2:])
    assert calls == {path: 1 for path in _SOURCES}
    assert queries["/drives"] == {
        "year": str(season),
        "week": str(week),
        "team": str(home_team),
    }
    assert queries["/plays"] == queries["/drives"]
    deferred = {
        parameter for node in plan.nodes for parameter in node.deferred_parameters
    }
    assert deferred == {"year", "week", "team"}


@pytest.mark.asyncio
async def test_workflow_exposes_exact_game_advanced_box_enrichment(
    api_server: ServerFactory,
    advanced_box_response: dict[str, object],
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Compose the scalar advanced-box source through team_games."""

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game_response])
        if request.path == "/game/box/advanced":
            return web.json_response(advanced_box_response)
        return web.json_response([])

    game_id = _required_game_value(game_response, "id")
    assert isinstance(game_id, int)
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "single-game-workflow-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            outputs: WorkflowOutputs[object] = await single_game_analysis(
                client,
                game_id=game_id,
                include_advanced_box=True,
            )

    team_frame = outputs["team_games"]
    assert isinstance(team_frame, pd.DataFrame)
    assert team_frame["advanced_box_coverage"].tolist() == ["present", "present"]
    assert team_frame.loc[0, "advanced_box"]["game_info"]["home_team"] == "Alabama"


@pytest.mark.asyncio
async def test_workflow_has_four_way_artifact_and_graph_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Produce identical named artifacts through every supported option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {path: 0 for path in _SOURCES}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response([game_response] if request.path == "/games" else [])

    game_id = _required_game_value(game_response, "id")
    assert isinstance(game_id, int)
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
                "single-game-workflow-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                policy = ExecutionPolicy(executor=executor, dask_max_workers=1)
                plan = await single_game_analysis.plan(
                    client,
                    game_id=game_id,
                    policy=policy,
                )
                run: RecipeRun[
                    WorkflowOutputs[object]
                ] = await single_game_analysis.run(
                    client,
                    game_id=game_id,
                    policy=policy,
                )
            graph_fingerprints.append(plan.graph_fingerprint)
            control_nodes = [
                node for node in plan.nodes if "operations.require_one" in node.node_id
            ]
            assert len(control_nodes) == 1
            assert control_nodes[0].placement == "coordinator"
            artifact_digests.append(
                {
                    name: artifact.descriptor.content_digest
                    for name, artifact in run.artifacts.items()
                }
            )

    assert len(set(graph_fingerprints)) == 1
    assert all(result == artifact_digests[0] for result in artifact_digests[1:])
    assert calls == {path: 4 for path in _SOURCES}
