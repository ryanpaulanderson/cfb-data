"""Validate the independently composable team-games recipe."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy
from cfb_data_recipes.team_games import (
    TeamGame,
    TeamGameResult,
    TeamStatsCoverage,
    team_games,
)

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

ServerFactory = Callable[[Callable[[web.Request], object]], object]


def _team_stats_payload(game_id: int) -> list[dict[str, object]]:
    """Return complete ordered conventional statistics for both game sides."""
    return [
        {
            "id": game_id,
            "teams": [
                {
                    "teamId": 333,
                    "team": "Alabama",
                    "conference": "SEC",
                    "homeAway": "home",
                    "points": 63,
                    "stats": [
                        {"category": "totalYards", "stat": "600"},
                        {"category": "turnovers", "stat": "1"},
                    ],
                },
                {
                    "teamId": 2459,
                    "team": "Western Kentucky",
                    "conference": None,
                    "homeAway": "away",
                    "points": 0,
                    "stats": [
                        {"category": "totalYards", "stat": "145"},
                        {"category": "turnovers", "stat": "3"},
                    ],
                },
            ],
        }
    ]


@pytest.mark.asyncio
async def test_base_recipe_produces_exactly_two_conservative_perspectives(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Derive two ID-keyed rows without requesting optional enrichment."""
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-games-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame = await team_games(client, year=2024, team="Alabama")

    assert paths == ["/games"]
    assert isinstance(frame, pd.DataFrame)
    assert tuple(frame.columns) == tuple(TeamGame.model_fields)
    assert list(zip(frame["game_id"], frame["team_id"], strict=True)) == [
        (401628347, 333),
        (401628347, 2459),
    ]
    assert frame["result"].tolist() == [TeamGameResult.win, TeamGameResult.loss]
    assert frame["point_differential"].tolist() == [63, -63]
    assert frame["team_stats_coverage"].tolist() == [
        TeamStatsCoverage.not_requested,
        TeamStatsCoverage.not_requested,
    ]
    assert frame["team_stats"].tolist() == [None, None]


@pytest.mark.asyncio
async def test_requested_stats_preserve_universe_and_four_way_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Attach complete ordered statistics identically across every option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    stats_payload = _team_stats_payload(int(game_response["id"]))
    calls: dict[str, int] = {"/games": 0, "/games/teams": 0}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        if request.path == "/games":
            return web.json_response([game_response])
        return web.json_response(stats_payload)

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    records: list[list[dict[str, object]]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "team-games-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run = await team_games.run(
                    client,
                    year=2024,
                    team="Alabama",
                    include_team_stats=True,
                    policy=ExecutionPolicy(
                        executor=executor,
                        dask_max_workers=1,
                    ),
                )
            digests.append(run.artifact.descriptor.content_digest)
            restored = run.artifact.load()
            records.append(restored.to_dict(orient="records"))
            assert len(restored) == 2
            assert restored["team_stats_coverage"].tolist() == [
                TeamStatsCoverage.present,
                TeamStatsCoverage.present,
            ]
            assert [stat["category"] for stat in restored.loc[0, "team_stats"]] == [
                "totalYards",
                "turnovers",
            ]

    assert calls == {"/games": 4, "/games/teams": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_requested_incomplete_stats_fail_without_shrinking_base_rows(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Fail requested enrichment when either stable perspective key is absent."""
    incomplete = _team_stats_payload(int(game_response["id"]))
    teams = incomplete[0]["teams"]
    assert isinstance(teams, list)
    incomplete[0]["teams"] = teams[:1]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [game_response] if request.path == "/games" else incomplete
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-games-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await team_games(
                    client,
                    year=2024,
                    team="Alabama",
                    include_team_stats=True,
                )

    assert exc_info.value.node_id.endswith("cfbd.team_games.normalize@1")
    assert exc_info.value.category == "ValueError"
