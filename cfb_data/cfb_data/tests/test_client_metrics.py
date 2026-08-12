"""Test Metrics endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.metrics import (
    FieldGoalExpectedPoints,
    PlayerGamePredictedPointsAdded,
    PlayerSeasonPredictedPointsAdded,
    PlayWinProbability,
    PredictedPointsValue,
    PregameWinProbability,
    TeamGamePredictedPointsAdded,
    TeamSeasonPredictedPointsAdded,
)

from cfb_data import (
    CFBDClient,
    CFBDRequestValidationError,
    CFBDResponseValidationError,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _season_unit() -> dict[str, object]:
    return {
        "overall": 0.2,
        "passing": 0.3,
        "rushing": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
        "cumulative": {"total": 100.0, "passing": 60.0, "rushing": 40.0},
    }


def _game_unit() -> dict[str, float]:
    return {
        "overall": 0.2,
        "passing": 0.3,
        "rushing": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
    }


def _split() -> dict[str, float]:
    return {
        "all": 0.2,
        "pass": 0.3,
        "rush": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
        "standardDowns": 0.15,
        "passingDowns": 0.25,
    }


def _payloads() -> dict[str, object]:
    return {
        "/ppa/predicted": [{"yardLine": 75, "predictedPoints": 2.4}],
        "/ppa/teams": [
            {
                "season": 2024,
                "conference": "B1G",
                "team": "Michigan",
                "offense": _season_unit(),
                "defense": _season_unit(),
            }
        ],
        "/ppa/games": [
            {
                "gameId": 401628452,
                "season": 2024,
                "week": 1,
                "seasonType": "regular",
                "team": "Michigan",
                "conference": "B1G",
                "opponent": "Fresno State",
                "offense": _game_unit(),
                "defense": _game_unit(),
            }
        ],
        "/ppa/players/games": [
            {
                "season": 2024,
                "week": 1,
                "seasonType": "regular",
                "id": "4426385",
                "name": "Donovan Edwards",
                "position": "RB",
                "team": "Michigan",
                "opponent": "Fresno State",
                "averagePPA": {"all": 0.2, "pass": None, "rush": 0.2},
            }
        ],
        "/ppa/players/season": [
            {
                "season": 2024,
                "id": "4426385",
                "name": "Donovan Edwards",
                "position": "RB",
                "team": "Michigan",
                "conference": "B1G",
                "averagePPA": _split(),
                "totalPPA": _split(),
            }
        ],
        "/metrics/wp": [
            {
                "gameId": 401628452,
                "playId": "1",
                "playText": "Kickoff",
                "homeId": 130,
                "home": "Michigan",
                "awayId": 278,
                "away": "Fresno State",
                "spread": -20.5,
                "homeBall": True,
                "homeScore": 0,
                "awayScore": 0,
                "yardLine": 75,
                "down": 1,
                "distance": 10,
                "homeWinProbability": 0.8,
                "playNumber": 0,
            },
            {
                "gameId": 401628452,
                "playId": "final",
                "playText": "Game ended",
                "homeId": 130,
                "home": "Michigan",
                "awayId": 278,
                "away": "Fresno State",
                "spread": -20.5,
                "homeBall": False,
                "homeScore": 30,
                "awayScore": 10,
                "yardLine": 50,
                "down": 0,
                "distance": 0,
                "homeWinProbability": 1.0,
                "playNumber": 100,
            },
        ],
        "/metrics/wp/pregame": [
            {
                "season": 2024,
                "seasonType": "regular",
                "week": 1,
                "gameId": 401628452,
                "homeTeam": "Michigan",
                "awayTeam": "Fresno State",
                "spread": -20.5,
                "homeWinProbability": 0.8,
            }
        ],
        "/metrics/fg/ep": [{"yardsToGoal": 20, "distance": 37, "expectedPoints": 2.2}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_metrics_routes_preserve_public_dataframe_contract(
    api_server: ServerFactory, backend: str
) -> None:
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
                    await client.metrics.predicted_points(down=1, distance=10),
                    PredictedPointsValue,
                ),
                (
                    await client.metrics.team_season_ppa(
                        year=2024,
                        team="Michigan",
                        exclude_garbage_time=True,
                        classification="fbs",
                    ),
                    TeamSeasonPredictedPointsAdded,
                ),
                (
                    await client.metrics.team_game_ppa(
                        year=2024, week=1, season_type="regular", team="Michigan"
                    ),
                    TeamGamePredictedPointsAdded,
                ),
                (
                    await client.metrics.player_game_ppa(
                        year=2024, week=1, team="Michigan", player_id=4426385
                    ),
                    PlayerGamePredictedPointsAdded,
                ),
                (
                    await client.metrics.player_season_ppa(
                        year=2024, team="Michigan", threshold=5
                    ),
                    PlayerSeasonPredictedPointsAdded,
                ),
                (
                    await client.metrics.win_probability(game_id=401628452),
                    PlayWinProbability,
                ),
                (
                    await client.metrics.pregame_win_probability(
                        year=2024, week=1, team="Michigan"
                    ),
                    PregameWinProbability,
                ),
                (
                    await client.metrics.field_goal_expected_points(),
                    FieldGoalExpectedPoints,
                ),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        expected_rows = 2 if model is PlayWinProbability else 1
        assert len(frame) == expected_rows

    assert observed["/ppa/teams"]["excludeGarbageTime"] == "true"
    assert observed["/ppa/games"]["seasonType"] == "regular"
    assert observed["/ppa/players/games"]["playerId"] == "4426385"
    assert observed["/metrics/wp"] == {"gameId": "401628452"}


@pytest.mark.asyncio
async def test_metrics_invalid_selector_stops_before_http(
    api_server: ServerFactory,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDRequestValidationError):
                await client.metrics.player_game_ppa(year=2024)

    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_metrics_empty_response_retains_typed_schema(
    api_server: ServerFactory, backend: str
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.metrics.predicted_points(down=1, distance=10)

    assert list(frame.columns) == list(PredictedPointsValue.model_fields)
    assert len(frame) == 0


@pytest.mark.asyncio
async def test_metrics_response_rejects_unknown_fields(
    api_server: ServerFactory,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [{"yardLine": 75, "predictedPoints": 2.4, "unexpected": True}]
        )

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError):
                await client.metrics.predicted_points(down=1, distance=10)
