"""Validate the independently composable team-games recipe."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    CFBDRunError,
    ExecutionPolicy,
)
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


def _advanced_unit(*, defense: bool) -> dict[str, object]:
    """Return one complete advanced-game unit."""
    return {
        "plays": 62,
        "drives": 11,
        "ppa": 0.1,
        "totalPPA": 6.2,
        "successRate": 0.44,
        "explosiveness": 1.2,
        "powerSuccess": None,
        "stuffRate": 0.16,
        "lineYards": 3.1,
        "lineYardsTotal": 110,
        "secondLevelYards": 0.9,
        "secondLevelYardsTotal": 31,
        "openFieldYards": 0.5 if defense else None,
        "openFieldYardsTotal": None if defense else 18,
        "standardDowns": {
            "ppa": 0.05,
            "successRate": 0.48,
            "explosiveness": 0.9,
        },
        "passingDowns": {
            "ppa": 0.2,
            "successRate": 0.32,
            "explosiveness": None,
        },
        "rushingPlays": {
            "ppa": 0.12,
            "totalPPA": 3.4,
            "successRate": 0.46,
            "explosiveness": 0.8,
        },
        "passingPlays": {
            "ppa": 0.08,
            "totalPPA": 2.8,
            "successRate": 0.42,
            "explosiveness": 1.5,
        },
    }


def _advanced_payload(game_id: int) -> list[dict[str, object]]:
    """Return advanced metrics for the requested team perspective."""
    return [
        {
            "gameId": game_id,
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "team": "Alabama",
            "opponent": "Western Kentucky",
            "offense": _advanced_unit(defense=False),
            "defense": _advanced_unit(defense=True),
        }
    ]


def _havoc_unit() -> dict[str, float]:
    """Return one complete game-havoc unit."""
    return {
        "totalPlays": 60,
        "totalHavocEvents": 9,
        "frontSevenHavocEvents": 5,
        "dbHavocEvents": 4,
        "havocRate": 0.15,
        "frontSevenHavocRate": 0.083,
        "dbHavocRate": 0.067,
    }


def _havoc_payload(game_id: int) -> list[dict[str, object]]:
    """Return havoc metrics for the requested team perspective."""
    return [
        {
            "gameId": game_id,
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "team": "Alabama",
            "conference": "SEC",
            "opponent": "Western Kentucky",
            "opponentConference": None,
            "offense": _havoc_unit(),
            "defense": _havoc_unit(),
        }
    ]


def _ppa_payload(game_id: int) -> list[dict[str, object]]:
    """Return game PPA for the requested team perspective."""
    unit = {
        "overall": 0.2,
        "passing": 0.3,
        "rushing": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
    }
    return [
        {
            "gameId": game_id,
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "team": "Alabama",
            "conference": "SEC",
            "opponent": "Western Kentucky",
            "offense": unit,
            "defense": unit,
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
async def test_requested_enrichments_preserve_universe_and_four_way_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Attach requested game-context enrichments across every option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    stats_payload = _team_stats_payload(int(game_response["id"]))
    payloads: dict[str, object] = {
        "/games": [game_response],
        "/games/teams": stats_payload,
        "/stats/game/advanced": _advanced_payload(int(game_response["id"])),
        "/stats/game/havoc": _havoc_payload(int(game_response["id"])),
        "/ppa/games": _ppa_payload(int(game_response["id"])),
    }
    calls: dict[str, int] = dict.fromkeys(payloads, 0)

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(payloads[request.path])

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
                    include_advanced_stats=True,
                    include_havoc=True,
                    include_ppa=True,
                    exclude_garbage_time=True,
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
            assert restored["advanced_stats_coverage"].tolist() == [
                TeamStatsCoverage.present,
                TeamStatsCoverage.not_requested,
            ]
            assert restored["havoc_coverage"].tolist() == [
                TeamStatsCoverage.present,
                TeamStatsCoverage.not_requested,
            ]
            assert restored["ppa_coverage"].tolist() == [
                TeamStatsCoverage.present,
                TeamStatsCoverage.not_requested,
            ]
            assert [stat["category"] for stat in restored.loc[0, "team_stats"]] == [
                "totalYards",
                "turnovers",
            ]
            assert restored.loc[0, "advanced_offense"]["plays"] == 62
            assert restored.loc[0, "havoc_defense"]["total_havoc_events"] == 9
            assert restored.loc[0, "ppa_offense"]["overall"] == 0.2

    assert calls == dict.fromkeys(payloads, 4)
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


@pytest.mark.asyncio
async def test_empty_requested_enrichment_is_explicit_for_selected_perspective(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Represent a valid-empty enrichment without changing the base universe."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response] if request.path == "/games" else [])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-games-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame = await team_games(
                client,
                year=2024,
                team="Alabama",
                include_advanced_stats=True,
            )

    assert len(frame) == 2
    assert frame["advanced_stats_coverage"].tolist() == [
        TeamStatsCoverage.empty,
        TeamStatsCoverage.not_requested,
    ]
    assert frame["advanced_offense"].tolist() == [None, None]


@pytest.mark.asyncio
async def test_conflicting_enrichment_fails_with_game_context_intact(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject a name-keyed enrichment that conflicts with its game opponent."""
    advanced = _advanced_payload(int(game_response["id"]))
    advanced[0]["opponent"] = "A Different Team"

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [game_response] if request.path == "/games" else advanced
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
                    include_advanced_stats=True,
                )

    assert exc_info.value.node_id.endswith("cfbd.team_games.normalize@1")
    assert exc_info.value.category == "ValueError"


@pytest.mark.asyncio
async def test_game_ppa_requires_explicit_year_during_pure_planning() -> None:
    """Reject season-shaped PPA enrichment before any operational I/O."""
    client = CFBDClient("team-games-key")

    with pytest.raises(CFBDRecipeCompilationError, match="builder failed"):
        await team_games.plan(
            client,
            game_id=401628347,
            include_ppa=True,
        )
