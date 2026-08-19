"""Expose bounded redacted observability for analytics execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import Protocol


class AnalyticsEventType(StrEnum):
    """Identify one analytics lifecycle or durability transition."""

    run_planned = "run_planned"
    run_started = "run_started"
    run_completed = "run_completed"
    run_failed = "run_failed"
    run_cancelled = "run_cancelled"
    step_ready = "step_ready"
    step_started = "step_started"
    step_reused = "step_reused"
    step_completed = "step_completed"
    step_failed = "step_failed"
    step_cancelled = "step_cancelled"
    resource_wait = "resource_wait"
    checkpoint_lookup = "checkpoint_lookup"
    checkpoint_reused = "checkpoint_reused"
    checkpoint_written = "checkpoint_written"
    checkpoint_rejected = "checkpoint_rejected"
    checkpoint_corrupt = "checkpoint_corrupt"
    contract_validated = "contract_validated"
    quality_validated = "quality_validated"
    artifact_loaded = "artifact_loaded"
    artifact_committed = "artifact_committed"
    source_attempt_reserved = "source_attempt_reserved"


class AnalyticsOutcome(StrEnum):
    """Classify the safe outcome carried by one analytics event."""

    success = "success"
    error = "error"
    cancelled = "cancelled"
    reused = "reused"
    rejected = "rejected"
    corrupt = "corrupt"


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    """Report one redacted analytics transition."""

    event_type: AnalyticsEventType
    run_id: str
    node_id: str | None = None
    parent_run_id: str | None = None
    attempt_id: str | None = None
    outcome: AnalyticsOutcome | None = None
    placement: str | None = None
    artifact_digest: str | None = None
    row_count: int | None = None
    byte_count: int | None = None
    duration_seconds: float | None = None
    failure_category: str | None = None


class AnalyticsObserver(Protocol):
    """Consume analytics events synchronously without taking ownership."""

    def __call__(self, event: AnalyticsEvent) -> None:
        """Observe one immutable redacted event."""
        ...


@dataclass(frozen=True, slots=True)
class AnalyticsStatsSnapshot:
    """Expose one immutable bounded aggregate statistics view."""

    total_events: int
    dropped_events: int
    by_type: Mapping[AnalyticsEventType, int]
    by_outcome: Mapping[AnalyticsOutcome, int]


class AnalyticsStats:
    """Aggregate analytics events with bounded process-local counters."""

    def __init__(self, *, max_events: int = 100_000) -> None:
        """Initialize bounded thread-safe counters.

        :param max_events: Maximum events admitted into aggregate counters.
        :raises ValueError: If the event bound is not a positive integer.
        """
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or max_events < 1
        ):
            raise ValueError("max_events must be a positive integer")
        self._max_events = max_events
        self._total = 0
        self._dropped = 0
        self._by_type: dict[AnalyticsEventType, int] = {}
        self._by_outcome: dict[AnalyticsOutcome, int] = {}
        self._lock = Lock()

    def __call__(self, event: AnalyticsEvent) -> None:
        """Record one event without retaining row-level data."""
        with self._lock:
            if self._total >= self._max_events:
                self._dropped += 1
                return
            self._total += 1
            self._by_type[event.event_type] = self._by_type.get(event.event_type, 0) + 1
            if event.outcome is not None:
                self._by_outcome[event.outcome] = (
                    self._by_outcome.get(event.outcome, 0) + 1
                )

    def snapshot(self) -> AnalyticsStatsSnapshot:
        """Return an immutable point-in-time statistics snapshot."""
        with self._lock:
            return AnalyticsStatsSnapshot(
                total_events=self._total,
                dropped_events=self._dropped,
                by_type=MappingProxyType(dict(self._by_type)),
                by_outcome=MappingProxyType(dict(self._by_outcome)),
            )


__all__ = [
    "AnalyticsEvent",
    "AnalyticsEventType",
    "AnalyticsObserver",
    "AnalyticsOutcome",
    "AnalyticsStats",
    "AnalyticsStatsSnapshot",
]
