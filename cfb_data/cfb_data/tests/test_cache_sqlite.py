"""Test the real SQLite cache, catalog, coverage, and lease backend."""

import json
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cfb_data.cache._catalog import (
    AthleteFact,
    AthleteTeamSeasonFact,
    CatalogProjection,
    ConferenceFact,
    CoverageRecord,
    CoverageStatus,
    GameFact,
    TeamFact,
    VenueFact,
)
from cfb_data.cache._models import ResponseRecord
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.cache.config import SQLiteCacheConfig
from cfb_data.errors import CFBDCacheBackendError


def _record(now: datetime) -> ResponseRecord:
    """Return one retained validated response record."""
    return ResponseRecord(
        key="a" * 64,
        endpoint="/games",
        response_contract="Game:list:v1",
        body=json.dumps([{"id": 401628347}]).encode(),
        fetched_at=now,
        fresh_until=now + timedelta(days=1),
        retained_until=now + timedelta(days=30),
        etag='"games-v1"',
        last_modified=None,
        row_count=1,
    )


def _projection(now: datetime, record: ResponseRecord) -> CatalogProjection:
    """Return representative normalized facts for one atomic commit."""
    return CatalogProjection(
        teams=(
            TeamFact(130, "Michigan", "MICH", ("Wolverines",)),
            TeamFact(333, "Alabama", "ALA", ("Crimson Tide",)),
        ),
        conferences=(ConferenceFact(5, "Big Ten", "B1G", "fbs"),),
        venues=(VenueFact(365, "Michigan Stadium", "Ann Arbor", "MI"),),
        games=(
            GameFact(
                id=401628347,
                season=2024,
                week=1,
                season_type="regular",
                start_date=now,
                status="completed",
                home_team_id=130,
                away_team_id=333,
                venue_id=365,
            ),
        ),
        athletes=(AthleteFact("4794102", "Zeke Berry", "DB"),),
        athlete_team_seasons=(AthleteTeamSeasonFact("4794102", "Michigan", 2024),),
        coverage=CoverageRecord(
            partition_key="/games:year=2024",
            namespace="game",
            canonical_filters="year=2024",
            capabilities=("game.identity", "game.schedule"),
            status=CoverageStatus.complete,
            response_key=record.key,
            endpoint=record.endpoint,
            fetched_at=now,
            validated_at=now,
            fresh_until=record.fresh_until,
            retained_until=record.retained_until,
            row_count=1,
            known_cap=None,
        ),
    )


@pytest.mark.asyncio
async def test_sqlite_atomically_persists_response_catalog_and_coverage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private" / "cache.sqlite3"
    now = datetime(2026, 8, 13, tzinfo=UTC)
    record = _record(now)
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()

    await backend.commit_response(record, _projection(now, record))

    assert await backend.get_response(record.key, now) == record
    assert (path.stat().st_mode & 0o777) == stat.S_IRUSR | stat.S_IWUSR
    assert [team.school for team in await backend.find_teams(" michigan ")] == [
        "Michigan"
    ]
    assert [team.id for team in await backend.find_teams("wolverines")] == [130]
    assert [conference.id for conference in await backend.find_conferences("b1g")] == [
        5
    ]
    assert [venue.id for venue in await backend.find_venues("Michigan Stadium")] == [
        365
    ]
    assert (await backend.find_game(401628347)).home_team_id == 130  # type: ignore[union-attr]
    assert [
        game.id
        for game in await backend.find_games(season=2024, week=1, team="Michigan")
    ] == [401628347]
    athletes = await backend.find_athletes(
        name="zeke berry", team="Michigan", season=2024
    )
    assert [(athlete.id, athlete.team) for athlete in athletes] == [
        ("4794102", "Michigan")
    ]

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_partial_facts_preserve_richer_catalog_fields(
    tmp_path: Path,
) -> None:
    """Keep known optional facts when a later source cannot observe them."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    record = _record(now)
    backend = await SQLiteCacheBackend(
        SQLiteCacheConfig(path=tmp_path / "cache.sqlite3")
    ).open()
    await backend.commit_response(record, _projection(now, record))

    later = now + timedelta(minutes=1)
    await backend.commit_response(
        _record(later),
        CatalogProjection(
            teams=(TeamFact(130, "Michigan", None, None),),
            conferences=(ConferenceFact(5, "Big Ten", None, None),),
            venues=(VenueFact(365, "Michigan Stadium", None, None),),
        ),
    )

    assert await backend.find_teams(130) == await backend.find_teams("Wolverines")
    team = (await backend.find_teams(130))[0]
    conference = (await backend.find_conferences(5))[0]
    venue = (await backend.find_venues(365))[0]
    assert (team.abbreviation, team.alternate_names) == (
        "MICH",
        ("Wolverines",),
    )
    assert (conference.abbreviation, conference.classification) == ("B1G", "fbs")
    assert (venue.city, venue.state) == ("Ann Arbor", "MI")

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_response_expiry_never_deletes_catalog_facts(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    record = _record(now)
    backend = await SQLiteCacheBackend(
        SQLiteCacheConfig(path=tmp_path / "cache.sqlite3")
    ).open()
    await backend.commit_response(record, _projection(now, record))

    assert await backend.cleanup_responses(record.retained_until) == 1
    assert await backend.get_response(record.key, record.retained_until) is None
    assert [team.id for team in await backend.find_teams(130)] == [130]

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_lease_requires_owner_and_replaces_only_after_expiry(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    expires = now + timedelta(seconds=60)
    backend = await SQLiteCacheBackend(
        SQLiteCacheConfig(path=tmp_path / "cache.sqlite3")
    ).open()

    assert await backend.acquire_lease("key", "owner-a", expires, now)
    assert not await backend.acquire_lease("key", "owner-b", expires, now)
    assert not await backend.renew_lease("key", "owner-b", expires)
    assert not await backend.release_lease("key", "owner-b")
    assert await backend.acquire_lease(
        "key", "owner-b", expires + timedelta(seconds=60), expires
    )
    assert not await backend.release_lease("key", "owner-a")
    assert await backend.release_lease("key", "owner-b")

    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_rejects_an_incompatible_catalog_schema(tmp_path: Path) -> None:
    """Fail explicitly instead of interpreting an unknown persistence contract."""
    path = tmp_path / "cache.sqlite3"
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.close()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE cache_meta SET value = '999' WHERE key = 'schema_version'"
        )

    with pytest.raises(CFBDCacheBackendError, match="initialization failed"):
        await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()


@pytest.mark.asyncio
async def test_sqlite_evicts_corrupt_response_metadata(tmp_path: Path) -> None:
    """Remove malformed retained metadata instead of failing on every read."""
    path = tmp_path / "cache.sqlite3"
    now = datetime(2026, 8, 13, tzinfo=UTC)
    record = _record(now)
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.commit_response(record, _projection(now, record))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE response_records SET fresh_until = 'not-a-timestamp'"
        )

    with pytest.raises(CFBDCacheBackendError, match="corrupt"):
        await backend.get_response(record.key, now)
    assert await backend.get_response(record.key, now) is None

    await backend.close()
