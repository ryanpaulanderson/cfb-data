"""Provide a task-local hard HTTP-attempt budget for analytical runs."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from cfb_data.errors import CFBDAnalyticsError


@dataclass(slots=True)
class _AttemptBudget:
    """Reserve attempts atomically across concurrent source tasks."""

    limit: int
    used: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_CURRENT_BUDGET: ContextVar[_AttemptBudget | None] = ContextVar(
    "cfb_data_attempt_budget", default=None
)


@contextmanager
def _attempt_budget_scope(limit: int) -> Iterator[_AttemptBudget]:
    """Install one shared task-local budget for an analytics run."""
    existing = _CURRENT_BUDGET.get()
    if existing is not None:
        if limit > existing.limit:
            raise CFBDAnalyticsError(
                "A child analytics run cannot raise its parent's attempt budget"
            )
        yield existing
        return
    budget = _AttemptBudget(limit)
    token = _CURRENT_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _CURRENT_BUDGET.reset(token)


async def _reserve_http_attempt() -> None:
    """Reserve one actual transport attempt before it is dispatched."""
    budget = _CURRENT_BUDGET.get()
    if budget is None:
        return
    async with budget.lock:
        if budget.used >= budget.limit:
            raise CFBDAnalyticsError("Analytics HTTP-attempt budget is exhausted")
        budget.used += 1


__all__ = ["_attempt_budget_scope", "_AttemptBudget", "_reserve_http_attempt"]
