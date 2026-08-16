"""Test public retrieval observability through the installed client contract."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.observability import (
    CacheBackendFailed,
    CacheLookupCompleted,
    CacheLookupOutcome,
    CacheLookupPhase,
    HTTPAttemptFinished,
    HTTPAttemptOutcome,
    RefreshCoordinated,
    RefreshOutcome,
    RetrievalFinished,
    RetrievalSource,
)

from cfb_data import (
    CachePolicyConfig,
    CacheProfile,
    CacheTTL,
    CFBDClient,
    RetrievalEvent,
    RetrievalStats,
    RetryPolicy,
    SQLiteCacheConfig,
)

ServerFactory = Callable[[Callable[[web.Request], object]], object]


@dataclass(slots=True)
class _Recorder:
    """Retain test events while also exercising the public aggregate observer."""

    events: list[RetrievalEvent] = field(default_factory=list)
    stats: RetrievalStats = field(default_factory=RetrievalStats)

    def __call__(self, event: RetrievalEvent, /) -> None:
        self.events.append(event)
        self.stats(event)


def _sqlite(path: Path) -> SQLiteCacheConfig:
    """Return a fast isolated SQLite configuration for client tests."""
    return SQLiteCacheConfig(path=path, io_timeout_seconds=0.5)


@pytest.mark.asyncio
async def test_stats_report_exact_http_attempts_and_fresh_cache_hits(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Distinguish endpoint retrievals from actual transport attempts."""
    calls = 0
    recorder = _Recorder()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            observer=recorder,
        ) as client:
            first = await client.games.calendar(year=2024)
            second = await client.games.calendar(year=2024)

    assert first.equals(second)
    assert calls == 1
    snapshot = recorder.stats.snapshot()
    assert snapshot.endpoint_retrievals == 2
    assert snapshot.successful_retrievals == 2
    assert snapshot.http_attempts == 1
    assert snapshot.retries == 0
    assert snapshot.cache_misses == 1
    assert snapshot.fresh_cache_hits == 1
    assert snapshot.cache_writes == 1
    assert snapshot.network_free_successes == 1
    assert snapshot.rows_returned == 2
    assert snapshot.fresh_hit_rate == 0.5
    assert snapshot.cache_served_rate == 0.5
    assert snapshot.network_free_rate == 0.5
    assert snapshot.by_endpoint["/calendar"].http_attempts == 1
    assert snapshot.by_endpoint["/calendar"].cache_served_rate == 0.5

    finishes = [
        event for event in recorder.events if isinstance(event, RetrievalFinished)
    ]
    assert [event.source for event in finishes] == [
        RetrievalSource.network,
        RetrievalSource.fresh_cache,
    ]


@pytest.mark.asyncio
async def test_retry_events_number_every_attempt_and_terminal_outcome(
    api_server: ServerFactory,
) -> None:
    """Count every retry-loop attempt without parsing transport logs."""
    calls = 0
    recorder = _Recorder()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return web.Response(status=503)
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
            observer=recorder,
        ) as client:
            result = await client.games.calendar(year=2024)

    assert result.empty
    snapshot = recorder.stats.snapshot()
    assert snapshot.endpoint_retrievals == 1
    assert snapshot.http_attempts == 2
    assert snapshot.retries == 1
    attempts = [
        event for event in recorder.events if isinstance(event, HTTPAttemptFinished)
    ]
    assert [event.attempt_number for event in attempts] == [1, 2]
    assert [event.outcome for event in attempts] == [
        HTTPAttemptOutcome.retry,
        HTTPAttemptOutcome.success,
    ]
    assert [event.terminal for event in attempts] == [False, True]
    assert [event.status_class for event in attempts] == [5, 2]


