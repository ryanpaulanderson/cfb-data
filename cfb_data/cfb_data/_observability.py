"""Dispatch public observability events without affecting retrieval behavior."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from cfb_data.observability import (
    RetrievalEvent,
    RetrievalObserver,
    RetrievalSource,
)

_LOGGER = logging.getLogger(__name__)
_ANALYTICS_CORRELATION: ContextVar[tuple[str, str] | None] = ContextVar(
    "cfb_data_analytics_retrieval_correlation", default=None
)


@dataclass(slots=True)
class _OperationContext:
    """Carry safe correlation state across cache and transport boundaries."""

    client_id: str
    operation_id: str
    endpoint: str
    started_at: float
    source: RetrievalSource = RetrievalSource.unknown
    refresh_id: str | None = None
    analytics_run_id: str | None = None
    analytics_node_id: str | None = None


class _EventDispatcher:
    """Deliver ordered events and isolate failures in an optional observer."""

    def __init__(
        self,
        observer: RetrievalObserver | None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize one client-scoped dispatcher.

        :param observer: Optional synchronous event observer.
        :param monotonic: Monotonic clock used for bounded durations.
        """
        self._observer = observer
        self._monotonic = monotonic
        self._client_id = uuid.uuid4().hex

    @property
    def enabled(self) -> bool:
        """Return whether a healthy observer is currently configured."""
        return self._observer is not None

    @property
    def client_id(self) -> str:
        """Return this dispatcher's non-secret client correlation identifier."""
        return self._client_id

    def new_operation(self, endpoint: str) -> _OperationContext | None:
        """Return a new safe operation context when observation is enabled."""
        if self._observer is None:
            return None
        correlation = _ANALYTICS_CORRELATION.get()
        return _OperationContext(
            client_id=self._client_id,
            operation_id=uuid.uuid4().hex,
            endpoint=endpoint,
            started_at=self._monotonic(),
            analytics_run_id=(correlation[0] if correlation is not None else None),
            analytics_node_id=(correlation[1] if correlation is not None else None),
        )

    def new_refresh_id(self) -> str:
        """Return a non-secret identifier for one shared refresh."""
        return uuid.uuid4().hex

    def now(self) -> float:
        """Return the current monotonic clock value."""
        return self._monotonic()

    def elapsed(self, started_at: float) -> float:
        """Return a finite non-negative elapsed duration."""
        return max(0.0, self._monotonic() - started_at)

    def emit(self, event: RetrievalEvent) -> None:
        """Deliver one event or disable a failing observer without propagating."""
        observer = self._observer
        if observer is None:
            return
        try:
            observer(event)
        except (Exception, asyncio.CancelledError) as exc:
            self._observer = None
            _LOGGER.warning(
                "CFBD retrieval observer disabled event=%s category=%s",
                type(event).__name__,
                type(exc).__name__,
            )


def _failure_category(error: BaseException) -> str:
    """Return a bounded safe category without retaining an exception object."""
    category = getattr(error, "category", None)
    if isinstance(category, str) and category:
        return category[:64]
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return f"http_{status}"
    return type(error).__name__[:64]


@contextmanager
def _analytics_retrieval_context(run_id: str, node_id: str) -> Iterator[None]:
    """Correlate task-local endpoint retrieval events with one analytics node."""
    token = _ANALYTICS_CORRELATION.set((run_id, node_id))
    try:
        yield
    finally:
        _ANALYTICS_CORRELATION.reset(token)


__all__ = [
    "_EventDispatcher",
    "_OperationContext",
    "_analytics_retrieval_context",
    "_failure_category",
]
