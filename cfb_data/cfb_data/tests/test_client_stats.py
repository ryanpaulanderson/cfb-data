"""Test Stats endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.stats import (
    AdvancedGameStat,
    AdvancedSeasonStat,
    GameHavocStats,
    PlayerGameSuccessRate,
    PlayerSeasonSuccessRate,
    PlayerStat,
    StatCategory,
    TeamStat,
)

from cfb_data import (
    CFBDClient,
    CFBDRequestValidationError,
    CFBDResponseValidationError,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _success_split() -> dict[str, object]:
    """Return one complete player success-rate split."""
    return {"plays": 20, "successes": 9, "successRate": 0.45}


def _season_unit(*, defense: bool) -> dict[str, object]:
    """Return one complete advanced-season unit."""
    passing_downs: dict[str, object] = {
        "rate": 0.3,
        "ppa": 0.2,
        "successRate": 0.35,
        "explosiveness": None,
    }
    if defense:
        passing_downs["totalPPA"] = 12.5
    return {
        "plays": 700,
        "drives": 120,
        "ppa": 0.15,
        "totalPPA": 105.0,
        "successRate": 0.42,
        "explosiveness": 1.1,
        "powerSuccess": None,
        "stuffRate": 0.15,
        "lineYards": 3.0,
        "lineYardsTotal": 1200,
        "secondLevelYards": 0.8,
        "secondLevelYardsTotal": 320,
        "openFieldYards": 0.7,
        "openFieldYardsTotal": 280,
        "totalOpportunies": 55,
        "pointsPerOpportunity": 4.1,
        "fieldPosition": {"averageStart": 70.0, "averagePredictedPoints": 1.2},
        "havoc": {"total": 0.18, "frontSeven": 0.1, "db": 0.08},
        "standardDowns": {
            "rate": 0.7,
            "ppa": 0.1,
            "successRate": 0.46,
            "explosiveness": 0.9,
        },
        "passingDowns": passing_downs,
        "rushingPlays": {
            "rate": 0.55,
            "ppa": 0.12,
            "totalPPA": 46.0,
            "successRate": 0.43,
            "explosiveness": 0.8,
        },
        "passingPlays": {
            "rate": 0.45,
            "ppa": 0.18,
            "totalPPA": 59.0,
            "successRate": 0.41,
            "explosiveness": 1.4,
        },
    }


def _game_unit(*, defense: bool) -> dict[str, object]:
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


def _havoc_unit() -> dict[str, float]:
    """Return one complete game havoc unit."""
    return {
        "totalPlays": 60,
        "totalHavocEvents": 9,
        "frontSevenHavocEvents": 5,
        "dbHavocEvents": 4,
        "havocRate": 0.15,
        "frontSevenHavocRate": 0.083,
        "dbHavocRate": 0.067,
    }


def _payloads() -> dict[str, object]:
    """Return representative valid payloads for every Stats route."""
    return {
        "/stats/player/season": [
            {
                "season": 2024,
                "playerId": "4685495",
                "player": "Alex Orji",
                "position": "QB",
                "team": "Michigan",
                "conference": "Big Ten",
                "category": "passing",
                "statType": "ATT",
                "stat": "45",
            }
        ],
        "/stats/player/success": [
            {
                "season": 2024,
                "id": "4685495",
                "name": "Alex Orji",
                "position": "QB",
                "team": "Michigan",
                "conference": "B1G",
                "passing": _success_split(),
                "rushing": _success_split(),
            }
        ],
        "/stats/player/success/game": [
            {
                "season": 2024,
                "seasonType": "regular",
                "week": 1,
                "gameId": 401628452,
                "id": "4685495",
                "name": "Alex Orji",
                "position": "QB",
                "team": "Michigan",
                "conference": "B1G",
                "opponent": "Fresno State",
                "passing": _success_split(),
                "rushing": _success_split(),
            }
        ],
        "/stats/season": [
            {
                "season": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "statName": "firstDowns",
                "statValue": 210,
            },
            {
                "season": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "statName": "timeOfPossession",
                "statValue": "22041",
            },
        ],
        "/stats/categories": ["completionAttempts", "firstDowns"],
        "/stats/season/advanced": [
            {
                "season": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "offense": _season_unit(defense=False),
                "defense": _season_unit(defense=True),
            }
        ],
        "/stats/game/advanced": [
            {
                "gameId": 401628452,
                "season": 2024,
                "seasonType": "regular",
                "week": 1,
                "team": "Michigan",
                "opponent": "Fresno State",
                "offense": _game_unit(defense=False),
                "defense": _game_unit(defense=True),
            }
        ],
        "/stats/game/havoc": [
            {
                "gameId": 401628452,
                "season": 2024,
                "seasonType": "regular",
                "week": 1,
                "team": "Michigan",
                "conference": "B1G",
                "opponent": "Fresno State",
                "opponentConference": "MWC",
                "offense": _havoc_unit(),
                "defense": _havoc_unit(),
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_stats_routes_preserve_public_dataframe_contract(
    api_server: ServerFactory,
    backend: str,
) -> None:
    """Validate every route, alias, schema, nested value, and scalar union."""
    payloads = _payloads()
    observed: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frames = [
                (
                    await client.stats.player_season(
                        year=2024,
                        conference="B1G",
                        team="Michigan",
                        start_week=1,
                        end_week=2,
                        season_type="regular",
                        category="passing",
                    ),
                    PlayerStat,
                ),
                (
                    await client.stats.player_season_success(
                        year=2024,
                        team="Michigan",
                        player_id=4685495,
                        season_type="regular",
                        start_week=1,
                        end_week=2,
                        threshold=10,
                        exclude_garbage_time=True,
                    ),
                    PlayerSeasonSuccessRate,
                ),
                (
                    await client.stats.player_game_success(
                        year=2024,
                        week=1,
                        season_type="regular",
                        conference="B1G",
                        team="Michigan",
                        player_id=4685495,
                        threshold=2,
                        exclude_garbage_time=False,
                    ),
                    PlayerGameSuccessRate,
                ),
                (
                    await client.stats.team_season(
                        year=2024,
                        team="Michigan",
                        conference="B1G",
                        start_week=1,
                        end_week=2,
                        classification="fbs",
                    ),
                    TeamStat,
                ),
                (await client.stats.categories(), StatCategory),
                (
                    await client.stats.advanced_season(
                        year=2024,
                        team="Michigan",
                        exclude_garbage_time=True,
                        start_week=1,
                        end_week=2,
                        classification="fbs",
                    ),
                    AdvancedSeasonStat,
                ),
                (
                    await client.stats.advanced_game(
                        year=2024,
                        team="Michigan",
                        week=1,
                        opponent="Fresno State",
                        exclude_garbage_time=True,
                        season_type="regular",
                    ),
                    AdvancedGameStat,
                ),
                (
                    await client.stats.game_havoc(
                        year=2024,
                        team="Michigan",
                        week=1,
                        opponent="Fresno State",
                        season_type="regular",
                    ),
                    GameHavocStats,
                ),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, row_model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(row_model.model_fields)

    team_stats = frames[3][0]
    categories = frames[4][0]
    season_advanced = frames[5][0]
    if backend == "pandas":
        assert list(team_stats["stat_value"]) == [210, "22041"]
        assert team_stats["stat_value"].dtype == object
        assert list(categories["category"]) == ["completionAttempts", "firstDowns"]
        assert season_advanced.loc[0, "defense"]["passing_downs"]["total_ppa"] == 12.5
    else:
        assert team_stats["stat_value"].to_list() == [210, "22041"]
        assert team_stats.schema["stat_value"] == pl.Object
        assert categories["category"].to_list() == [
            "completionAttempts",
            "firstDowns",
        ]
        assert season_advanced["defense"][0]["passing_downs"]["total_ppa"] == 12.5

    assert observed["/stats/player/season"]["startWeek"] == "1"
    assert observed["/stats/player/season"]["seasonType"] == "regular"
    assert observed["/stats/player/success"]["playerId"] == "4685495"
    assert observed["/stats/player/success"]["excludeGarbageTime"] == "true"
    assert observed["/stats/player/success/game"]["excludeGarbageTime"] == "false"
    assert observed["/stats/season"]["classification"] == "fbs"
    assert observed["/stats/categories"] == {}
    assert observed["/stats/season/advanced"]["endWeek"] == "2"
    assert observed["/stats/game/advanced"]["opponent"] == "Fresno State"
    assert observed["/stats/game/havoc"]["seasonType"] == "regular"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_stats_empty_frames_keep_exact_schemas(
    api_server: ServerFactory,
    backend: str,
) -> None:
    """Return typed empty frames for scalar arrays and heterogeneous values."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            categories = await client.stats.categories()
            team_stats = await client.stats.team_season(year=2024)

    assert list(categories.columns) == ["category"]
    assert list(team_stats.columns) == list(TeamStat.model_fields)
    assert len(categories) == len(team_stats) == 0
    if backend == "pandas":
        assert team_stats["stat_value"].dtype == object
    else:
        assert team_stats.schema["stat_value"] == pl.Object


