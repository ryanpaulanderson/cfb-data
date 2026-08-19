"""Dispatch analytics events without affecting coordinator correctness."""

from __future__ import annotations

import asyncio
import logging

from .observability import AnalyticsEvent, AnalyticsObserver

_LOGGER = logging.getLogger(__name__)


class _AnalyticsDispatcher:
    """Deliver ordered events and isolate a failing optional observer."""

    def __init__(self, observer: AnalyticsObserver | None) -> None:
        """Bind one run-scoped optional observer."""
        self._observer = observer

    @property
    def enabled(self) -> bool:
        """Return whether a healthy observer remains configured."""
        return self._observer is not None

    def emit(self, event: AnalyticsEvent) -> None:
        """Deliver one event or disable a failing observer safely."""
        observer = self._observer
        if observer is None:
            return
        try:
            observer(event)
        except (Exception, asyncio.CancelledError) as exc:
            self._observer = None
            _LOGGER.warning(
                "CFBD analytics observer disabled event=%s category=%s",
                event.event_type,
                type(exc).__name__,
            )
