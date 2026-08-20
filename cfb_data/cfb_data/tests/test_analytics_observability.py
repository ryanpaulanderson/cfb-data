"""Tests for bounded analytics events and retrieval correlation."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from aiohttp import web
from cfb_data._observability import _analytics_retrieval_context
from cfb_data.analytics import (
    AnalyticsEvent,
    AnalyticsEventType,
    AnalyticsOutcome,
    AnalyticsStats,
)
from cfb_data.analytics._observability import _AnalyticsDispatcher
from cfb_data.observability import RetrievalEvent, RetrievalFinished, RetrievalStarted

from cfb_data import CFBDClient, RetryPolicy

ServerFactory = Callable[[Callable[[web.Request], object]], object]


def test_analytics_stats_are_bounded_thread_safe_aggregates() -> None:
    """Count safe event categories without retaining unbounded event payloads."""
    stats = AnalyticsStats(max_events=2)
    events = (
        AnalyticsEvent(AnalyticsEventType.run_started, "run-1"),
        AnalyticsEvent(
            AnalyticsEventType.step_completed,
            "run-1",
            node_id="node-1",
            outcome=AnalyticsOutcome.success,
            row_count=3,
        ),
        AnalyticsEvent(AnalyticsEventType.run_completed, "run-1"),
    )
    for event in events:
        stats(event)

    snapshot = stats.snapshot()
    assert snapshot.total_events == 2
    assert snapshot.dropped_events == 1
    assert snapshot.by_type[AnalyticsEventType.step_completed] == 1
    assert snapshot.by_outcome[AnalyticsOutcome.success] == 1


def test_failing_analytics_observer_is_disabled_without_propagation() -> None:
    """Keep telemetry failures outside analytical correctness."""
    calls = 0

    def observer(event: AnalyticsEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("private observer failure")

    dispatcher = _AnalyticsDispatcher(observer)
    dispatcher.emit(AnalyticsEvent(AnalyticsEventType.run_started, "run-1"))
    dispatcher.emit(AnalyticsEvent(AnalyticsEventType.run_completed, "run-1"))

    assert calls == 1
    assert not dispatcher.enabled


def test_analytics_event_contract_has_no_raw_data_or_path_fields() -> None:
    """Keep event fields bounded to safe identifiers and aggregate evidence."""
    field_names = set(AnalyticsEvent.__dataclass_fields__)

    assert {
        "parameters",
        "rows",
        "frame",
        "path",
        "exception",
        "message",
        "credential",
        "response_body",
    }.isdisjoint(field_names)


@pytest.mark.asyncio
async def test_retrieval_events_inherit_task_local_analytics_correlation(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
) -> None:
    """Correlate source retrieval boundaries without leaking selectors."""
    events: list[RetrievalEvent] = []

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "correlation-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            observer=events.append,
        ) as client:
            with _analytics_retrieval_context("run-safe", "node-safe"):
                await client.games.calendar(year=2024)

    boundaries = [
        event
        for event in events
        if isinstance(event, (RetrievalStarted, RetrievalFinished))
    ]
    assert len(boundaries) == 2
    assert all(event.analytics_run_id == "run-safe" for event in boundaries)
    assert all(event.analytics_node_id == "node-safe" for event in boundaries)
    assert "correlation-key" not in repr(boundaries)
