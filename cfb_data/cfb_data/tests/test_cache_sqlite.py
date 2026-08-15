"""Test the real SQLite cache, catalog, coverage, and lease backend."""

import asyncio
import json
import sqlite3
import stat
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cfb_data._catalog.models import (
    AthleteFact,
    AthleteTeamSeasonFact,
    CatalogProjection,
    CoachFact,
    CoachTeamSeasonFact,
    ConferenceAffiliationFact,
    ConferenceFact,
    CoverageRecord,
    CoverageStatus,
    DriveFact,
    GameFact,
    PlayFact,
    PlayoffMatchupFact,
    RecruitFact,
    TeamFact,
    TeamSeasonFact,
    VenueFact,
    VocabularyFact,
)
from cfb_data._catalog.projection import CatalogSink, ObservationAuthority
from cfb_data.cache._models import ResponseRecord
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.cache.config import SQLiteCacheConfig
from cfb_data.errors import CFBDCacheBackendError
from cfb_data.tests._sqlite_test_sql import sqlite_test_sql


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
        team_seasons=(TeamSeasonFact(130, 2024, "Big Ten", 365),),
        conferences=(ConferenceFact(5, "Big Ten", "B1G", "fbs"),),
        affiliations=(ConferenceAffiliationFact(130, 5, 1896, None),),
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
        recruits=(RecruitFact("recruit-1", "4794102", "Zeke Berry", 2022),),
        coaches=(CoachFact(1, "Sherrone Moore"),),
        coach_team_seasons=(CoachTeamSeasonFact(1, 130, 2024, None, 1),),
        drives=(DriveFact("drive-1", 401628347, 130, "Michigan", 333, "Alabama"),),
        plays=(PlayFact("play-1", 401628347, "drive-1", 1, "Rush"),),
        vocabularies=(VocabularyFact("play_type", "1", "Rush", "RUSH"),),
        playoff_matchups=(PlayoffMatchupFact(1, 2024, 401628347),),
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


def _team_observation(
    observed_at: datetime, *, abbreviation: str | None, aliases: tuple[str, ...]
) -> CatalogProjection:
    """Return one authoritative team observation with sparse abbreviation nulls."""
    sink = CatalogSink(observed_at)
    observed = {"id", "school", "alternate_names"}
    if abbreviation is not None:
        observed.add("abbreviation")
    sink.add(
        TeamFact(130, "Michigan", abbreviation, aliases),
        authority=ObservationAuthority.authoritative,
        source="teams.Team",
        observed_fields=frozenset(observed),
    )
    return sink.projection()


def _recruit_observation(
    observed_at: datetime, *, athlete_id: str | None
) -> CatalogProjection:
    """Return an authoritative recruit observation including a nullable link."""
    sink = CatalogSink(observed_at)
    sink.add(
        RecruitFact("recruit-1", athlete_id, "Zeke Berry", 2022),
        authority=ObservationAuthority.authoritative,
        source="recruiting.Recruit",
        observed_fields=frozenset(("id", "athlete_id", "name", "year")),
    )
    return sink.projection()


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
    for team_query in ("Michigan", "MICH", "Wolverines"):
        assert [
            game.id
            for game in await backend.find_games(season=2024, week=1, team=team_query)
        ] == [401628347]
    athletes = await backend.find_athletes(
        name="zeke berry", team="Michigan", season=2024
    )
    assert [(athlete.id, athlete.team) for athlete in athletes] == [
        ("4794102", "Michigan")
    ]
    counts = await backend.catalog_counts()
    assert (counts.teams, counts.conferences, counts.venues, counts.games) == (
        2,
        1,
        1,
        1,
    )
    assert all(value > 0 for value in asdict(counts).values())

    await backend.close()
    reopened = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    assert [team.id for team in await reopened.find_teams("Wolverines")] == [130]
    assert await reopened.catalog_counts() == counts
    await reopened.close()


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
async def test_sqlite_authoritative_alias_removal_updates_lookup_index(
    tmp_path: Path,
) -> None:
    """Stop resolving an alias removed by a later authoritative team response."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    backend = await SQLiteCacheBackend(
        SQLiteCacheConfig(path=tmp_path / "cache.sqlite3")
    ).open()
    await backend.commit_response(
        _record(now),
        CatalogProjection(teams=(TeamFact(130, "Michigan", "MICH", ("Wolverines",)),)),
    )
    await backend.commit_response(
        _record(now + timedelta(minutes=1)),
        CatalogProjection(teams=(TeamFact(130, "Michigan", "MICH", ()),)),
    )

    assert await backend.find_teams("Wolverines") == []
    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_authoritative_null_clears_recruit_athlete_link(
    tmp_path: Path,
) -> None:
    """Persist an explicit authoritative null over an older recruit link."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    path = tmp_path / "cache.sqlite3"
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.commit_response(
        _record(now), _recruit_observation(now, athlete_id="4794102")
    )
    later = now + timedelta(minutes=1)
    await backend.commit_response(
        _record(later), _recruit_observation(later, athlete_id=None)
    )
    await backend.close()

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            sqlite_test_sql("select_recruit_athlete_id.sql")
        ).fetchone()

    assert row == (None,)


