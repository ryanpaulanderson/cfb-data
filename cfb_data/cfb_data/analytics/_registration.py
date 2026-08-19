"""Collect decorated recipe candidates for immutable discovery snapshots."""

from __future__ import annotations

import weakref
from threading import RLock

_LOCK = RLock()
_CANDIDATES: list[weakref.ReferenceType[object]] = []


def _publish_candidate(recipe: object) -> None:
    """Record a decorated object without making it a mutable lookup catalog."""
    with _LOCK:
        _CANDIDATES.append(weakref.ref(recipe))


def _candidate_snapshot() -> tuple[object, ...]:
    """Return the currently live direct-import candidates."""
    with _LOCK:
        return tuple(
            candidate for ref in _CANDIDATES if (candidate := ref()) is not None
        )
