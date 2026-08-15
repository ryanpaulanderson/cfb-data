"""Exercise Redis caching against an explicitly configured real service."""

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from aiohttp import web
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
from cfb_data.cache._redis import RedisCacheBackend
from cfb_data.errors import CFBDCacheBackendError
from redis.asyncio import Redis

from cfb_data import CFBDClient, RedisCacheConfig

ServerFactory = Callable[[Callable[[web.Request], object]], object]


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


def _team_season_observation(
    observed_at: datetime,
    *,
    conference_name: str | None,
    venue_id: int | None,
) -> CatalogProjection:
    """Return one authoritative team-season relationship observation."""
    sink = CatalogSink(observed_at)
    sink.add(
        TeamSeasonFact(130, 2024, conference_name, venue_id),
        authority=ObservationAuthority.authoritative,
        source="teams.Team",
        observed_fields=frozenset(("team_id", "season", "conference_name", "venue_id")),
    )
    return sink.projection()


@pytest_asyncio.fixture
async def redis_config() -> AsyncIterator[RedisCacheConfig]:
    """Yield an isolated namespace and remove only its owned integration keys."""
    url = os.getenv("CFB_DATA_TEST_REDIS_URL")
    if not url:
        pytest.skip("set CFB_DATA_TEST_REDIS_URL for real Redis integration tests")
    config = RedisCacheConfig(url=url, key_prefix=f"cfb-data-test-{uuid.uuid4().hex}")
    try:
        yield config
    finally:
        client = Redis.from_url(config.url)
        owned_keys = [
            key async for key in client.scan_iter(match=f"{config.key_prefix}:v1:*")
        ]
        if owned_keys:
            await client.delete(*owned_keys)
        await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_retains_catalog_after_native_response_expiry(
    redis_config: RedisCacheConfig,
) -> None:
    config = redis_config
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="b" * 64,
        endpoint="/teams",
        response_contract="Team:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(milliseconds=100),
        retained_until=now + timedelta(seconds=1),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    projection = CatalogProjection(
        teams=(TeamFact(130, "Michigan", "MICH", ("Wolverines",)),),
        coverage=CoverageRecord(
            partition_key="/teams:",
            namespace="team",
            canonical_filters="",
            capabilities=("team.core_identity",),
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
    backend = await RedisCacheBackend(config).open()
    await backend.record_coverage_failure(
        endpoint="/teams",
        canonical_filters="",
        failure_category="CFBDTransportError",
        failed_at=now,
    )
    client = Redis.from_url(config.url)
    assert (
        len(
            [
                key
                async for key in client.scan_iter(
                    match=f"{config.key_prefix}:v1:coverage-failure:*"
                )
            ]
        )
        == 1
    )
    await backend.commit_response(record, projection)
    assert [
        key
        async for key in client.scan_iter(
            match=f"{config.key_prefix}:v1:coverage-failure:*"
        )
    ] == []

    assert [team.id for team in await backend.find_teams("wolverines")] == [130]
    counts = await backend.catalog_counts()
    assert counts.teams == 1
    await asyncio.sleep(1.1)
    assert await backend.get_response(record.key, datetime.now(UTC)) is None
    assert [team.id for team in await backend.find_teams(130)] == [130]

    await backend.close()
    reopened = await RedisCacheBackend(config).open()
    assert [team.id for team in await reopened.find_teams("Wolverines")] == [130]
    assert await reopened.catalog_counts() == counts
    await reopened.close()
    await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_counts_and_reopens_every_canonical_grain(
    redis_config: RedisCacheConfig,
) -> None:
    """Persist and inspect all fifteen explicit catalog grains."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="6" * 64,
        endpoint="/catalog-contract",
        response_contract="CatalogContract:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    projection = CatalogProjection(
        teams=(TeamFact(130, "Michigan", "MICH", ("Wolverines",)),),
        team_seasons=(TeamSeasonFact(130, 2024, "Big Ten", 365),),
        conferences=(ConferenceFact(5, "Big Ten", "B1G", "fbs"),),
        affiliations=(ConferenceAffiliationFact(130, 5, 1896, None),),
        venues=(VenueFact(365, "Michigan Stadium", "Ann Arbor", "MI"),),
        games=(GameFact(99, 2024, 1, "regular"),),
        athletes=(AthleteFact("42", "Test Athlete", "QB"),),
        athlete_team_seasons=(AthleteTeamSeasonFact("42", "Michigan", 2024),),
        recruits=(RecruitFact("recruit-1", "42", "Test Athlete", 2024),),
        coaches=(CoachFact(1, "Test Coach"),),
        coach_team_seasons=(CoachTeamSeasonFact(1, 130, 2024, None, 1),),
        drives=(DriveFact("drive-1", 99, 130, "Michigan", None, None),),
        plays=(PlayFact("play-1", 99, "drive-1", 1, "Rush"),),
        vocabularies=(VocabularyFact("play_type", "1", "Rush"),),
        playoff_matchups=(PlayoffMatchupFact(1, 2024, 99),),
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(record, projection)
    await backend.commit_response(record, projection)
    counts = await backend.catalog_counts()
    assert len(asdict(counts)) == 15
    assert all(value == 1 for value in asdict(counts).values())
    await backend.close()

    reopened = await RedisCacheBackend(redis_config).open()
    assert await reopened.catalog_counts() == counts
    await reopened.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_high_cardinality_athletes_use_bounded_hash_structures(
    redis_config: RedisCacheConfig,
) -> None:
    """Keep large rosters out of one-key-per-fact Redis layouts."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="5" * 64,
        endpoint="/roster",
        response_contract="RosterPlayer:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=2_000,
    )
    athletes = tuple(
        AthleteFact(str(index), f"Player {index}", "QB") for index in range(1, 2_001)
    )
    memberships = tuple(
        AthleteTeamSeasonFact(str(index), "Michigan", 2024) for index in range(1, 2_001)
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(
            athletes=athletes,
            athlete_team_seasons=memberships,
        ),
    )

    counts = await backend.catalog_counts()
    resolved = await backend.find_athletes(
        name="Player 2000", team="Michigan", season=2024
    )
    client = Redis.from_url(redis_config.url)
    catalog_keys = [
        key
        async for key in client.scan_iter(
            match=f"{redis_config.key_prefix}:v1:catalog:*"
        )
    ]

    assert (counts.athletes, counts.athlete_team_seasons) == (2_000, 2_000)
    assert [athlete.id for athlete in resolved] == ["2000"]
    assert len(catalog_keys) == 2

    await client.aclose()
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_partial_facts_preserve_richer_catalog_fields(
    redis_config: RedisCacheConfig,
) -> None:
    """Keep known aliases when a later source cannot observe them."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="e" * 64,
        endpoint="/teams",
        response_contract="Team:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(
            teams=(TeamFact(130, "Michigan", "MICH", ("Wolverines",)),),
            conferences=(ConferenceFact(5, "Big Ten", "B1G", "fbs"),),
            venues=(VenueFact(365, "Michigan Stadium", "Ann Arbor", "MI"),),
        ),
    )

    later = now + timedelta(seconds=1)
    await backend.commit_response(
        ResponseRecord(
            key=record.key,
            endpoint=record.endpoint,
            response_contract=record.response_contract,
            body=record.body,
            fetched_at=later,
            fresh_until=later + timedelta(seconds=10),
            retained_until=later + timedelta(seconds=30),
            etag=None,
            last_modified=None,
            row_count=0,
        ),
        CatalogProjection(
            teams=(TeamFact(130, "Michigan", None, None),),
            conferences=(ConferenceFact(5, "Big Ten", None, None),),
            venues=(VenueFact(365, "Michigan Stadium", None, None),),
        ),
    )

    team = (await backend.find_teams(130))[0]
    conference = (await backend.find_conferences(5))[0]
    venue = (await backend.find_venues(365))[0]
    assert await backend.find_teams("Wolverines") == [team]
    assert (team.abbreviation, team.alternate_names) == (
        "MICH",
        ("Wolverines",),
    )
    assert (conference.abbreviation, conference.classification) == ("B1G", "fbs")
    assert (venue.city, venue.state) == ("Ann Arbor", "MI")

    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_authoritative_alias_removal_updates_lookup_index(
    redis_config: RedisCacheConfig,
) -> None:
    """Stop resolving an alias removed by a later authoritative team response."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="9" * 64,
        endpoint="/teams",
        response_contract="Team:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(teams=(TeamFact(130, "Michigan", "MICH", ("Wolverines",)),)),
    )
    await backend.commit_response(
        record,
        CatalogProjection(teams=(TeamFact(130, "Michigan", "MICH", ()),)),
    )

    assert await backend.find_teams("Wolverines") == []
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_authoritative_null_clears_recruit_athlete_link(
    redis_config: RedisCacheConfig,
) -> None:
    """Persist an explicit authoritative null in the compact recruit layout."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="4" * 64,
        endpoint="/recruiting/players",
        response_contract="Recruit:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record, _recruit_observation(now, athlete_id="4794102")
    )
    later = now + timedelta(minutes=1)
    later_record = replace(
        record,
        fetched_at=later,
        fresh_until=later + timedelta(seconds=10),
        retained_until=later + timedelta(seconds=30),
    )
    await backend.commit_response(
        later_record, _recruit_observation(later, athlete_id=None)
    )
    await backend.close()

    client = Redis.from_url(redis_config.url)
    payloads = await client.hvals(f"{redis_config.key_prefix}:v1:catalog:recruit")
    await client.aclose()
    assert len(payloads) == 1
    payload: object = json.loads(payloads[0])
    assert isinstance(payload, dict)
    assert payload["athlete_id"] is None


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_authoritative_null_clears_team_season_relationships(
    redis_config: RedisCacheConfig,
) -> None:
    """Delete denormalized team-season fields after authoritative absence."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="7" * 64,
        endpoint="/teams",
        response_contract="Team:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        _team_season_observation(
            now,
            conference_name="Big Ten",
            venue_id=365,
        ),
    )
    await backend.commit_response(
        replace(record, fetched_at=now + timedelta(minutes=1)),
        _team_season_observation(
            now + timedelta(minutes=1),
            conference_name=None,
            venue_id=None,
        ),
    )
    client = Redis.from_url(redis_config.url)
    key = f"{redis_config.key_prefix}:v1:catalog:team-season:130:2024"
    stored = await client.hgetall(key)

    assert b"conference_name" not in stored
    assert b"venue_id" not in stored

    await client.aclose()
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_redis_catalog_merge_is_ingestion_order_independent(
    redis_config: RedisCacheConfig,
    reverse: bool,
) -> None:
    """Select canonical fields by evidence rather than commit order."""
    older = datetime.now(UTC)
    newer = older + timedelta(seconds=1)

    def record(observed_at: datetime) -> ResponseRecord:
        return ResponseRecord(
            key="7" * 64,
            endpoint="/teams",
            response_contract="Team:list:v1",
            body=b"[]",
            fetched_at=observed_at,
            fresh_until=observed_at + timedelta(seconds=10),
            retained_until=observed_at + timedelta(seconds=30),
            etag=None,
            last_modified=None,
            row_count=0,
        )

    states = (
        (
            record(older),
            _team_observation(older, abbreviation="MICH", aliases=("Wolverines",)),
        ),
        (record(newer), _team_observation(newer, abbreviation=None, aliases=())),
    )
    backend = await RedisCacheBackend(redis_config).open()
    for response, projection in reversed(states) if reverse else states:
        await backend.commit_response(response, projection)

    result = (await backend.find_teams(130))[0]
    assert result.abbreviation == "MICH"
    assert result.alternate_names == ()
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_renamed_identities_reject_stale_index_members(
    redis_config: RedisCacheConfig,
) -> None:
    """Reject old exact names after authoritative identity renames."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="8" * 64,
        endpoint="/catalog-test",
        response_contract="CatalogTest:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(
            conferences=(ConferenceFact(5, "Western Conference", "WEST", "fbs"),),
            venues=(VenueFact(365, "Old Stadium", "Ann Arbor", "MI"),),
            athletes=(AthleteFact("42", "Old Name", "QB"),),
        ),
    )
    await backend.commit_response(
        record,
        CatalogProjection(
            conferences=(ConferenceFact(5, "Eastern Conference", "EAST", "fbs"),),
            venues=(VenueFact(365, "New Stadium", "Ann Arbor", "MI"),),
            athletes=(AthleteFact("42", "New Name", "QB"),),
        ),
    )

    stale_matches = {
        "conference": await backend.find_conferences("Western Conference"),
        "venue": await backend.find_venues("Old Stadium"),
        "athlete": await backend.find_athletes(name="Old Name", team=None, season=None),
    }
    assert stale_matches == {"conference": [], "venue": [], "athlete": []}
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_sparse_affiliation_preserves_known_end_year(
    redis_config: RedisCacheConfig,
) -> None:
    """Keep a known affiliation interval when a later fact cannot observe its end."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="0" * 64,
        endpoint="/conferences/affiliations",
        response_contract="TeamConferenceAffiliation:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(
            affiliations=(ConferenceAffiliationFact(130, 5, 1896, 1906),)
        ),
    )
    await backend.commit_response(
        record,
        CatalogProjection(
            affiliations=(ConferenceAffiliationFact(130, 5, 1896, None),)
        ),
    )

    client = Redis.from_url(redis_config.url)
    raw = await client.get(
        f"{redis_config.key_prefix}:v1:catalog:affiliation:130:5:1896"
    )
    assert raw is not None
    assert json.loads(raw)["end_year"] == 1906

    await backend.close()
    await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_season_facts_preserve_coach_tenure_ranges(
    redis_config: RedisCacheConfig,
) -> None:
    """Keep authoritative tenure intervals across per-season projections."""
    now = datetime.now(UTC)
    record = ResponseRecord(
        key="f" * 64,
        endpoint="/coaches/tenures",
        response_contract="CoachTenure:list:v1",
        body=b"[]",
        fetched_at=now,
        fresh_until=now + timedelta(seconds=10),
        retained_until=now + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=0,
    )
    backend = await RedisCacheBackend(redis_config).open()
    await backend.commit_response(
        record,
        CatalogProjection(
            coach_team_seasons=(
                CoachTeamSeasonFact(1, 130, 2020, 2024, 44),
                CoachTeamSeasonFact(2, 333, 2022, None, 45),
            )
        ),
    )
    await backend.commit_response(
        record,
        CatalogProjection(
            coach_team_seasons=(
                CoachTeamSeasonFact(1, 130, 2020, 2020),
                CoachTeamSeasonFact(2, 333, 2022, 2022),
            )
        ),
    )

    client = Redis.from_url(redis_config.url, decode_responses=True)
    keys = sorted(
        [
            key
            async for key in client.scan_iter(
                match=f"{redis_config.key_prefix}:v1:catalog:coach-team-season:*"
            )
        ]
    )
    rows = [await client.hgetall(key) for key in keys]
    by_coach = {row["coach_id"]: row for row in rows}
    assert by_coach["1"]["end_year"] == "2024"
    assert by_coach["1"]["tenure_id"] == "44"
    assert "end_year" not in by_coach["2"]
    assert by_coach["2"]["tenure_id"] == "45"

    await client.aclose()
    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_cross_client_lease_coalesces_one_http_refresh(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    redis_config: RedisCacheConfig,
) -> None:
    config = redis_config
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with (
            CFBDClient("key", base_url=base_url, cache=config) as first,
            CFBDClient("key", base_url=base_url, cache=config) as second,
        ):
            results = await asyncio.gather(
                first.games.calendar(year=2024),
                second.games.calendar(year=2024),
            )

    assert calls == 1
    assert results[0].equals(results[1])


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_lease_scripts_require_the_current_owner(
    redis_config: RedisCacheConfig,
) -> None:
    backend = await RedisCacheBackend(redis_config).open()
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=2)

    assert await backend.acquire_lease("lease", "owner-a", expires, now)
    assert not await backend.acquire_lease("lease", "owner-b", expires, now)
    assert not await backend.renew_lease("lease", "owner-b", expires)
    assert not await backend.release_lease("lease", "owner-b")
    assert await backend.renew_lease("lease", "owner-a", expires)
    assert await backend.release_lease("lease", "owner-a")

    await backend.close()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_rejects_an_incompatible_catalog_schema(
    redis_config: RedisCacheConfig,
) -> None:
    """Fail explicitly rather than interpreting an unknown Redis namespace."""
    config = redis_config
    client = Redis.from_url(config.url)
    schema_key = f"{config.key_prefix}:v1:meta:schema-version"
    await client.set(schema_key, b"999")

    with pytest.raises(CFBDCacheBackendError, match="incompatible"):
        await RedisCacheBackend(config).open()

    await client.delete(schema_key)
    await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_catalog_fact_upserts_under_one_stable_versioned_key(
    redis_config: RedisCacheConfig,
) -> None:
    """Preserve first-seen provenance when a durable entity is observed again."""
    config = redis_config
    first_seen = datetime.now(UTC)
    record = ResponseRecord(
        key="c" * 64,
        endpoint="/coaches/profile",
        response_contract="CoachProfile:one:v1",
        body=b"{}",
        fetched_at=first_seen,
        fresh_until=first_seen + timedelta(seconds=10),
        retained_until=first_seen + timedelta(seconds=30),
        etag=None,
        last_modified=None,
        row_count=1,
    )
    backend = await RedisCacheBackend(config).open()
    await backend.commit_response(
        record, CatalogProjection(coaches=(CoachFact(1, "First Name"),))
    )
    later = first_seen + timedelta(seconds=1)
    await backend.commit_response(
        ResponseRecord(
            key=record.key,
            endpoint=record.endpoint,
            response_contract=record.response_contract,
            body=record.body,
            fetched_at=later,
            fresh_until=later + timedelta(seconds=10),
            retained_until=later + timedelta(seconds=30),
            etag=None,
            last_modified=None,
            row_count=1,
        ),
        CatalogProjection(coaches=(CoachFact(1, "Updated Name"),)),
    )

    client = Redis.from_url(config.url, decode_responses=True)
    keys = [
        key
        async for key in client.scan_iter(
            match=f"{config.key_prefix}:v1:catalog:coach:*"
        )
    ]
    assert len(keys) == 1
    fact = await client.hgetall(keys[0])
    assert fact["first_seen_at"] == first_seen.isoformat()
    assert fact["last_seen_at"] == later.isoformat()
    assert fact["name"] == "Updated Name"
    assert fact["source_version"] == "1"
    assert fact["schema_version"] == "1"

    await backend.close()
    owned_keys = [
        key async for key in client.scan_iter(match=f"{config.key_prefix}:v1:*")
    ]
    if owned_keys:
        await client.delete(*owned_keys)
    await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_evicts_a_corrupt_response_record(
    redis_config: RedisCacheConfig,
) -> None:
    """Remove an invalid versioned record so subsequent access is a clean miss."""
    config = redis_config
    backend = await RedisCacheBackend(config).open()
    client = Redis.from_url(config.url)
    digest = "d" * 64
    key = f"{config.key_prefix}:v1:response:{digest}"
    await client.set(key, b"not-json")

    with pytest.raises(CFBDCacheBackendError, match="corrupt"):
        await backend.get_response(digest, datetime.now(UTC))
    assert await backend.get_response(digest, datetime.now(UTC)) is None

    await backend.close()
    await client.aclose()
