"""Test reference-data endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.conferences import (
    Conference,
    TeamConferenceAffiliation,
    TeamConferenceChange,
)
from cfb_data.teams import Matchup, RosterPlayer, Team, TeamATS, TeamTalent
from cfb_data.venues import Venue

from cfb_data import (
    CFBDClient,
    CFBDRequestValidationError,
    CFBDResponseValidationError,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _venue() -> dict[str, object]:
    """Return one complete Venue response row."""
    return {
        "id": 365,
        "name": "Bryant-Denny Stadium",
        "city": "Tuscaloosa",
        "state": "AL",
        "zip": "35487",
        "countryCode": "US",
        "timezone": "America/Chicago",
        "latitude": 33.2083,
        "longitude": -87.5504,
        "elevation": "673",
        "capacity": 100077,
        "constructionYear": 1929,
        "grass": True,
        "dome": False,
    }


def _team() -> dict[str, object]:
    """Return one complete Team response row."""
    return {
        "id": 333,
        "school": "Alabama",
        "mascot": "Crimson Tide",
        "abbreviation": "ALA",
        "alternateNames": ["Bama"],
        "conference": "SEC",
        "division": "West",
        "classification": "fbs",
        "color": "#9E1B32",
        "alternateColor": "#FFFFFF",
        "logos": ["https://example.test/alabama.png"],
        "twitter": "@AlabamaFTBL",
        "location": _venue(),
    }


def _matchup() -> dict[str, object]:
    """Return one matchup summary with a nested game."""
    return {
        "team1": "Alabama",
        "team2": "Auburn",
        "endYear": 2024,
        "team1Wins": 1,
        "team2Wins": 0,
        "ties": 0,
        "games": [
            {
                "season": 2024,
                "week": 14,
                "seasonType": "regular",
                "date": "2024-11-30T14:30:00-06:00",
                "neutralSite": False,
                "venue": "Bryant-Denny Stadium",
                "homeTeam": "Alabama",
                "homeScore": 28,
                "awayTeam": "Auburn",
                "awayScore": 14,
                "winner": "Alabama",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_reference_data_routes_preserve_backend_contract(
    api_server: ServerFactory,
    backend: str,
) -> None:
    """Validate all routes, aliases, schemas, and nested values."""
    payloads: dict[str, object] = {
        "/venues": [_venue()],
        "/conferences": [
            {
                "id": 8,
                "name": "Southeastern Conference",
                "shortName": "SEC",
                "abbreviation": "SEC",
                "classification": "fbs",
                "memberCount": 16,
            }
        ],
        "/conferences/changes": [
            {
                "teamId": 150,
                "team": "Texas",
                "fromConferenceId": 4,
                "fromConference": "Big 12 Conference",
                "fromConferenceAbbreviation": "B12",
                "fromClassification": "fbs",
                "toConferenceId": 8,
                "toConference": "Southeastern Conference",
                "toConferenceAbbreviation": "SEC",
                "toClassification": "fbs",
                "effectiveYear": 2024,
            }
        ],
        "/conferences/affiliations": [
            {
                "teamId": 333,
                "team": "Alabama",
                "conferenceId": 8,
                "conference": "Southeastern Conference",
                "conferenceAbbreviation": "SEC",
                "classification": "fbs",
                "conferenceDivision": "West",
                "startYear": 1933,
                "endYear": None,
            }
        ],
        "/teams": [_team()],
        "/teams/fbs": [_team()],
        "/teams/matchup": _matchup(),
        "/teams/ats": [
            {
                "year": 2024,
                "teamId": 333,
                "team": "Alabama",
                "conference": "SEC",
                "games": 12,
                "atsWins": 7,
                "atsLosses": 5,
                "atsPushes": 0,
                "avgCoverMargin": 2.25,
            }
        ],
        "/roster": [
            {
                "id": "4433970",
                "firstName": "Jalen",
                "lastName": "Milroe",
                "team": "Alabama",
                "height": 74.0,
                "weight": 220,
                "jersey": 4,
                "year": 3,
                "position": "QB",
                "homeCity": "Katy",
                "homeState": "TX",
                "homeCountry": "USA",
                "homeLatitude": 29.7858,
                "homeLongitude": -95.8245,
                "homeCountyFIPS": "48201",
                "recruitIds": ["70001"],
            }
        ],
        "/talent": [{"year": 2024, "team": "Alabama", "talent": 1018.55}],
    }
    observed: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frames = [
                (await client.venues.list(), Venue),
                (
                    await client.conferences.list(year=2024, classification="fbs"),
                    Conference,
                ),
                (await client.conferences.changes(year=2024), TeamConferenceChange),
                (
                    await client.conferences.affiliations(
                        team="Alabama", min_year=2020, max_year=2024
                    ),
                    TeamConferenceAffiliation,
                ),
                (await client.teams.list(conference="SEC", year=2024), Team),
                (await client.teams.fbs(year=2024), Team),
                (
                    await client.teams.matchup(
                        team1="Alabama",
                        team2="Auburn",
                        min_year=2024,
                        max_year=2024,
                    ),
                    Matchup,
                ),
                (await client.teams.ats(year=2024, team="Alabama"), TeamATS),
                (
                    await client.teams.roster(
                        team="Alabama", year=2024, classification="fbs"
                    ),
                    RosterPlayer,
                ),
                (await client.teams.talent(year=2024), TeamTalent),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    teams_frame = frames[4][0]
    matchup_frame = frames[6][0]
    if backend == "pandas":
        assert str(teams_frame.dtypes["location"]) == "object"
        assert teams_frame.loc[0, "location"]["id"] == 365
        assert str(matchup_frame.dtypes["games"]) == "object"
        assert matchup_frame.loc[0, "games"][0]["winner"] == "Alabama"
    else:
        assert isinstance(teams_frame.schema["location"], pl.Struct)
        assert teams_frame["location"].struct.field("id")[0] == 365
        assert isinstance(matchup_frame.schema["games"], pl.List)
        assert matchup_frame["games"][0].to_list()[0]["winner"] == "Alabama"

    assert observed == {
        "/venues": {},
        "/conferences": {"year": "2024", "classification": "fbs"},
        "/conferences/changes": {"year": "2024"},
        "/conferences/affiliations": {
            "team": "Alabama",
            "minYear": "2020",
            "maxYear": "2024",
        },
        "/teams": {"conference": "SEC", "year": "2024"},
        "/teams/fbs": {"year": "2024"},
        "/teams/matchup": {
            "team1": "Alabama",
            "team2": "Auburn",
            "minYear": "2024",
            "maxYear": "2024",
        },
        "/teams/ats": {"year": "2024", "team": "Alabama"},
        "/roster": {"team": "Alabama", "year": "2024", "classification": "fbs"},
        "/talent": {"year": "2024"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_reference_data_empty_frames_keep_exact_schemas(
    api_server: ServerFactory,
    backend: str,
) -> None:
    """Return typed empty frames for representative shared/nested models."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            venues = await client.venues.list()
            teams = await client.teams.list()
            affiliations = await client.conferences.affiliations()

    assert list(venues.columns) == list(Venue.model_fields)
    assert list(teams.columns) == list(Team.model_fields)
    assert list(affiliations.columns) == list(TeamConferenceAffiliation.model_fields)
    assert len(venues) == len(teams) == len(affiliations) == 0


@pytest.mark.asyncio
async def test_reference_data_request_validation_stops_before_http(
    api_server: ServerFactory,
) -> None:
    """Reject invalid ranges and required filters before transport."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDRequestValidationError):
                await client.conferences.affiliations(year=2024, min_year=2020)
            with pytest.raises(CFBDRequestValidationError):
                await client.teams.matchup(
                    team1="Alabama", team2="Auburn", min_year=2025, max_year=2024
                )
            with pytest.raises(CFBDRequestValidationError):
                await client.teams.ats()
            with pytest.raises(CFBDRequestValidationError):
                await client.teams.talent(year=1800)

    assert calls == 0


@pytest.mark.asyncio
async def test_reference_data_response_validation_precedes_frame_conversion(
    api_server: ServerFactory,
) -> None:
    """Reject malformed nested Team data before constructing a frame."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([{"id": 333, "school": "Alabama"}])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError) as exc_info:
                await client.teams.list()

    assert exc_info.value.endpoint == "/teams"
    assert "Alabama" not in str(exc_info.value)
