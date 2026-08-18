"""Test Ratings endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.ratings import (
    ConferenceSP,
    ExpandedTeamSRS,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)
from pydantic import ValidationError

from cfb_data import CFBDClient, CFBDResponseValidationError

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _offense(*, ranked: bool) -> dict[str, object]:
    values: dict[str, object] = {
        "rating": 30.0,
        "success": None,
        "explosiveness": None,
        "rushing": None,
        "passing": None,
        "standardDowns": None,
        "passingDowns": None,
        "runRate": None,
        "pace": None,
    }
    if ranked:
        values = {"ranking": 10, **values}
    return values


def _defense(*, ranked: bool) -> dict[str, object]:
    values: dict[str, object] = {
        "rating": 20.0,
        "success": None,
        "explosiveness": None,
        "rushing": None,
        "passing": None,
        "standardDowns": None,
        "passingDowns": None,
        "havoc": {"total": None, "frontSeven": None, "db": None},
    }
    if ranked:
        values = {"ranking": 12, **values}
    return values


def _payloads() -> dict[str, object]:
    return {
        "/ratings/core": [
            {
                "year": 2024,
                "throughSeasonType": "postseason",
                "throughWeek": 16,
                "team": "Michigan",
                "conference": "Big Ten",
                "overall": 4.2,
                "offense": 2.1,
                "defense": -2.1,
                "offensePlays": 700,
                "defensePlays": 680,
                "modelVersion": "1.0",
            }
        ],
        "/ratings/sp": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "rating": 20.0,
                "ranking": 10,
                "secondOrderWins": None,
                "sos": None,
                "offense": _offense(ranked=True),
                "defense": _defense(ranked=True),
                "specialTeams": {"rating": 1.0},
            },
            {
                "year": 2024,
                "team": "nationalAverages",
                "rating": 0.0,
                "ranking": None,
                "secondOrderWins": None,
                "sos": None,
                "offense": _offense(ranked=True),
                "defense": _defense(ranked=True),
                "specialTeams": {"rating": 0.0},
            },
        ],
        "/ratings/sp/conferences": [
            {
                "year": 2024,
                "conference": "Big Ten",
                "rating": 15.0,
                "secondOrderWins": None,
                "sos": None,
                "offense": _offense(ranked=False),
                "defense": _defense(ranked=False),
                "specialTeams": {"rating": None},
            }
        ],
        "/ratings/srs": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "division": None,
                "rating": 10.0,
                "ranking": 12,
            }
        ],
        "/ratings/srs/expanded": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "division": None,
                "rating": 10.0,
                "ranking": 12,
                "classification": "fbs",
            }
        ],
        "/ratings/elo": [
            {"year": 2024, "team": "Michigan", "conference": "Big Ten", "elo": 1600}
        ],
        "/ratings/fpi": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "fpi": 12.5,
                "resumeRanks": {
                    "strengthOfRecord": 10,
                    "fpi": 12,
                    "averageWinProbability": 9,
                    "strengthOfSchedule": 20,
                    "remainingStrengthOfSchedule": None,
                    "gameControl": 11,
                },
                "efficiencies": {
                    "overall": 80.0,
                    "offense": 75.0,
                    "defense": 85.0,
                    "specialTeams": 70.0,
                },
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_ratings_routes_preserve_public_dataframe_contract(
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
                (await client.ratings.core(year=2024, team="Michigan"), TeamCoreRating),
                (await client.ratings.sp(year=2024, team="Michigan"), TeamSP),
                (
                    await client.ratings.conference_sp(
                        year=2024, conference="B1G", classification="fbs"
                    ),
                    ConferenceSP,
                ),
                (await client.ratings.srs(year=2024, team="Michigan"), TeamSRS),
                (
                    await client.ratings.expanded_srs(
                        year=2024, team="Michigan", classification="fbs"
                    ),
                    ExpandedTeamSRS,
                ),
                (
                    await client.ratings.elo(
                        year=2024, week=10, season_type="regular", team="Michigan"
                    ),
                    TeamElo,
                ),
                (await client.ratings.fpi(year=2024, team="Michigan"), TeamFPI),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        expected_rows = 2 if model is TeamSP else 1
        assert len(frame) == expected_rows

    assert observed["/ratings/sp/conferences"]["classification"] == "fbs"
    assert observed["/ratings/elo"] == {
        "year": "2024",
        "week": "10",
        "seasonType": "regular",
        "team": "Michigan",
    }


@pytest.mark.asyncio
async def test_sp_validation_preserves_nested_null_rating_diagnostics(
    api_server: ServerFactory,
) -> None:
    """Report the field path and numeric type mismatch seen in issue 89."""
    payload = _payloads()["/ratings/sp"]
    assert isinstance(payload, list)
    first_row = payload[0]
    assert isinstance(first_row, dict)
    offense = first_row["offense"]
    assert isinstance(offense, dict)
    offense["rating"] = None

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payload)

    api_key = "never-expose-api-key"
    async with api_server(handler) as base_url:
        async with CFBDClient(api_key, base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError) as exc_info:
                await client.ratings.sp(team="Penn State")

    cause = exc_info.value.__cause__
    assert isinstance(cause, ValidationError)
    detail = cause.errors(include_url=False)[0]
    assert detail["loc"] == (0, "offense", "rating")
    assert detail["type"] == "float_type"
    assert detail["input"] is None
    assert "valid number" in str(cause)
    assert "input_type=NoneType" in str(cause)
    assert api_key not in repr(exc_info.value)
    assert api_key not in repr(cause)
