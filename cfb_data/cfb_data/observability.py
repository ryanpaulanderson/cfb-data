"""Expose bounded retrieval, cache, and transport observability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import Protocol

from cfb_data.cache.config import CacheMode, CacheProfile


class RetrievalOutcome(StrEnum):
    """Identify the terminal state of one validated endpoint retrieval."""

    success = "success"
    error = "error"
    cancelled = "cancelled"


class RetrievalSource(StrEnum):
    """Identify how one retrieval obtained its validated response."""

    unknown = "unknown"
    network = "network"
    fresh_cache = "fresh_cache"
    revalidated_cache = "revalidated_cache"
    retained_cache = "retained_cache"
    stale_fallback = "stale_fallback"


class CacheLookupPhase(StrEnum):
    """Identify why the coordinator consulted the response cache."""

    initial = "initial"
    leader_recheck = "leader_recheck"
    lease_wait = "lease_wait"
    post_lease = "post_lease"


class CacheLookupOutcome(StrEnum):
    """Identify the safe result of one response-cache lookup."""

    skipped_disabled = "skipped_disabled"
    skipped_operational = "skipped_operational"
    skipped_bypass = "skipped_bypass"
    fresh_hit = "fresh_hit"
    miss = "miss"
    stale = "stale"
    incompatible = "incompatible"
    corrupt = "corrupt"
    backend_error = "backend_error"


class RefreshOutcome(StrEnum):
    """Identify one local or distributed refresh-coordination outcome."""

    local_leader = "local_leader"
    local_follower = "local_follower"
    lease_unavailable = "lease_unavailable"
    lease_acquired = "lease_acquired"
    lease_wait_started = "lease_wait_started"
    lease_wait_satisfied = "lease_wait_satisfied"
    lease_timeout = "lease_timeout"
    lease_released = "lease_released"


class HTTPAttemptOutcome(StrEnum):
    """Identify the terminal state of one client-side HTTP attempt."""

    success = "success"
    retry = "retry"
    http_error = "http_error"
    transport_error = "transport_error"
    response_error = "response_error"
    cancelled = "cancelled"


class CacheWriteOutcome(StrEnum):
    """Identify whether a validated response reached durable cache storage."""

    stored = "stored"
    revalidated = "revalidated"
    reprojected = "reprojected"
    skipped_policy = "skipped_policy"
    skipped_size = "skipped_size"
    backend_error = "backend_error"


@dataclass(frozen=True, slots=True)
class RetrievalStarted:
    """Report the start of one validated endpoint retrieval.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for this endpoint retrieval.
    :param endpoint: Fixed API endpoint path without a query string.
    :param parameter_names: Supplied query-field names without their values.
    :param cache_mode: Cache mode in effect when retrieval began.
    """

    client_id: str
    operation_id: str
    endpoint: str
    parameter_names: tuple[str, ...]
    cache_mode: CacheMode
    analytics_run_id: str | None = None
    analytics_step_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalFinished:
    """Report the terminal state of one validated endpoint retrieval.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for this endpoint retrieval.
    :param endpoint: Fixed API endpoint path without a query string.
    :param outcome: Terminal retrieval outcome.
    :param source: Source that supplied the validated response, when successful.
    :param row_count: Validated row count, or ``None`` when unavailable.
    :param duration_seconds: Non-negative elapsed retrieval duration.
    :param failure_category: Bounded exception class name, without its message.
    """

    client_id: str
    operation_id: str
    endpoint: str
    outcome: RetrievalOutcome
    source: RetrievalSource
    row_count: int | None
    duration_seconds: float
    failure_category: str | None
    analytics_run_id: str | None = None
    analytics_step_id: str | None = None


@dataclass(frozen=True, slots=True)
class CacheLookupCompleted:
    """Report one bounded response-cache lookup result.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the endpoint retrieval.
    :param endpoint: Fixed API endpoint path without a query string.
    :param profile: Cache freshness profile for the endpoint.
    :param phase: Coordinator phase that caused the lookup.
    :param outcome: Safe lookup result category.
    :param record_age_seconds: Non-negative record age when one was decoded.
    :param record_bytes: Stored body size when one was decoded.
    """

    client_id: str
    operation_id: str
    endpoint: str
    profile: CacheProfile
    phase: CacheLookupPhase
    outcome: CacheLookupOutcome
    record_age_seconds: float | None
    record_bytes: int | None


@dataclass(frozen=True, slots=True)
class RefreshCoordinated:
    """Report one local or distributed refresh-coordination transition.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the observing retrieval.
    :param refresh_id: Random identifier for the potentially shared refresh.
    :param endpoint: Fixed API endpoint path without a query string.
    :param outcome: Coordination transition that occurred.
    """

    client_id: str
    operation_id: str
    refresh_id: str
    endpoint: str
    outcome: RefreshOutcome


@dataclass(frozen=True, slots=True)
class HTTPAttemptStarted:
    """Report the start of one client-side HTTP transport attempt.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the initiating retrieval.
    :param refresh_id: Random identifier for the refresh performing the attempt.
    :param endpoint: Fixed API endpoint path without a query string.
    :param attempt_number: One-based attempt number within the retry loop.
    """

    client_id: str
    operation_id: str
    refresh_id: str
    endpoint: str
    attempt_number: int


@dataclass(frozen=True, slots=True)
class HTTPAttemptFinished:
    """Report the terminal state of one client-side HTTP transport attempt.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the initiating retrieval.
    :param refresh_id: Random identifier for the refresh performing the attempt.
    :param endpoint: Fixed API endpoint path without a query string.
    :param attempt_number: One-based attempt number within the retry loop.
    :param outcome: Attempt disposition, including whether it will be retried.
    :param terminal: Whether no later attempt is scheduled for this request.
    :param status_class: HTTP status divided by 100, when a response was received.
    :param duration_seconds: Non-negative elapsed attempt duration.
    :param response_bytes: Response body size read by this attempt.
    :param retry_delay_seconds: Scheduled delay before the next attempt.
    :param failure_category: Bounded exception class name, without its message.
    """

    client_id: str
    operation_id: str
    refresh_id: str
    endpoint: str
    attempt_number: int
    outcome: HTTPAttemptOutcome
    terminal: bool
    status_class: int | None
    duration_seconds: float
    response_bytes: int
    retry_delay_seconds: float | None
    failure_category: str | None


@dataclass(frozen=True, slots=True)
class StaleFallbackUsed:
    """Report that retained data masked an allowed exhausted failure.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the endpoint retrieval.
    :param refresh_id: Random identifier for the failed refresh.
    :param endpoint: Fixed API endpoint path without a query string.
    :param failure_category: Bounded exception class name, without its message.
    :param record_age_seconds: Non-negative age of the retained response.
    :param record_bytes: Stored response-body size.
    """

    client_id: str
    operation_id: str
    refresh_id: str
    endpoint: str
    failure_category: str
    record_age_seconds: float
    record_bytes: int


@dataclass(frozen=True, slots=True)
class CacheWriteCompleted:
    """Report the disposition of one validated response-cache write.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Random identifier for the endpoint retrieval.
    :param endpoint: Fixed API endpoint path without a query string.
    :param outcome: Write result or reason storage was skipped.
    :param row_count: Number of validated rows represented by the response.
    :param body_bytes: Serialized response-body size considered for storage.
    """

    client_id: str
    operation_id: str
    endpoint: str
    outcome: CacheWriteOutcome
    row_count: int
    body_bytes: int


@dataclass(frozen=True, slots=True)
class CacheBackendFailed:
    """Report a bounded cache-backend failure without retaining its exception.

    :param client_id: Random identifier shared by events from one client.
    :param operation_id: Retrieval identifier, or ``None`` for lifecycle work.
    :param endpoint: Fixed endpoint path, or ``None`` for lifecycle work.
    :param operation: Bounded backend operation name.
    :param failure_category: Bounded exception class name, without its message.
    """

    client_id: str
    operation_id: str | None
    endpoint: str | None
    operation: str
    failure_category: str


type RetrievalEvent = (
    RetrievalStarted
    | RetrievalFinished
    | CacheLookupCompleted
    | RefreshCoordinated
    | HTTPAttemptStarted
    | HTTPAttemptFinished
    | StaleFallbackUsed
    | CacheWriteCompleted
    | CacheBackendFailed
)


class RetrievalObserver(Protocol):
    """Receive immutable retrieval events synchronously and in emission order."""

    def __call__(self, event: RetrievalEvent, /) -> None:
        """Observe one bounded event without blocking or performing async I/O."""
        ...


@dataclass(frozen=True, slots=True)
class EndpointRetrievalStats:
    """Summarize bounded observed behavior for an aggregate or one endpoint.

    Count fields record the named events or terminal retrieval states. Byte,
    row, and duration fields are cumulative totals for the same observation
    interval. The retrieval-observability guide defines every counter.
    """

    endpoint_retrievals: int
    successful_retrievals: int
    failed_retrievals: int
    cancelled_retrievals: int
    http_attempts: int
    retries: int
    fresh_cache_hits: int
    retained_cache_serves: int
    stale_fallbacks: int
    cache_misses: int
    stale_entries: int
    incompatible_entries: int
    corrupt_entries: int
    cache_backend_failures: int
    cache_writes: int
    cache_write_failures: int
    coalesced_retrievals: int
    lease_waits: int
    lease_timeouts: int
    cache_served_retrievals: int
    network_free_successes: int
    response_bytes: int
    cache_bytes_written: int
    rows_returned: int
    total_retrieval_seconds: float
    total_http_seconds: float

    @property
    def fresh_hit_rate(self) -> float | None:
        """Return fresh hits divided by conclusive initial cache lookups.

        :return: Ratio from zero through one, or ``None`` without a lookup.
        """
        denominator = (
            self.fresh_cache_hits
            + self.cache_misses
            + self.stale_entries
            + self.incompatible_entries
            + self.corrupt_entries
        )
        if denominator == 0:
            return None
        return self.fresh_cache_hits / denominator

    @property
    def network_free_rate(self) -> float | None:
        """Return successful retrievals that initiated no HTTP attempt.

        :return: Ratio from zero through one, or ``None`` without a success.
        """
        if self.successful_retrievals == 0:
            return None
        return self.network_free_successes / self.successful_retrievals

    @property
    def cache_served_rate(self) -> float | None:
        """Return cache-served retrievals divided by successful retrievals.

        :return: Ratio from zero through one, or ``None`` without a success.
        """
        if self.successful_retrievals == 0:
            return None
        return self.cache_served_retrievals / self.successful_retrievals


@dataclass(frozen=True, slots=True)
class RetrievalStatsSnapshot(EndpointRetrievalStats):
    """Provide an immutable aggregate and endpoint-level statistics snapshot.

    Aggregate fields cover every observed event. ``by_endpoint`` maps each
    fixed endpoint path to the same bounded statistics for only that endpoint.
    """

    by_endpoint: Mapping[str, EndpointRetrievalStats]


@dataclass(slots=True)
class _MutableStats:
    """Accumulate one aggregate without retaining raw event payloads."""

    endpoint_retrievals: int = 0
    successful_retrievals: int = 0
    failed_retrievals: int = 0
    cancelled_retrievals: int = 0
    http_attempts: int = 0
    retries: int = 0
    fresh_cache_hits: int = 0
    retained_cache_serves: int = 0
    stale_fallbacks: int = 0
    cache_misses: int = 0
    stale_entries: int = 0
    incompatible_entries: int = 0
    corrupt_entries: int = 0
    cache_backend_failures: int = 0
    cache_writes: int = 0
    cache_write_failures: int = 0
    coalesced_retrievals: int = 0
    lease_waits: int = 0
    lease_timeouts: int = 0
    cache_served_retrievals: int = 0
    network_free_successes: int = 0
    response_bytes: int = 0
    cache_bytes_written: int = 0
    rows_returned: int = 0
    total_retrieval_seconds: float = 0.0
    total_http_seconds: float = 0.0

    def snapshot(self) -> EndpointRetrievalStats:
        """Return an immutable copy of these counters."""
        return EndpointRetrievalStats(
            endpoint_retrievals=self.endpoint_retrievals,
            successful_retrievals=self.successful_retrievals,
            failed_retrievals=self.failed_retrievals,
            cancelled_retrievals=self.cancelled_retrievals,
            http_attempts=self.http_attempts,
            retries=self.retries,
            fresh_cache_hits=self.fresh_cache_hits,
            retained_cache_serves=self.retained_cache_serves,
            stale_fallbacks=self.stale_fallbacks,
            cache_misses=self.cache_misses,
            stale_entries=self.stale_entries,
            incompatible_entries=self.incompatible_entries,
            corrupt_entries=self.corrupt_entries,
            cache_backend_failures=self.cache_backend_failures,
            cache_writes=self.cache_writes,
            cache_write_failures=self.cache_write_failures,
            coalesced_retrievals=self.coalesced_retrievals,
            lease_waits=self.lease_waits,
            lease_timeouts=self.lease_timeouts,
            cache_served_retrievals=self.cache_served_retrievals,
            network_free_successes=self.network_free_successes,
            response_bytes=self.response_bytes,
            cache_bytes_written=self.cache_bytes_written,
            rows_returned=self.rows_returned,
            total_retrieval_seconds=self.total_retrieval_seconds,
            total_http_seconds=self.total_http_seconds,
        )


@dataclass(slots=True)
class RetrievalStats:
    """Aggregate bounded cache and transport statistics from retrieval events.

    Pass an instance as ``CFBDClient(observer=...)`` and call :meth:`snapshot`
    during or after the client context. The collector stores counters and active
    operation identifiers only; it never retains response or cache payloads.
    """

    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _totals: _MutableStats = field(default_factory=_MutableStats, init=False)
    _by_endpoint: dict[str, _MutableStats] = field(default_factory=dict, init=False)
    _active_operations: set[str] = field(default_factory=set, init=False)
    _operations_with_http: set[str] = field(default_factory=set, init=False)

    def __call__(self, event: RetrievalEvent, /) -> None:
        """Update bounded counters for one immutable retrieval event.

        :param event: Event emitted by a configured client.
        """
        with self._lock:
            if isinstance(event, RetrievalStarted):
                self._active_operations.add(event.operation_id)
            elif (
                isinstance(event, HTTPAttemptStarted)
                and event.operation_id in self._active_operations
            ):
                self._operations_with_http.add(event.operation_id)
            had_http = (
                isinstance(event, RetrievalFinished)
                and event.operation_id in self._operations_with_http
            )
            endpoint = _event_endpoint(event)
            endpoint_stats = (
                self._by_endpoint.setdefault(endpoint, _MutableStats())
                if endpoint is not None
                else None
            )
            self._apply(self._totals, event, had_http=had_http)
            if endpoint_stats is not None:
                self._apply(endpoint_stats, event, had_http=had_http)
            if isinstance(event, RetrievalFinished):
                self._active_operations.discard(event.operation_id)
                self._operations_with_http.discard(event.operation_id)

    def snapshot(self) -> RetrievalStatsSnapshot:
        """Return an immutable aggregate and per-endpoint snapshot.

        :return: Counters observed before the snapshot lock was released.
        """
        with self._lock:
            total = self._totals.snapshot()
            by_endpoint = MappingProxyType(
                {
                    endpoint: counters.snapshot()
                    for endpoint, counters in sorted(self._by_endpoint.items())
                }
            )
        return RetrievalStatsSnapshot(
            **{
                name: getattr(total, name)
                for name in EndpointRetrievalStats.__dataclass_fields__
            },
            by_endpoint=by_endpoint,
        )

    def reset(self) -> None:
        """Clear all aggregate counters and active-operation state.

        Existing immutable snapshots remain unchanged.
        """
        with self._lock:
            self._totals = _MutableStats()
            self._by_endpoint.clear()
            self._active_operations.clear()
            self._operations_with_http.clear()

    def _apply(
        self,
        stats: _MutableStats,
        event: RetrievalEvent,
        *,
        had_http: bool,
    ) -> None:
        """Apply one event to one mutable aggregate while holding the lock."""
        if isinstance(event, RetrievalStarted):
            stats.endpoint_retrievals += 1
        elif isinstance(event, RetrievalFinished):
            stats.total_retrieval_seconds += event.duration_seconds
            if event.outcome is RetrievalOutcome.success:
                stats.successful_retrievals += 1
                if not had_http:
                    stats.network_free_successes += 1
                if event.row_count is not None:
                    stats.rows_returned += event.row_count
                if event.source in {
                    RetrievalSource.fresh_cache,
                    RetrievalSource.revalidated_cache,
                    RetrievalSource.retained_cache,
                    RetrievalSource.stale_fallback,
                }:
                    stats.cache_served_retrievals += 1
                if event.source is RetrievalSource.retained_cache:
                    stats.retained_cache_serves += 1
            elif event.outcome is RetrievalOutcome.error:
                stats.failed_retrievals += 1
            else:
                stats.cancelled_retrievals += 1
        elif isinstance(event, HTTPAttemptStarted):
            stats.http_attempts += 1
            if event.attempt_number > 1:
                stats.retries += 1
        elif isinstance(event, HTTPAttemptFinished):
            stats.total_http_seconds += event.duration_seconds
            stats.response_bytes += event.response_bytes
        elif isinstance(event, CacheLookupCompleted):
            if event.phase is not CacheLookupPhase.initial:
                return
            if event.outcome is CacheLookupOutcome.fresh_hit:
                stats.fresh_cache_hits += 1
            elif event.outcome is CacheLookupOutcome.miss:
                stats.cache_misses += 1
            elif event.outcome is CacheLookupOutcome.stale:
                stats.stale_entries += 1
            elif event.outcome is CacheLookupOutcome.incompatible:
                stats.incompatible_entries += 1
            elif event.outcome is CacheLookupOutcome.corrupt:
                stats.corrupt_entries += 1
        elif isinstance(event, CacheBackendFailed):
            stats.cache_backend_failures += 1
        elif isinstance(event, CacheWriteCompleted):
            if event.outcome in {
                CacheWriteOutcome.stored,
                CacheWriteOutcome.revalidated,
            }:
                stats.cache_writes += 1
                stats.cache_bytes_written += event.body_bytes
            elif event.outcome is CacheWriteOutcome.backend_error:
                stats.cache_write_failures += 1
        elif isinstance(event, StaleFallbackUsed):
            stats.stale_fallbacks += 1
        elif isinstance(event, RefreshCoordinated):
            if event.outcome is RefreshOutcome.local_follower:
                stats.coalesced_retrievals += 1
            elif event.outcome is RefreshOutcome.lease_wait_started:
                stats.lease_waits += 1
            elif event.outcome is RefreshOutcome.lease_timeout:
                stats.lease_timeouts += 1


def _event_endpoint(event: RetrievalEvent) -> str | None:
    """Return the fixed endpoint carried by an event, if applicable."""
    return event.endpoint


__all__ = [
    "CacheBackendFailed",
    "CacheLookupCompleted",
    "CacheLookupOutcome",
    "CacheLookupPhase",
    "CacheWriteCompleted",
    "CacheWriteOutcome",
    "EndpointRetrievalStats",
    "HTTPAttemptFinished",
    "HTTPAttemptOutcome",
    "HTTPAttemptStarted",
    "RefreshCoordinated",
    "RefreshOutcome",
    "RetrievalEvent",
    "RetrievalFinished",
    "RetrievalObserver",
    "RetrievalOutcome",
    "RetrievalSource",
    "RetrievalStarted",
    "RetrievalStats",
    "RetrievalStatsSnapshot",
    "StaleFallbackUsed",
]
