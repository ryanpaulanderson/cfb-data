"""Persistently reserve real-API attempts before transport dispatch."""

from __future__ import annotations

import fcntl
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LiveBudgetSnapshot:
    """Report the cumulative authorized live-call spend."""

    spent: int
    absolute_limit: int
    investigation_limit: int


class LiveCallLedger:
    """Own a process-locked, never-refunded real-API attempt ledger."""

    def __init__(
        self,
        path: Path,
        *,
        initial_spent: int = 1,
        absolute_limit: int = 1000,
        investigation_limit: int = 800,
    ) -> None:
        self._path = path
        self._initial_spent = initial_spent
        self._absolute_limit = absolute_limit
        self._investigation_limit = investigation_limit

    def reserve(self, endpoint: str) -> LiveBudgetSnapshot:
        """Permanently reserve one attempt before its HTTP dispatch."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            content = handle.read()
            spent = self._initial_spent if not content else _spent(content)
            if spent >= self._investigation_limit:
                raise RuntimeError(
                    "Live API investigation limit reached; preserve the final "
                    "200-call safety reserve and ask for direction"
                )
            if spent >= self._absolute_limit:
                raise RuntimeError("Live API absolute 1,000-call ceiling reached")
            spent += 1
            payload = {
                "spent": spent,
                "absolute_limit": self._absolute_limit,
                "investigation_limit": self._investigation_limit,
                "last_endpoint": endpoint,
            }
            handle.seek(0)
            handle.truncate()
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            return LiveBudgetSnapshot(
                spent=spent,
                absolute_limit=self._absolute_limit,
                investigation_limit=self._investigation_limit,
            )

    def snapshot(self) -> LiveBudgetSnapshot:
        """Return the current ledger without reserving a call."""
        if not self._path.exists():
            return LiveBudgetSnapshot(
                self._initial_spent,
                self._absolute_limit,
                self._investigation_limit,
            )
        with self._path.open(encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            spent = _spent(handle.read())
        return LiveBudgetSnapshot(
            spent, self._absolute_limit, self._investigation_limit
        )


def _spent(content: str) -> int:
    """Read a validated non-negative spend from one ledger payload."""
    payload: object = json.loads(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Live API ledger is corrupt")
    spent = payload.get("spent")
    if isinstance(spent, bool) or not isinstance(spent, int) or spent < 0:
        raise RuntimeError("Live API ledger spent value is corrupt")
    return spent
