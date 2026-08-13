"""Test Recruiting endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.recruiting import (
    AggregatedTeamRecruiting,
    Recruit,
    TeamRecruitingRanking,
)
from pydantic import ValidationError

from cfb_data import CFBDClient, RecruitingGroupsRequest, RecruitingPlayersRequest

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _payloads() -> dict[str, object]:
    return {
        "/recruiting/players": [
            {
                "id": "12345",
                "athleteId": "4426385",
                "recruitType": "HighSchool",
                "year": 2024,
                "ranking": 25,
                "name": "Test Recruit",
                "school": "Test High",
                "committedTo": "Michigan",
                "position": "RB",
                "height": 72.5,
                "weight": 205,
                "stars": 4,
                "rating": 0.95,
                "city": "Ann Arbor",
                "stateProvince": "MI",
                "country": "USA",
                "hometownInfo": {
                    "latitude": 42.28,
                    "longitude": -83.74,
                    "fipsCode": "26161",
                },
            }
        ],
        "/recruiting/teams": [
            {"year": 2024, "rank": 16, "team": "Michigan", "points": 262.4}
        ],
        "/recruiting/groups": [
            {
                "team": "Michigan",
                "conference": "Big Ten",
                "positionGroup": "Running Back",
                "averageRating": 0.91,
                "totalRating": 1.82,
                "commits": "2",
                "averageStars": "4.0000",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_recruiting_routes_validate_and_normalize_all_public_grains(
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
                    await client.recruiting.players(
                        year=2024,
                        team="Michigan",
                        classification="HighSchool",
                    ),
                    Recruit,
                ),
                (
                    await client.recruiting.teams(year=2024, team="Michigan"),
                    TeamRecruitingRanking,
                ),
                (
                    await client.recruiting.groups(
                        team="Michigan",
                        recruit_type="HighSchool",
                        start_year=2020,
                        end_year=2024,
                    ),
                    AggregatedTeamRecruiting,
                ),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    groups = frames[2][0]
    assert groups["commits"][0] == 2
    assert groups["average_stars"][0] == 4.0
    assert observed["/recruiting/players"]["classification"] == "HighSchool"
    assert observed["/recruiting/groups"] == {
        "team": "Michigan",
        "recruitType": "HighSchool",
        "startYear": "2020",
        "endYear": "2024",
    }


def test_recruiting_requests_enforce_selectors_and_ranges() -> None:
    with pytest.raises(ValidationError):
        RecruitingPlayersRequest()
    with pytest.raises(ValidationError, match="start_year"):
        RecruitingGroupsRequest(start_year=2025, end_year=2024)
