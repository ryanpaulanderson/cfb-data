"""Test response caching through the installed public client behavior."""

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.cache._sqlite import SQLiteCacheBackend

from cfb_data import (
    CacheMode,
    CachePolicyConfig,
    CacheProfile,
    CacheTTL,
    CFBDAuthenticationError,
    CFBDCacheMissError,
    CFBDClient,
    CFBDClientStateError,
    RetryPolicy,
    SQLiteCacheConfig,
)

ServerFactory = Callable[[Callable[[web.Request], object]], object]


def _sqlite(path: Path) -> SQLiteCacheConfig:
    """Return a test-local SQLite backend configuration."""
    return SQLiteCacheConfig(path=path)


def _immediately_stale() -> CachePolicyConfig:
    """Return schedule policy that retains but never considers data fresh."""
    return CachePolicyConfig(
        {
            CacheProfile.schedule: CacheTTL(
                fresh_for=timedelta(0), retain_for=timedelta(days=1)
            )
        }
    )


@pytest.mark.asyncio
async def test_validated_exact_response_hit_avoids_http_and_preserves_lifecycle(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        client = CFBDClient(
            "account-a", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        )
        async with client:
            first = await client.games.calendar(year=2024)
            second = await client.games.calendar(year=2024)

        assert first.equals(second)
        assert calls == 1
        with pytest.raises(CFBDClientStateError):
            await client.games.calendar(year=2024)


@pytest.mark.asyncio
async def test_cache_isolated_by_credentials_and_query_scalar_types(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    path = tmp_path / "cache.sqlite3"
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "account-a", base_url=base_url, cache=_sqlite(path)
        ) as client:
            await client.games.calendar(year=2024)
        async with CFBDClient(
            "account-b", base_url=base_url, cache=_sqlite(path)
        ) as client:
            await client.games.calendar(year=2024)

    assert calls == 2


@pytest.mark.asyncio
async def test_invalid_response_is_never_cached(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return web.json_response([{"season": "private-invalid-value"}])
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        ) as client:
            with pytest.raises(Exception, match="Response validation failed"):
                await client.games.calendar(year=2024)
            result = await client.games.calendar(year=2024)

    assert len(result) == 1
    assert calls == 2


@pytest.mark.asyncio
async def test_process_local_single_flight_shields_leader_from_follower_cancellation(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls = 0
    release = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        await release.wait()
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        ) as client:
            first = asyncio.create_task(client.games.calendar(year=2024))
            second = asyncio.create_task(client.games.calendar(year=2024))
            await asyncio.sleep(0.05)
            second.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await second
            result = await first

    assert len(result) == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_conditional_refresh_extends_body_without_replacing_it(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    requests: list[str | None] = []

    async def handler(request: web.Request) -> web.Response:
        requests.append(request.headers.get("If-None-Match"))
        if len(requests) == 1:
            return web.json_response([calendar_response], headers={"ETag": '"v1"'})
        return web.Response(status=304, headers={"ETag": '"v1"'})

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            cache_policy=_immediately_stale(),
        ) as client:
            first = await client.games.calendar(year=2024)
            second = await client.games.calendar(year=2024)

    assert first.equals(second)
    assert requests == [None, '"v1"']


@pytest.mark.asyncio
async def test_stale_if_error_masks_only_retryable_failures(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    status = 200

    async def handler(request: web.Request) -> web.Response:
        if status == 200:
            return web.json_response([calendar_response])
        return web.Response(status=status)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            cache_policy=_immediately_stale(),
            retry_policy=RetryPolicy(max_attempts=1),
        ) as client:
            first = await client.games.calendar(year=2024)
            status = 503
            stale = await client.games.calendar(year=2024)
            assert first.equals(stale)
            status = 401
            with pytest.raises(CFBDAuthenticationError):
                await client.games.calendar(year=2024)


@pytest.mark.asyncio
async def test_explicit_cache_modes_refresh_bypass_and_local_only(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        ) as client:
            with client.cache_mode(CacheMode.local_only):
                with pytest.raises(CFBDCacheMissError):
                    await client.games.calendar(year=2024)
            await client.games.calendar(year=2024)
            with client.cache_mode("local_only"):
                await client.games.calendar(year=2024)
            with client.cache_mode("refresh"):
                await client.games.calendar(year=2024)
            with client.cache_mode("bypass"):
                await client.games.calendar(year=2024)

    assert calls == 3


@pytest.mark.asyncio
async def test_distributed_refresh_follower_waits_for_new_record(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Do not satisfy forced refresh from the retained pre-refresh record."""
    calls = 0
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            refresh_started.set()
            await release_refresh.wait()
        return web.json_response([calendar_response])

    path = tmp_path / "cache.sqlite3"
    async with api_server(handler) as base_url:
        async with (
            CFBDClient("key", base_url=base_url, cache=_sqlite(path)) as leader,
            CFBDClient("key", base_url=base_url, cache=_sqlite(path)) as follower,
        ):
            await leader.games.calendar(year=2024)
            with leader.cache_mode("refresh"):
                leader_task = asyncio.create_task(leader.games.calendar(year=2024))
            await refresh_started.wait()
            with follower.cache_mode("refresh"):
                follower_task = asyncio.create_task(follower.games.calendar(year=2024))
            await asyncio.sleep(0.1)
            follower_finished_early = follower_task.done()
            release_refresh.set()
            await asyncio.gather(leader_task, follower_task)

    assert not follower_finished_early
    assert calls == 2


@pytest.mark.asyncio
async def test_distributed_lease_timeout_fails_open_to_http(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Refresh directly when a distributed lease outlives the wait budget."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    path = tmp_path / "cache.sqlite3"
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            timeout_seconds=0.05,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=_sqlite(path),
            cache_policy=_immediately_stale(),
        ) as client:
            await client.games.calendar(year=2024)
            with sqlite3.connect(path) as connection:
                row = connection.execute("SELECT key FROM response_records").fetchone()
                assert row is not None
                connection.execute(
                    "INSERT INTO refresh_leases"
                    "(key, owner_token, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
                    (row[0], "other-worker", "2026-01-01", "9999-12-31"),
                )

            refreshed = await client.games.calendar(year=2024)

    assert len(refreshed) == 1
    assert calls == 2


@pytest.mark.asyncio
async def test_local_only_rejects_disabled_and_operational_caching(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Never spend quota when local-only intent cannot be honored."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response({})

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with client.cache_mode("local_only"):
                with pytest.raises(CFBDCacheMissError):
                    await client.games.calendar(year=2024)
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
        ) as client:
            with client.cache_mode("local_only"):
                with pytest.raises(CFBDCacheMissError):
                    await client.info.account()

    assert calls == 0


@pytest.mark.asyncio
async def test_corrupt_retained_record_is_evicted_and_refetched(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Treat persisted bytes as untrusted and recover through validated HTTP."""
    calls = 0
    path = tmp_path / "cache.sqlite3"

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url, cache=_sqlite(path)) as client:
            await client.games.calendar(year=2024)

        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE response_records SET body = ?", (b"not-json",))

        async with CFBDClient("key", base_url=base_url, cache=_sqlite(path)) as client:
            recovered = await client.games.calendar(year=2024)

    assert len(recovered) == 1
    assert calls == 2


@pytest.mark.asyncio
async def test_backend_open_failure_fails_open_without_logging_secrets(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep normal API calls available and emit only a bounded failure category."""
    token = "private-token-must-not-appear"

    async def unavailable(self: SQLiteCacheBackend) -> SQLiteCacheBackend:
        raise OSError("private backend detail")

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([calendar_response])

    monkeypatch.setattr(SQLiteCacheBackend, "open", unavailable)
    caplog.set_level(logging.WARNING)
    async with api_server(handler) as base_url:
        async with CFBDClient(
            token,
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
        ) as client:
            result = await client.games.calendar(year=2024)

    assert len(result) == 1
    assert "category=OSError" in caplog.text
    assert token not in caplog.text
    assert "private backend detail" not in caplog.text


@pytest.mark.asyncio
async def test_first_waiter_cancellation_does_not_cancel_shared_refresh(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep the internal leader alive when its first public waiter is cancelled."""
    calls = 0
    release = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        await release.wait()
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        ) as client:
            first = asyncio.create_task(client.games.calendar(year=2024))
            second = asyncio.create_task(client.games.calendar(year=2024))
            await asyncio.sleep(0.05)
            first.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            result = await second

    assert len(result) == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_last_waiter_cancellation_stops_refresh_and_releases_lease(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Cancel an unobserved refresh so a later request can become the leader."""
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(tmp_path / "cache.sqlite3")
        ) as client:
            abandoned = asyncio.create_task(client.games.calendar(year=2024))
            await started.wait()
            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError):
                await abandoned

            release.set()
            result = await client.games.calendar(year=2024)

    assert len(result) == 1
    assert calls == 2
