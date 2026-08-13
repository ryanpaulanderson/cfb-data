"""Test Rankings and Betting endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.betting import BettingGame
from cfb_data.rankings import PollWeek
from pydantic import ValidationError

from cfb_data import BettingLinesRequest, CFBDClient, RankingsRequest

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _rankings_payload() -> list[dict[str, object]]:
    return [
        {
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "polls": [
                {
                    "poll": "AP Top 25",
                    "isFinal": None,
                    "ranks": [
                        {
                            "rank": 9,
                            "teamId": 130,
                            "school": "Michigan",
                            "conference": "Big Ten",
                            "firstPlaceVotes": 0,
                            "points": 995,
                        }
                    ],
                }
            ],
        }
    ]


def _betting_payload() -> list[dict[str, object]]:
    return [
        {
            "id": 401628455,
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "startDate": "2024-08-31T19:30:00-04:00",
            "homeTeamId": 130,
            "homeTeam": "Michigan",
            "homeConference": "Big Ten",
            "homeClassification": "fbs",
            "homeScore": 30,
            "awayTeamId": 278,
            "awayTeam": "Fresno State",
            "awayConference": "Mountain West",
            "awayClassification": "fbs",
            "awayScore": 10,
            "lines": [
                {
                    "provider": "DraftKings",
                    "spread": -21.5,
                    "formattedSpread": "Michigan -21.5",
                    "spreadOpen": -22.0,
                    "overUnder": 45.5,
                    "overUnderOpen": 46.0,
                    "homeMoneyline": -1800,
                    "awayMoneyline": 900,
                }
            ],
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_rankings_and_betting_preserve_nested_dataframe_contract(
    api_server: ServerFactory, backend: str
) -> None:
    payloads = {
        "/rankings": _rankings_payload(),
        "/lines": _betting_payload(),
    }
    observed: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            rankings = await client.rankings.list(year=2024, poll="cfp", latest=True)
            betting = await client.betting.lines(
                year=2024, week=1, team="Michigan", provider="DraftKings"
            )

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    assert isinstance(rankings, expected_type)
    assert isinstance(betting, expected_type)
    assert list(rankings.columns) == list(PollWeek.model_fields)
    assert list(betting.columns) == list(BettingGame.model_fields)
    assert len(rankings) == len(betting) == 1

    if backend == "pandas":
        assert rankings.loc[0, "polls"][0]["ranks"][0]["school"] == "Michigan"
        assert betting.loc[0, "lines"][0]["provider"] == "DraftKings"
        assert betting.loc[0, "start_date"].tzinfo is UTC
    else:
        assert rankings["polls"][0].to_list()[0]["ranks"][0]["school"] == "Michigan"
        assert betting["lines"][0].to_list()[0]["provider"] == "DraftKings"
        assert betting["start_date"][0].utcoffset().total_seconds() == 0

    assert observed["/rankings"] == {
        "year": "2024",
        "poll": "cfp",
        "latest": "true",
    }
    assert observed["/lines"]["provider"] == "DraftKings"


def test_rankings_and_betting_reject_invalid_selector_combinations() -> None:
    with pytest.raises(ValidationError, match="cannot both be true"):
        RankingsRequest(year=2024, poll="cfp", latest=True, final=True)
    with pytest.raises(ValidationError, match="poll='cfp'"):
        RankingsRequest(year=2024, latest=True)
    with pytest.raises(ValidationError):
        BettingLinesRequest()


def test_betting_rejects_naive_start_timestamp() -> None:
    payload = _betting_payload()[0]
    payload["startDate"] = "2024-08-31T19:30:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        BettingGame.model_validate(payload)
