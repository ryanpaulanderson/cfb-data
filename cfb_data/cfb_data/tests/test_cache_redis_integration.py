"""Exercise Redis caching against an explicitly configured real service."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from aiohttp import web
from cfb_data.cache._catalog import (
    CatalogProjection,
    CoachFact,
    CoverageRecord,
    CoverageStatus,
    TeamFact,
)
from cfb_data.cache._models import ResponseRecord
from cfb_data.cache._redis import RedisCacheBackend
from cfb_data.errors import CFBDCacheBackendError
from redis.asyncio import Redis

from cfb_data import CFBDClient, RedisCacheConfig

ServerFactory = Callable[[Callable[[web.Request], object]], object]


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
    await asyncio.sleep(1.1)
    assert await backend.get_response(record.key, datetime.now(UTC)) is None
    assert [team.id for team in await backend.find_teams(130)] == [130]

    await backend.close()
    await client.aclose()


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