@pytest.mark.asyncio
async def test_stats_request_validation_stops_before_http(
    api_server: ServerFactory,
) -> None:
    """Reject missing selectors, reversed ranges, and invalid values locally."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            invalid_calls = [
                client.stats.player_season_success(),
                client.stats.player_game_success(year=2024),
                client.stats.team_season(),
                client.stats.advanced_season(year=2024, start_week=5, end_week=4),
                client.stats.advanced_game(team=""),
                client.stats.game_havoc(year=1800),
            ]
            for call in invalid_calls:
                with pytest.raises(CFBDRequestValidationError):
                    await call

    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload", "invoke"),
    [
        (
            "/stats/categories",
            ["passing", 42],
            lambda client: client.stats.categories(),
        ),
        (
            "/stats/season",
            [
                {
                    "season": 2024,
                    "team": "Michigan",
                    "conference": "Big Ten",
                    "statName": "games",
                    "statValue": True,
                }
            ],
            lambda client: client.stats.team_season(year=2024),
        ),
        (
            "/stats/game/advanced",
            [{"gameId": 401628452}],
            lambda client: client.stats.advanced_game(year=2024, week=1),
        ),
    ],
)
async def test_stats_reject_malformed_responses_before_conversion(
    api_server: ServerFactory,
    path: str,
    payload: object,
    invoke: Callable[[CFBDClient[pd.DataFrame]], object],
) -> None:
    """Reject invalid scalar arrays, unions, and nested response objects."""

    async def handler(request: web.Request) -> web.Response:
        assert request.path == path
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError):
                await invoke(client)
