"""Test typed identity resolution and minimal hydration through the client."""

import sqlite3
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aiohttp import web

from cfb_data import (
    CFBDCacheBackendError,
    CFBDClient,
    CFBDIdentityAmbiguityError,
    CFBDIdentityNotFoundError,
    CFBDServerError,
    Classification,
    FreshnessMode,
    RetryPolicy,
    SQLiteCacheConfig,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _venue() -> dict[str, object]:
    """Return one complete venue response row."""
    return {
        "id": 365,
        "name": "Michigan Stadium",
        "city": "Ann Arbor",
        "state": "MI",
        "zip": "48109",
        "countryCode": "US",
        "timezone": "America/Detroit",
        "latitude": 42.2658,
        "longitude": -83.7487,
        "elevation": "840",
        "capacity": 107601,
        "constructionYear": 1927,
        "grass": False,
        "dome": False,
    }


def _team(
    *, team_id: int = 130, school: str = "Michigan", alias: str = "Wolverines"
) -> dict[str, object]:
    """Return one complete team response row."""
    return {
        "id": team_id,
        "school": school,
        "mascot": alias,
        "abbreviation": "MICH" if team_id == 130 else "ALT",
        "alternateNames": [alias],
        "conference": "Big Ten",
        "division": None,
        "classification": "fbs",
        "color": "#00274C",
        "alternateColor": "#FFCB05",
        "logos": [],
        "twitter": None,
        "location": _venue(),
    }


def _conference() -> dict[str, object]:
    """Return one complete conference response row."""
    return {
        "id": 5,
        "name": "Big Ten Conference",
        "shortName": "Big Ten",
        "abbreviation": "B1G",
        "classification": "fbs",
        "memberCount": 18,
    }


def _affiliation() -> dict[str, object]:
    """Return one complete historical affiliation row."""
    return {
        "teamId": 130,
        "team": "Michigan",
        "conferenceId": 5,
        "conference": "Big Ten Conference",
        "conferenceAbbreviation": "B1G",
        "classification": "fbs",
        "conferenceDivision": None,
        "startYear": 1896,
        "endYear": None,
    }


def _roster_player() -> dict[str, object]:
    """Return one complete roster identity row."""
    return {
        "id": "4426385",
        "firstName": "Donovan",
        "lastName": "Edwards",
        "team": "Michigan",
        "height": 72.0,
        "weight": 210,
        "jersey": 7,
        "year": 4,
        "position": "RB",
        "homeCity": "West Bloomfield",
        "homeState": "MI",
        "homeCountry": "US",
        "homeLatitude": None,
        "homeLongitude": None,
        "homeCountyFIPS": None,
        "recruitIds": ["70001"],
    }


def _player_search() -> dict[str, object]:
    """Return one complete player-search identity row."""
    return {
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
        "teamStints": [{"team": "Michigan", "startYear": 2021, "endYear": 2024}],
    }


@pytest.mark.asyncio
async def test_identity_namespaces_resolve_without_dataframe_materialization(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    payloads: dict[str, object] = {
        "/teams": [_team()],
        "/conferences": [_conference()],
        "/venues": [_venue()],
        "/games": [game_response],
        "/roster": [_roster_player()],
    }

    async def handler(request: web.Request) -> web.Response:
        calls.append(request.path)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            team = await client.identities.teams.resolve("wolverines")
            assert await client.identities.teams.resolve_id("130") == 130
            assert await client.identities.teams.resolve_name(130) == "Michigan"
            conference = await client.identities.conferences.resolve("b1g")
            venue = await client.identities.venues.resolve("Michigan Stadium")
            game = await client.identities.games.resolve(game_id=401628347)
            athlete = await client.identities.athletes.resolve(
                name="Donovan Edwards", team="Michigan", season=2024
            )

    assert team.id == 130
    assert conference.id == 5
    assert venue.id == 365
    assert game.home_team_id == 333
    assert athlete.id == "4426385"
    assert calls == ["/teams", "/conferences", "/venues", "/games", "/roster"]


@pytest.mark.asyncio
async def test_game_identity_find_uses_exact_team_abbreviation_with_fresh_coverage(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Return SQLite game matches for every supported exact team identity."""
    calls: list[str] = []
    game = dict(game_response)
    game.update(
        {
            "homeId": 130,
            "homeTeam": "Michigan",
            "homeConference": "Big Ten",
        }
    )
    payloads: dict[str, object] = {"/teams": [_team()], "/games": [game]}

    async def handler(request: web.Request) -> web.Response:
        calls.append(request.path)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            await client.teams.list()
            await client.games.list(year=2024, team="MICH")
            matches = await client.identities.games.find(season=2024, team="MICH")

    assert [match.id for match in matches] == [401628347]
    assert calls == ["/teams", "/games"]


@pytest.mark.asyncio
async def test_identity_resolution_works_in_memory_without_persistence(
    api_server: ServerFactory,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([_player_search()])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            athlete = await client.identities.athletes.resolve(
                name="Donovan Edwards", team="Michigan"
            )

    assert athlete.id == "4426385"


@pytest.mark.asyncio
async def test_local_only_never_uses_network_and_requires_a_catalog(
    api_server: ServerFactory,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDCacheBackendError):
                await client.identities.teams.resolve(
                    "Michigan", freshness=FreshnessMode.local_only
                )

    assert calls == 0


@pytest.mark.asyncio
async def test_identity_resolution_never_guesses_ambiguous_or_missing_names(
    api_server: ServerFactory,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [
                _team(team_id=1, school="Alpha", alias="Shared"),
                _team(team_id=2, school="Beta", alias="Shared"),
            ]
        )

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDIdentityAmbiguityError, match="1:Alpha, 2:Beta"):
                await client.identities.teams.resolve("shared")
            with pytest.raises(CFBDIdentityNotFoundError):
                await client.identities.teams.resolve("absent")


@pytest.mark.asyncio
async def test_fresh_complete_coverage_proves_absence_without_another_call(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Do not spend quota rechecking a name absent from a complete partition."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            with pytest.raises(CFBDIdentityNotFoundError):
                await client.identities.teams.resolve("absent")
            with pytest.raises(CFBDIdentityNotFoundError):
                await client.identities.teams.resolve("still absent")

    assert calls == 1


@pytest.mark.asyncio
async def test_hydration_dry_run_resume_and_quota_call_formula(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, str]] = []
    payloads: dict[str, object] = {
        "/teams": [_team()],
        "/teams/fbs": [_team()],
        "/venues": [_venue()],
        "/conferences": [_conference()],
        "/conferences/affiliations": [_affiliation()],
        "/games": [game_response],
        "/roster": [_roster_player()],
        "/plays/types": [{"id": 1, "text": "Rush", "abbreviation": "RUSH"}],
        "/plays/stats/types": [{"id": 1, "name": "Yards"}],
        "/stats/categories": ["rushing"],
    }

    async def handler(request: web.Request) -> web.Response:
        calls.append(
            (
                request.path,
                request.query.get("year", ""),
                request.query.get("classification", ""),
            )
        )
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            dry_run = await client.identities.hydrate(
                seasons=[2023, 2024],
                classification=Classification.fbs,
                include_vocabularies=True,
                dry_run=True,
            )
            assert dry_run.planned_calls == 11
            assert dry_run.classification is Classification.fbs
            assert dry_run.endpoints[0] == "/teams/fbs"
            assert calls == []

            completed = await client.identities.hydrate(
                seasons=[2023, 2024],
                classification="fbs",
                include_vocabularies=True,
                max_concurrency=3,
            )
            assert completed.completed_calls == 11
            assert len(calls) == 11

            assert (await client.identities.teams.resolve("MICH")).id == 130
            assert (await client.identities.conferences.resolve("B1G")).id == 5
            assert (
                await client.identities.games.resolve(game_id=401628347)
            ).id == 401628347
            assert (
                await client.identities.athletes.resolve(
                    name="Donovan Edwards", team="Michigan", season=2024
                )
            ).id == "4426385"
            assert (
                await client.identities.athletes.resolve(
                    name="Donovan Edwards",
                    freshness=FreshnessMode.local_only,
                )
            ).id == "4426385"
            assert (
                await client.identities.athletes.resolve(
                    name="Donovan Edwards",
                    team="Michigan",
                    freshness=FreshnessMode.local_only,
                )
            ).id == "4426385"
            assert len(calls) == 11

            resumed = await client.identities.hydrate(
                seasons=[2023, 2024],
                classification=Classification.fbs,
                include_vocabularies=True,
                dry_run=True,
            )

    assert resumed.planned_calls == 0
    assert len([call for call in calls if call[0] == "/games"]) == 2
    assert len([call for call in calls if call[0] == "/roster"]) == 2
    assert all(
        call[2] == "fbs"
        for call in calls
        if call[0]
        in {
            "/conferences",
            "/conferences/affiliations",
            "/games",
            "/roster",
        }
    )


@pytest.mark.asyncio
async def test_hydration_rejects_invalid_scope_before_api_io(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Validate all planning inputs before consulting coverage or spending quota."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            with pytest.raises(ValueError, match="seasons"):
                await client.identities.hydrate(seasons=[2024, True], dry_run=True)
            with pytest.raises(ValueError, match="classification"):
                await client.identities.hydrate(
                    seasons=[2024], classification="naia", dry_run=True
                )
            with pytest.raises(ValueError, match="max_concurrency"):
                await client.identities.hydrate(
                    seasons=[2024], max_concurrency=False, dry_run=True
                )
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDCacheBackendError, match="catalog backend"):
                await client.identities.hydrate(seasons=[2024], dry_run=True)

    assert calls == 0


@pytest.mark.asyncio
async def test_ensure_fresh_can_fall_back_to_retained_catalog_identity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Use known facts for retryable API failure even without a response body."""
    status = 200
    path = tmp_path / "cache.sqlite3"

    async def handler(request: web.Request) -> web.Response:
        if status == 200:
            return web.json_response([_team()])
        return web.Response(status=status)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            original = await client.identities.teams.resolve("Michigan")

        with sqlite3.connect(path) as connection:
            connection.execute("DELETE FROM response_records")
            connection.execute(
                "UPDATE coverage SET fresh_until = ?",
                (datetime(2000, 1, 1, tzinfo=UTC).isoformat(),),
            )

        status = 503
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=path),
            retry_policy=RetryPolicy(max_attempts=1),
        ) as client:
            retained = await client.identities.teams.resolve("Michigan")

    assert retained == original


@pytest.mark.asyncio
async def test_failed_hydration_marks_no_false_coverage_and_resumes_minimally(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Retain completed partitions and retry only failed or unstarted calls."""
    fail_games = True
    calls: list[str] = []
    cache_path = tmp_path / "cache.sqlite3"
    payloads: dict[str, object] = {
        "/teams": [_team()],
        "/venues": [_venue()],
        "/conferences": [_conference()],
        "/conferences/affiliations": [_affiliation()],
        "/games": [game_response],
        "/roster": [_roster_player()],
    }

    async def handler(request: web.Request) -> web.Response:
        calls.append(request.path)
        if request.path == "/games" and fail_games:
            return web.Response(status=503)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=cache_path),
            retry_policy=RetryPolicy(max_attempts=1),
        ) as client:
            with pytest.raises(CFBDServerError):
                await client.identities.hydrate(seasons=[2024], max_concurrency=1)
            with sqlite3.connect(cache_path) as connection:
                failure_rows = connection.execute(
                    "SELECT endpoint, failure_category FROM coverage_failures "
                    "ORDER BY endpoint"
                ).fetchall()
            assert ("/games", "CFBDServerError") in failure_rows
            resume = await client.identities.hydrate(
                seasons=[2024], max_concurrency=1, dry_run=True
            )
            assert resume.endpoints == ("/games", "/roster")

            fail_games = False
            completed = await client.identities.hydrate(
                seasons=[2024], max_concurrency=1
            )
            with sqlite3.connect(cache_path) as connection:
                assert (
                    connection.execute(
                        "SELECT endpoint FROM coverage_failures"
                    ).fetchall()
                    == []
                )

    assert completed.completed_calls == 2
    assert calls == [
        "/teams",
        "/venues",
        "/conferences",
        "/conferences/affiliations",
        "/games",
        "/games",
        "/roster",
    ]
