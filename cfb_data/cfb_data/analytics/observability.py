"""Expose bounded observability for dataset and workflow execution."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import Protocol

_LOGGER = logging.getLogger(__name__)


class AnalyticsOutcome(StrEnum):
    """Identify a terminal analytics operation state."""

    success = "success"
    error = "error"
    cancelled = "cancelled"


class RunPhase(StrEnum):
    """Identify one immutable run lifecycle transition."""

    planned = "planned"
    started = "started"
    finished = "finished"


class StepPhase(StrEnum):
    """Identify one step lifecycle transition."""

    ready = "ready"
    started = "started"
    reused = "reused"
    finished = "finished"


class ArtifactAction(StrEnum):
    """Identify one artifact-store action."""

    lookup = "lookup"
    loaded = "loaded"
    committed = "committed"
    rejected = "rejected"


@dataclass(frozen=True, slots=True)
class AnalyticsRunEvent:
    """Report a safe run lifecycle transition."""

    run_id: str
    definition_id: str
    phase: RunPhase
    outcome: AnalyticsOutcome | None
    step_count: int
    duration_seconds: float | None
    failure_category: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsStepEvent:
    """Report a safe step lifecycle transition."""

    run_id: str
    step_id: str
    operation_id: str
    phase: StepPhase
    outcome: AnalyticsOutcome | None
    row_count: int | None
    duration_seconds: float | None
    failure_category: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsArtifactEvent:
    """Report a safe artifact-store transition."""

    run_id: str
    step_id: str
    action: ArtifactAction
    kind: str
    row_count: int | None
    byte_count: int | None
    failure_category: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsValidationEvent:
    """Report one bounded table-contract validation outcome."""

    run_id: str
    step_id: str
    contract_id: str
    passed: bool
    row_count: int
    failed_checks: int


type AnalyticsEvent = (
    AnalyticsRunEvent
    | AnalyticsStepEvent
    | AnalyticsArtifactEvent
    | AnalyticsValidationEvent
)


class AnalyticsObserver(Protocol):
    """Receive one immutable analytics event synchronously."""

    def __call__(self, event: AnalyticsEvent, /) -> None:
        """Observe one event without mutating it."""


@dataclass(frozen=True, slots=True)
class AnalyticsStatsSnapshot:
    """Expose immutable bounded analytics counters."""

    runs: int
    successful_runs: int
    failed_runs: int
    cancelled_runs: int
    steps: int
    reused_steps: int
    failed_steps: int
    artifacts_committed: int
    artifacts_rejected: int
    rows_materialized: int
    bytes_committed: int
    by_definition: Mapping[str, int]


@dataclass(slots=True)
class AnalyticsStats:
    """Collect process-local bounded analytics counters."""

    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _runs: int = field(default=0, init=False)
    _successful_runs: int = field(default=0, init=False)
    _failed_runs: int = field(default=0, init=False)
    _cancelled_runs: int = field(default=0, init=False)
    _steps: int = field(default=0, init=False)
    _reused_steps: int = field(default=0, init=False)
    _failed_steps: int = field(default=0, init=False)
    _artifacts_committed: int = field(default=0, init=False)
    _artifacts_rejected: int = field(default=0, init=False)
    _rows_materialized: int = field(default=0, init=False)
    _bytes_committed: int = field(default=0, init=False)
    _by_definition: dict[str, int] = field(default_factory=dict, init=False)

    def __call__(self, event: AnalyticsEvent, /) -> None:
        """Update counters for one event.

        :param event: Immutable event emitted by an analytics runner.
        """
        with self._lock:
            if isinstance(event, AnalyticsRunEvent):
                if event.phase is RunPhase.started:
                    self._runs += 1
                    self._by_definition[event.definition_id] = (
                        self._by_definition.get(event.definition_id, 0) + 1
                    )
                elif event.phase is RunPhase.finished:
                    if event.outcome is AnalyticsOutcome.success:
                        self._successful_runs += 1
                    elif event.outcome is AnalyticsOutcome.cancelled:
                        self._cancelled_runs += 1
                    elif event.outcome is AnalyticsOutcome.error:
                        self._failed_runs += 1
            elif isinstance(event, AnalyticsStepEvent):
                if event.phase is StepPhase.started:
                    self._steps += 1
                elif event.phase is StepPhase.reused:
                    self._reused_steps += 1
                elif (
                    event.phase is StepPhase.finished
                    and event.outcome is AnalyticsOutcome.error
                ):
                    self._failed_steps += 1
            elif isinstance(event, AnalyticsArtifactEvent):
                if event.action is ArtifactAction.committed:
                    self._artifacts_committed += 1
                    self._rows_materialized += event.row_count or 0
                    self._bytes_committed += event.byte_count or 0
                elif event.action is ArtifactAction.rejected:
                    self._artifacts_rejected += 1

    def snapshot(self) -> AnalyticsStatsSnapshot:
        """Return an immutable snapshot of all observed counters."""
        with self._lock:
            return AnalyticsStatsSnapshot(
                runs=self._runs,
                successful_runs=self._successful_runs,
                failed_runs=self._failed_runs,
                cancelled_runs=self._cancelled_runs,
                steps=self._steps,
                reused_steps=self._reused_steps,
                failed_steps=self._failed_steps,
                artifacts_committed=self._artifacts_committed,
                artifacts_rejected=self._artifacts_rejected,
                rows_materialized=self._rows_materialized,
                bytes_committed=self._bytes_committed,
                by_definition=MappingProxyType(
                    dict(sorted(self._by_definition.items()))
                ),
            )


class _AnalyticsDispatcher:
    """Deliver ordered analytics events while isolating observer failures."""

    def __init__(
        self,
        observer: AnalyticsObserver | Callable[[object], None] | None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._observer = observer
        self._monotonic = monotonic

    @property
    def enabled(self) -> bool:
        """Return whether a healthy observer remains configured."""
        return self._observer is not None

    def now(self) -> float:
        """Return a monotonic timestamp."""
        return self._monotonic()

    def elapsed(self, started_at: float) -> float:
        """Return a finite non-negative duration."""
        return max(0.0, self._monotonic() - started_at)

    def emit(self, event: AnalyticsEvent) -> None:
        """Deliver one event or disable a failing observer."""
        observer = self._observer
        if observer is None:
            return
        try:
            observer(event)
        except (Exception, asyncio.CancelledError) as exc:
            self._observer = None
            _LOGGER.warning(
                "CFBD analytics observer disabled event=%s category=%s",
                type(event).__name__,
                type(exc).__name__,
            )


__all__ = [
    "AnalyticsArtifactEvent",
    "AnalyticsEvent",
    "AnalyticsObserver",
    "AnalyticsOutcome",
    "AnalyticsRunEvent",
    "AnalyticsStats",
    "AnalyticsStatsSnapshot",
    "AnalyticsStepEvent",
    "AnalyticsValidationEvent",
    "ArtifactAction",
    "RunPhase",
    "StepPhase",
]