@pytest.mark.asyncio
async def test_sqlite_catalog_merge_is_ingestion_order_independent(
    tmp_path: Path,
) -> None:
    """Select canonical fields by evidence rather than commit order."""
    older = datetime(2026, 8, 13, tzinfo=UTC)
    newer = older + timedelta(minutes=1)
    states = (
        (
            _record(older),
            _team_observation(older, abbreviation="MICH", aliases=("Wolverines",)),
        ),
        (_record(newer), _team_observation(newer, abbreviation=None, aliases=())),
    )
    results = []
    for index, ordered in enumerate((states, tuple(reversed(states)))):
        backend = await SQLiteCacheBackend(
            SQLiteCacheConfig(path=tmp_path / f"order-{index}.sqlite3")
        ).open()
        for record, projection in ordered:
            await backend.commit_response(record, projection)
        results.append((await backend.find_teams(130))[0])
        await backend.close()

    assert results[0] == results[1]
    assert results[0].abbreviation == "MICH"
    assert results[0].alternate_names == ()


@pytest.mark.asyncio
async def test_sqlite_cancelled_commit_rolls_back_open_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow a later commit after cancellation interrupts an open transaction."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    backend = await SQLiteCacheBackend(
        SQLiteCacheConfig(path=tmp_path / "cache.sqlite3")
    ).open()
    original_commit_projection = backend._commit_projection
    projection_started = asyncio.Event()

    async def blocked_projection(*_: object) -> None:
        projection_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(backend, "_commit_projection", blocked_projection)
    interrupted = asyncio.create_task(
        backend.commit_response(_record(now), CatalogProjection())
    )
    await projection_started.wait()
    interrupted.cancel()
    with pytest.raises(asyncio.CancelledError):
        await interrupted

    monkeypatch.setattr(backend, "_commit_projection", original_commit_projection)
    await backend.commit_response(
        _record(now + timedelta(minutes=1)), CatalogProjection()
    )
    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_sparse_affiliation_preserves_known_end_year(
    tmp_path: Path,
) -> None:
    """Keep a known affiliation interval when a later fact cannot observe its end."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    path = tmp_path / "cache.sqlite3"
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.commit_response(
        _record(now),
        CatalogProjection(
            affiliations=(ConferenceAffiliationFact(130, 5, 1896, 1906),)
        ),
    )
    await backend.commit_response(
        _record(now + timedelta(minutes=1)),
        CatalogProjection(
            affiliations=(ConferenceAffiliationFact(130, 5, 1896, None),)
        ),
    )
    await backend.close()

    with sqlite3.connect(path) as connection:
        end_year = connection.execute(
            sqlite_test_sql("select_affiliation_end_year.sql")
        ).fetchone()
    assert end_year == (1906,)


@pytest.mark.asyncio
async def test_sqlite_season_facts_preserve_coach_tenure_ranges(
    tmp_path: Path,
) -> None:
    """Keep authoritative tenure intervals across per-season projections."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    path = tmp_path / "cache.sqlite3"
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.commit_response(
        _record(now),
        CatalogProjection(
            coach_team_seasons=(
                CoachTeamSeasonFact(1, 130, 2020, 2024, 44),
                CoachTeamSeasonFact(2, 333, 2022, None, 45),
            )
        ),
    )
    await backend.commit_response(
        _record(now + timedelta(minutes=1)),
        CatalogProjection(
            coach_team_seasons=(
                CoachTeamSeasonFact(1, 130, 2020, 2020),
                CoachTeamSeasonFact(2, 333, 2022, 2022),
            )
        ),
    )
    await backend.close()

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            sqlite_test_sql("select_coach_team_seasons.sql")
        ).fetchall()
    assert rows == [(1, 2024, 44), (2, None, 45)]


@pytest.mark.asyncio
async def test_sqlite_sparse_relationships_preserve_richer_fields(
    tmp_path: Path,
) -> None:
    """Keep optional relationship facts that a later source cannot observe."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    path = tmp_path / "cache.sqlite3"
    backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=path)).open()
    await backend.commit_response(
        _record(now),
        CatalogProjection(
            drives=(DriveFact("drive-1", 99, 130, "Michigan", 333, "Alabama"),),
            plays=(PlayFact("play-1", 99, "drive-1", 1, "Rush"),),
            vocabularies=(VocabularyFact("play_type", "1", "Rush", "RUSH"),),
            playoff_matchups=(PlayoffMatchupFact(10, 2024, 99),),
        ),
    )
    await backend.commit_response(
        _record(now + timedelta(minutes=1)),
        CatalogProjection(
            drives=(DriveFact("drive-1", 99, None, None, None, None),),
            plays=(PlayFact("play-1", 99, None, None, None),),
            vocabularies=(VocabularyFact("play_type", "1", "Rush", None),),
            playoff_matchups=(PlayoffMatchupFact(10, None, None),),
        ),
    )
    await backend.close()

    with sqlite3.connect(path) as connection:
        drive = connection.execute(sqlite_test_sql("select_drive.sql")).fetchone()
        play = connection.execute(sqlite_test_sql("select_play.sql")).fetchone()
        vocabulary = connection.execute(
            sqlite_test_sql("select_play_type_abbreviation.sql")
        ).fetchone()
        playoff = connection.execute(
            sqlite_test_sql("select_playoff_matchup.sql")
        ).fetchone()
    assert drive == (130, "Michigan", 333, "Alabama")
    assert play == ("drive-1", 1, "Rush")
    assert vocabulary == ("RUSH",)
    assert playoff == (2024, 99)


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
        connection.execute(sqlite_test_sql("set_incompatible_schema_version.sql"))

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
        connection.execute(sqlite_test_sql("corrupt_response_timestamp.sql"))

    with pytest.raises(CFBDCacheBackendError, match="corrupt"):
        await backend.get_response(record.key, now)
    assert await backend.get_response(record.key, now) is None

    await backend.close()