@pytest.mark.asyncio
async def test_stale_fallback_is_separate_from_stale_lookup_and_http_attempt(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Report retained availability after an exhausted retryable response."""
    calls = 0
    recorder = _Recorder()
    policy = CachePolicyConfig(
        ttl_overrides={
            CacheProfile.schedule: CacheTTL(
                fresh_for=timedelta(0),
                retain_for=timedelta(days=1),
            )
        }
    )

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return web.json_response([calendar_response])
        return web.Response(status=503)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            cache_policy=policy,
            retry_policy=RetryPolicy(max_attempts=1),
            observer=recorder,
        ) as client:
            first = await client.games.calendar(year=2024)
            stale = await client.games.calendar(year=2024)

    assert first.equals(stale)
    snapshot = recorder.stats.snapshot()
    assert snapshot.endpoint_retrievals == 2
    assert snapshot.http_attempts == 2
    assert snapshot.stale_entries == 1
    assert snapshot.stale_fallbacks == 1
    assert snapshot.cache_served_retrievals == 1
    assert snapshot.cache_served_rate == 0.5


@pytest.mark.asyncio
async def test_single_flight_counts_two_retrievals_and_one_http_attempt(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Correlate followers without multiplying quota-relevant attempt counts."""
    calls = 0
    release = asyncio.Event()
    recorder = _Recorder()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        await release.wait()
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            observer=recorder,
        ) as client:
            first = asyncio.create_task(client.games.calendar(year=2024))
            second = asyncio.create_task(client.games.calendar(year=2024))
            await asyncio.sleep(0.05)
            release.set()
            results = await asyncio.gather(first, second)

    assert calls == 1
    assert results[0].equals(results[1])
    snapshot = recorder.stats.snapshot()
    assert snapshot.endpoint_retrievals == 2
    assert snapshot.http_attempts == 1
    assert snapshot.coalesced_retrievals == 1
    followers = [
        event
        for event in recorder.events
        if isinstance(event, RefreshCoordinated)
        and event.outcome is RefreshOutcome.local_follower
    ]
    assert len(followers) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "replacement", "expected"),
    [
        ("body", b'"private-cache-body"', CacheLookupOutcome.corrupt),
        (
            "response_contract",
            "private-incompatible-contract",
            CacheLookupOutcome.incompatible,
        ),
    ],
)
async def test_corrupt_and_incompatible_records_are_observable_and_refetched(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
    column: str,
    replacement: bytes | str,
    expected: CacheLookupOutcome,
) -> None:
    """Distinguish invalid retained records from ordinary cache misses."""
    calls = 0
    path = tmp_path / "cache.sqlite3"
    recorder = _Recorder()

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(path), observer=recorder
        ) as client:
            await client.games.calendar(year=2024)

        with sqlite3.connect(path) as connection:
            if column == "body":
                connection.execute(
                    "UPDATE response_records SET body = ?", (replacement,)
                )
            else:
                connection.execute(
                    "UPDATE response_records SET response_contract = ?",
                    (replacement,),
                )

        async with CFBDClient(
            "key", base_url=base_url, cache=_sqlite(path), observer=recorder
        ) as client:
            await client.games.calendar(year=2024)

    assert calls == 2
    initial_outcomes = [
        event.outcome
        for event in recorder.events
        if isinstance(event, CacheLookupCompleted)
        and event.phase is CacheLookupPhase.initial
    ]
    assert expected in initial_outcomes
    snapshot = recorder.stats.snapshot()
    if expected is CacheLookupOutcome.corrupt:
        assert snapshot.corrupt_entries == 1
    else:
        assert snapshot.incompatible_entries == 1
    serialized_events = repr([asdict(event) for event in recorder.events])
    assert "private-cache-body" not in serialized_events
    assert "private-incompatible-contract" not in serialized_events


@pytest.mark.asyncio
async def test_backend_failure_is_not_reported_as_a_miss_and_stays_redacted(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail open with a distinct bounded cache failure and exact HTTP count."""
    recorder = _Recorder()

    async def unavailable(self: SQLiteCacheBackend) -> SQLiteCacheBackend:
        raise OSError("private backend detail")

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([calendar_response])

    monkeypatch.setattr(SQLiteCacheBackend, "open", unavailable)
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "private-api-key",
            base_url=base_url,
            cache=_sqlite(tmp_path / "cache.sqlite3"),
            observer=recorder,
        ) as client:
            result = await client.games.calendar(year=987654321)

    assert len(result) == 1
    failures = [
        event for event in recorder.events if isinstance(event, CacheBackendFailed)
    ]
    assert len(failures) == 1
    assert failures[0].operation == "open"
    lookups = [
        event for event in recorder.events if isinstance(event, CacheLookupCompleted)
    ]
    assert lookups[0].outcome is CacheLookupOutcome.backend_error
    snapshot = recorder.stats.snapshot()
    assert snapshot.cache_backend_failures == 1
    assert snapshot.cache_misses == 0
    assert snapshot.http_attempts == 1
    serialized_events = repr([asdict(event) for event in recorder.events])
    assert "private-api-key" not in serialized_events
    assert "987654321" not in serialized_events
    assert "private backend detail" not in serialized_events


@pytest.mark.asyncio
async def test_observer_failure_is_isolated_logged_once_and_then_disabled(
    api_server: ServerFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep retrieval correctness independent from a failing observer."""
    observed = 0

    def failing_observer(event: RetrievalEvent) -> None:
        nonlocal observed
        observed += 1
        raise ValueError("private observer detail")

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    caplog.set_level(logging.WARNING, logger="cfb_data._observability")
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, observer=failing_observer
        ) as client:
            result = await client.games.calendar(year=2024)

    assert result.empty
    assert observed == 1
    assert caplog.text.count("observer disabled") == 1
    assert "category=ValueError" in caplog.text
    assert "private observer detail" not in caplog.text


@pytest.mark.asyncio
async def test_cancellation_finishes_attempt_and_retrieval_without_being_swallowed(
    api_server: ServerFactory,
) -> None:
    """Preserve cancellation while producing bounded terminal events."""
    started = asyncio.Event()
    release = asyncio.Event()
    recorder = _Recorder()

    async def handler(request: web.Request) -> web.Response:
        started.set()
        await release.wait()
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url, observer=recorder) as client:
            task = asyncio.create_task(client.games.calendar(year=2024))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()

    snapshot = recorder.stats.snapshot()
    assert snapshot.endpoint_retrievals == 1
    assert snapshot.cancelled_retrievals == 1
    assert snapshot.http_attempts == 1
    attempts = [
        event for event in recorder.events if isinstance(event, HTTPAttemptFinished)
    ]
    assert len(attempts) == 1
    assert attempts[0].outcome is HTTPAttemptOutcome.cancelled
