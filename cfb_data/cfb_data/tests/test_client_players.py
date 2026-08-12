"""Test Players endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.players import (
    PlayerSearchResult,
    PlayerSeasonOverview,
    PlayerTransfer,
    PlayerUsage,
    ReturningProduction,
)
from pydantic import ValidationError

from cfb_data import CFBDClient, TransferEligibility

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _usage() -> dict[str, float | None]:
    return {
        "overall": 0.3,
        "pass": None,
        "rush": 0.5,
        "firstDown": 0.4,
        "secondDown": 0.3,
        "thirdDown": 0.2,
        "standardDowns": 0.35,
        "passingDowns": 0.25,
    }


def _ppa() -> dict[str, float]:
    return {
        "all": 0.2,
        "pass": 0.1,
        "rush": 0.3,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
        "standardDowns": 0.15,
        "passingDowns": 0.25,
    }


def _payloads() -> dict[str, object]:
    return {
        "/player/search": [
            {
                "id": "4426385",
                "team": "Michigan",
                "name": "Donovan Edwards",
                "firstName": "Donovan",
                "lastName": "Edwards",
                "weight": 210,
                "height": 72.0,
                "jersey": 7,
                "position": "RB",
                "hometown": "West Bloomfield",
                "teamColor": "#00274C",
                "teamColorSecondary": "#FFCB05",
                "activeStartYear": 2021,
                "activeEndYear": 2024,
                "teamStints": [
                    {"team": "Michigan", "startYear": 2021, "endYear": 2024}
                ],
            }
        ],
        "/player/usage": [
            {
                "season": 2024,
                "id": "4426385",
                "name": "Donovan Edwards",
                "position": "RB",
                "team": "Michigan",
                "conference": "B1G",
                "usage": _usage(),
            }
        ],
        "/player/season/overview": {
            "season": 2024,
            "id": "4426385",
            "name": "Donovan Edwards",
            "position": "RB",
            "team": "Michigan",
            "conference": "Big Ten",
            "games": 13,
            "boxScoreStats": {
                "categories": [
                    {"name": "rushing", "stats": [{"name": "YDS", "value": "589"}]}
                ]
            },
            "usage": _usage(),
            "ppa": {"average": _ppa(), "total": _ppa()},
        },
        "/player/returning": [
            {
                "season": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "totalPPA": 10.0,
                "totalPassingPPA": 1.0,
                "totalReceivingPPA": 2.0,
                "totalRushingPPA": 7.0,
                "percentPPA": 0.5,
                "percentPassingPPA": 0.1,
                "percentReceivingPPA": 0.2,
                "percentRushingPPA": 0.7,
                "usage": 0.6,
                "passingUsage": 0.1,
                "receivingUsage": 0.2,
                "rushingUsage": 0.7,
            }
        ],
        "/player/portal": [
            {
                "season": 2024,
                "firstName": "Test",
                "lastName": "Player",
                "position": "RB",
                "origin": "Michigan",
                "destination": None,
                "transferDate": "2024-12-01T12:00:00-05:00",
                "rating": None,
                "stars": 4,
                "eligibility": "Immediate",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_players_routes_preserve_public_dataframe_contract(
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
                    await client.players.search(
                        search_term="Edwards", year=2024, team="Michigan"
                    ),
                    PlayerSearchResult,
                ),
                (
                    await client.players.usage(
                        year=2024,
                        team="Michigan",
                        player_id=4426385,
                        exclude_garbage_time=True,
                    ),
                    PlayerUsage,
                ),
                (
                    await client.players.season_overview(year=2024, player_id=4426385),
                    PlayerSeasonOverview,
                ),
                (
                    await client.players.returning_production(
                        year=2024, team="Michigan"
                    ),
                    ReturningProduction,
                ),
                (await client.players.transfer_portal(year=2024), PlayerTransfer),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    overview = frames[2][0]
    portal = frames[4][0]
    if backend == "pandas":
        assert overview.loc[0, "box_score_stats"]["categories"][0]["name"] == "rushing"
        assert portal.loc[0, "transfer_date"].tzinfo is UTC
    else:
        assert (
            overview["box_score_stats"]
            .struct.field("categories")[0]
            .to_list()[0]["name"]
            == "rushing"
        )
        assert portal["transfer_date"][0].utcoffset().total_seconds() == 0

    assert observed["/player/search"]["searchTerm"] == "Edwards"
    assert observed["/player/usage"]["excludeGarbageTime"] == "true"
    assert observed["/player/season/overview"]["playerId"] == "4426385"


def test_player_transfer_requires_aware_timestamp_and_enum() -> None:
    payload = _payloads()["/player/portal"]
    assert isinstance(payload, list)
    valid = PlayerTransfer.model_validate(payload[0])
    assert valid.eligibility is TransferEligibility.immediate
    invalid = dict(payload[0])
    invalid["transferDate"] = "2024-12-01T12:00:00"
    with pytest.raises(ValidationError, match="timezone-aware"):
        PlayerTransfer.model_validate(invalid)
