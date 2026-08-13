"""Test Coaches endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.coaches import Coach, CoachProfile, CoachTenure, DetailedCoachSeason
from pydantic import ValidationError

from cfb_data import CFBDClient, CoachesRequest, CoachSeasonsRequest

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _record(*, games: int = 15, wins: int = 8, losses: int = 7) -> dict[str, object]:
    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": 0,
        "winPercentage": wins / games if games else None,
    }


def _season_summary() -> dict[str, object]:
    return {
        "teamId": 130,
        "school": "Michigan",
        "conference": "Big Ten",
        "year": 2024,
        **_record(),
        "preseasonRank": 9,
        "postseasonRank": None,
        "srs": 6.11,
        "spOverall": 8.2,
        "spOffense": -1.2,
        "spDefense": 10.4,
    }


def _detailed_season() -> dict[str, object]:
    return {
        **_record(),
        "coach": {"id": 24, "firstName": "Sherrone", "lastName": "Moore"},
        "team": {"id": 130, "school": "Michigan", "conference": "Big Ten"},
        "year": 2024,
        "preseasonRank": 9,
        "postseasonRank": None,
        "srs": 6.11,
        "spOverall": 8.2,
        "spOffense": -1.2,
        "spDefense": 10.4,
        "teamMetrics": {
            "spSpecialTeams": 1.2,
            "strengthOfSchedule": None,
            "secondOrderWins": None,
            "fpi": 7.4,
            "yearOverYear": {"wins": -7, "srs": -15.3, "spOverall": -12.4},
        },
        "recruiting": {"rank": 16, "points": 262.4, "talent": 890.1},
        "pollResume": {
            "preseasonRank": 9,
            "postseasonRank": None,
            "bestRank": 9,
            "weeksRanked": 10,
            "weeksTopTen": 2,
        },
        "attributionComplete": True,
        "recordSplits": {
            "conference": _record(games=9, wins=5, losses=4),
            "postseason": _record(games=1, wins=1, losses=0),
            "home": _record(games=8, wins=6, losses=2),
            "away": _record(games=5, wins=1, losses=4),
            "neutral": _record(games=2, wins=1, losses=1),
        },
        "scoring": {
            "pointsFor": 330,
            "pointsAgainst": 293,
            "averagePointDifferential": 2.47,
        },
        "cfp": {"appeared": False, "seed": None, "outcome": None},
        "draftFollowingSeason": {
            "year": 2025,
            "totalPicks": 13,
            "firstRoundPicks": 2,
        },
    }


def _payloads() -> dict[str, object]:
    return {
        "/coaches": [
            {
                "id": 24,
                "firstName": "Sherrone",
                "lastName": "Moore",
                "hireDate": "2024-01-26T12:00:00-05:00",
                "seasons": [_season_summary()],
            }
        ],
        "/coaches/profile": {
            "id": 24,
            "firstName": "Sherrone",
            "lastName": "Moore",
            "displayName": "Sherrone Moore",
            "currentTeam": {"id": 130, "school": "Michigan", "conference": "Big Ten"},
            "career": {
                **_record(games=15, wins=8, losses=7),
                "seasons": 1,
                "teams": 1,
                "firstYear": 2024,
                "lastYear": 2024,
            },
            "birthDate": "1986-02-03",
            "almaMater": {"id": 2305, "school": "Oklahoma"},
            "graduationYear": 2008,
            "wikidataId": "Q124000000",
            "hallOfFameYear": None,
        },
        "/coaches/seasons": [_detailed_season()],
        "/coaches/tenures": [
            {
                "id": 900,
                "coach": {"id": 24, "firstName": "Sherrone", "lastName": "Moore"},
                "team": {"id": 130, "school": "Michigan"},
                "hireDate": "2024-01-26",
                "startYear": 2024,
                "endYear": None,
                "effectiveStart": "2024-01-26T17:00:00Z",
                "effectiveEnd": None,
                "isInterim": False,
                "active": True,
                "seasons": 1,
                "record": _record(),
                "attributionComplete": True,
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_all_coaches_routes_preserve_public_dataframe_contract(
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
                    await client.coaches.list(
                        first_name="Sherrone", team="Michigan", year=2024
                    ),
                    Coach,
                ),
                (await client.coaches.profile(coach_id=24), CoachProfile),
                (
                    await client.coaches.seasons(coach_id=24, year=2024),
                    DetailedCoachSeason,
                ),
                (
                    await client.coaches.tenures(coach_id=24, year=2024, active=True),
                    CoachTenure,
                ),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    coaches = frames[0][0]
    seasons = frames[2][0]
    tenures = frames[3][0]
    if backend == "pandas":
        assert coaches.loc[0, "hire_date"].tzinfo is UTC
        assert seasons.loc[0, "team_metrics"]["year_over_year"]["wins"] == -7
        assert tenures.loc[0, "effective_start"].tzinfo is UTC
    else:
        assert coaches["hire_date"][0].utcoffset().total_seconds() == 0
        assert (
            seasons["team_metrics"]
            .struct.field("year_over_year")
            .struct.field("wins")[0]
            == -7
        )
        assert tenures["effective_start"][0].utcoffset().total_seconds() == 0

    assert observed["/coaches"]["firstName"] == "Sherrone"
    assert observed["/coaches/profile"] == {"coachId": "24"}
    assert observed["/coaches/tenures"]["active"] == "true"


def test_coaches_requests_reject_invalid_ids_and_ranges() -> None:
    with pytest.raises(ValidationError, match="min_year"):
        CoachesRequest(min_year=2025, max_year=2024)
    with pytest.raises(ValidationError):
        CoachSeasonsRequest(coach_id=0)


def test_coach_rejects_naive_hire_timestamp() -> None:
    payload = _payloads()["/coaches"]
    assert isinstance(payload, list)
    payload[0]["hireDate"] = "2024-01-26T12:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        Coach.model_validate(payload[0])
