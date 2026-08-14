"""Test typed identity resolution and minimal hydration through the client."""

import sqlite3
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data._catalog.models import CatalogProjection
from cfb_data.cache._models import ResponseRecord
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.tests._sqlite_test_sql import sqlite_test_sql

from cfb_data import (
    CacheMode,
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
async def test_team_stats_enrich_local_game_team_relationships(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Find a cached game by a team carried only in nested team-stat rows."""
    payload = [
        {
            "id": 401628347,
            "teams": [
                {
                    "teamId": 130,
                    "team": "Michigan",
                    "conference": "Big Ten",
                    "homeAway": "home",
                    "points": 12,
                    "stats": [],
                },
                {
                    "teamId": 251,
                    "team": "Texas",
                    "conference": "SEC",
                    "homeAway": "away",
                    "points": 31,
                    "stats": [],
                },
            ],
        }
    ]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            await client.games.team_stats(year=2024, team="Michigan")
            matches = await client.identities.games.find(
                season=2024,
                team="Michigan",
                freshness=FreshnessMode.local_only,
            )

    assert [
        (match.id, match.home_team_id, match.away_team_id) for match in matches
    ] == [(401628347, 130, 251)]


@pytest.mark.asyncio
async def test_incomplete_game_does_not_claim_a_scheduled_status(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Leave status unknown when the games endpoint only proves incompleteness."""
    game = dict(game_response)
    game["completed"] = False

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            await client.games.list(year=2024)
            identity = await client.identities.games.resolve(
                game_id=401628347,
                freshness=FreshnessMode.local_only,
            )

    assert identity.status is None


@pytest.mark.asyncio
async def test_cacheless_game_identity_normalizes_unknown_relationships(
    api_server: ServerFactory,
    game_response: dict[str, object],
) -> None:
    """Apply compact game normalization without persistent catalog storage."""
    game = dict(game_response)
    game.update({"completed": False, "homeId": 0, "awayId": 0, "venueId": 0})

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            identity = await client.identities.games.resolve(game_id=401628347)

    assert (
        identity.status,
        identity.home_team_id,
        identity.away_team_id,
        identity.venue_id,
    ) == (None, None, None, None)


@pytest.mark.asyncio
async def test_zero_team_placeholder_is_not_persisted_as_an_identity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Exclude unresolved zero team IDs from the public identity catalog."""
    record = {"games": 0, "wins": 0, "losses": 0, "ties": 0}
    payload = {
        "year": 2024,
        "teamId": 0,
        "team": "Placeholder",
        "classification": "fbs",
        "conference": "Independent",
        "division": "",
        "expectedWins": None,
        "total": record,
        "conferenceGames": record,
        "homeGames": record,
        "awayGames": record,
        "neutralSiteGames": record,
        "regularSeason": record,
        "postseason": record,
    }

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([payload])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            await client.games.records(year=2024)
            with pytest.raises(CFBDIdentityNotFoundError):
                await client.identities.teams.resolve(
                    "Placeholder", freshness=FreshnessMode.local_only
                )


@pytest.mark.asyncio
async def test_ensure_fresh_fails_open_after_catalog_read_corruption(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Use a retained validated response when the catalog cannot answer."""
    path = tmp_path / "cache.sqlite3"
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            await client.teams.list()
            with sqlite3.connect(path) as connection:
                connection.execute(sqlite_test_sql("corrupt_team_aliases_json.sql"))

            identity = await client.identities.teams.resolve(130)

    assert identity.id == 130
    assert calls == 1


@pytest.mark.asyncio
async def test_ensure_fresh_does_not_accept_transient_coverage_after_read_failure(
    api_server: ServerFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh when durable coverage cannot confirm a transient catalog fact."""
    path = tmp_path / "cache.sqlite3"
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async def fail_coverage_read(backend: SQLiteCacheBackend, **kwargs: object) -> bool:
        del backend, kwargs
        raise RuntimeError("coverage read failed")

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            assert (await client.identities.teams.resolve("Michigan")).id == 130
            with sqlite3.connect(path) as connection:
                connection.execute(sqlite_test_sql("delete_responses.sql"))
            monkeypatch.setattr(
                SQLiteCacheBackend, "has_fresh_coverage", fail_coverage_read
            )

            refreshed = await client.identities.teams.resolve("Michigan")

    assert refreshed.id == 130
    assert calls == 2


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
async def test_local_only_uses_the_transient_catalog_without_network(
    api_server: ServerFactory,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDIdentityNotFoundError):
                await client.identities.teams.resolve(
                    "Michigan", freshness=FreshnessMode.local_only
                )
            assert calls == 0
            await client.teams.list()
            identity = await client.identities.teams.resolve(
                "Michigan", freshness=FreshnessMode.local_only
            )

    assert identity.id == 130
    assert calls == 1


@pytest.mark.asyncio
async def test_local_only_identity_reads_surface_durable_catalog_failures(
    api_server: ServerFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise one explicit cache error for every strict public identity read."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async def fail_catalog_read(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("catalog read failed")

    for method_name in (
        "find_teams",
        "find_conferences",
        "find_venues",
        "find_game",
        "find_games",
        "find_athletes",
    ):
        monkeypatch.setattr(SQLiteCacheBackend, method_name, fail_catalog_read)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            await client.teams.list()
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.teams.resolve(
                    "Michigan", freshness=FreshnessMode.local_only
                )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.conferences.resolve(
                    "Big Ten", freshness=FreshnessMode.local_only
                )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.venues.resolve(
                    "Michigan Stadium", freshness=FreshnessMode.local_only
                )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.games.resolve(
                    game_id=401628347, freshness=FreshnessMode.local_only
                )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.games.find(
                    season=2024, freshness=FreshnessMode.local_only
                )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.athletes.resolve(
                    name="Donovan Edwards", freshness=FreshnessMode.local_only
                )
            stale = await client.identities.teams.resolve(
                "Michigan", freshness=FreshnessMode.allow_stale
            )

    assert stale.id == 130
    assert calls == 1


@pytest.mark.asyncio
async def test_retained_response_reprojects_after_projection_contract_change(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Rebuild catalog facts locally when source-owned projection metadata changes."""
    calls = 0
    path = tmp_path / "cache.sqlite3"

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([_team()])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            await client.teams.list()

        with sqlite3.connect(path) as connection:
            connection.execute(sqlite_test_sql("delete_team_aliases.sql"))
            connection.execute(sqlite_test_sql("delete_teams.sql"))
            connection.execute(sqlite_test_sql("delete_team_observations.sql"))
            connection.execute(sqlite_test_sql("stale_team_projection_contract.sql"))

        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            with client.cache_mode(CacheMode.local_only):
                await client.teams.list()
            identity = await client.identities.teams.resolve(
                "Wolverines", freshness=FreshnessMode.local_only
            )

    assert identity.id == 130
    assert calls == 1


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
async def test_classified_coverage_must_contain_the_matched_team(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Refresh a partition capable of updating a stale matched identity."""
    path = tmp_path / "cache.sqlite3"
    broad_calls = 0

    def team(team_id: int, school: str, classification: str) -> dict[str, object]:
        payload = _team(team_id=team_id, school=school, alias="Mascot")
        payload["classification"] = classification
        payload["conference"] = "Ivy" if classification == "fcs" else "Big Ten"
        return payload

    async def handler(request: web.Request) -> web.Response:
        nonlocal broad_calls
        if request.path == "/teams/fbs":
            return web.json_response([team(130, "Michigan", "fbs")])
        assert request.path == "/teams"
        broad_calls += 1
        school = "Harvard" if broad_calls == 1 else "Harvard Crimson"
        return web.json_response([team(108, school, "fcs")])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=SQLiteCacheConfig(path=path)
        ) as client:
            await client.teams.list()
            past = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
            with sqlite3.connect(path) as connection:
                connection.execute(
                    sqlite_test_sql("stale_broad_team_coverage.sql"),
                    (past,),
                )
                connection.execute(
                    sqlite_test_sql("stale_team_response.sql"),
                    (past,),
                )
            await client.teams.fbs()

            identity = await client.identities.teams.resolve(108)

    assert identity.school == "Harvard Crimson"
    assert broad_calls == 2


@pytest.mark.asyncio
async def test_hydration_dry_run_resume_and_quota_call_formula(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

            async def fail_coverage_read(
                backend: SQLiteCacheBackend, **kwargs: object
            ) -> bool:
                del backend, kwargs
                raise RuntimeError("coverage read failed")

            monkeypatch.setattr(
                SQLiteCacheBackend, "has_fresh_coverage", fail_coverage_read
            )
            with pytest.raises(CFBDCacheBackendError, match="could not answer"):
                await client.identities.hydrate(
                    seasons=[2023, 2024],
                    classification=Classification.fbs,
                    include_vocabularies=True,
                    dry_run=True,
                )

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
            connection.execute(sqlite_test_sql("delete_responses.sql"))
            connection.execute(
                sqlite_test_sql("stale_all_coverage.sql"),
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
                    sqlite_test_sql("select_coverage_failures.sql")
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
                        sqlite_test_sql("select_coverage_failure_endpoints.sql")
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


@pytest.mark.asyncio
async def test_hydration_rejects_a_response_not_durably_committed(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never report hydration success from transient fail-open coverage alone."""
    payloads: dict[str, object] = {
        "/teams": [_team()],
        "/venues": [_venue()],
        "/conferences": [_conference()],
        "/conferences/affiliations": [_affiliation()],
        "/games": [game_response],
        "/roster": [_roster_player()],
    }

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payloads[request.path])

    async def discard_commit(
        backend: SQLiteCacheBackend,
        record: ResponseRecord,
        projection: CatalogProjection,
    ) -> None:
        del backend, record, projection

    monkeypatch.setattr(SQLiteCacheBackend, "commit_response", discard_commit)
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "cache.sqlite3"),
        ) as client:
            with pytest.raises(CFBDCacheBackendError, match="durably commit"):
                await client.identities.hydrate(seasons=[2024], max_concurrency=1)
