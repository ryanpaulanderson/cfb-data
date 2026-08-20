"""Persistently reserve real-API attempts before transport dispatch."""

from __future__ import annotations

import fcntl
import json
import os
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

    def reserve(
        self,
        endpoint: str,
        *,
        authorized_ceiling: int | None = None,
    ) -> LiveBudgetSnapshot:
        """Permanently reserve one attempt before its HTTP dispatch.

        :param endpoint: Non-secret endpoint path used as audit evidence.
        :param authorized_ceiling: Optional cumulative ceiling for one live session.
        :return: Updated cumulative budget state.
        :raises ValueError: If the session ceiling is not a positive integer.
        :raises RuntimeError: If any applicable ceiling has been reached.
        """
        if authorized_ceiling is not None and (
            isinstance(authorized_ceiling, bool)
            or not isinstance(authorized_ceiling, int)
            or authorized_ceiling < 1
        ):
            raise ValueError("authorized_ceiling must be a positive integer")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            content = handle.read()
            spent = self._initial_spent if not content else _spent(content)
            if authorized_ceiling is not None and spent >= authorized_ceiling:
                raise RuntimeError("Live API authorized session ceiling reached")
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
            os.fsync(handle.fileno())
            _sync_directory(self._path.parent)
            return LiveBudgetSnapshot(
                spent=spent,
                absolute_limit=self._absolute_limit,
                investigation_limit=self._investigation_limit,
            )

    def authorized_ceiling(
        self,
        *,
        maximum_new_attempts: int,
        safety_cushion: int,
    ) -> int:
        """Return the cumulative ceiling for one bounded live session.

        :param maximum_new_attempts: Maximum additional reservations for the session.
        :param safety_cushion: Attempts preserved below the operational stop.
        :return: Cumulative reservation ceiling enforced by :meth:`reserve`.
        :raises ValueError: If either argument is outside its integer domain.
        :raises RuntimeError: If no attempt remains under every limit.
        """
        if (
            isinstance(maximum_new_attempts, bool)
            or not isinstance(maximum_new_attempts, int)
            or maximum_new_attempts < 1
        ):
            raise ValueError("maximum_new_attempts must be a positive integer")
        if (
            isinstance(safety_cushion, bool)
            or not isinstance(safety_cushion, int)
            or safety_cushion < 0
        ):
            raise ValueError("safety_cushion must be a non-negative integer")
        snapshot = self.snapshot()
        ceiling = min(
            snapshot.spent + maximum_new_attempts,
            snapshot.absolute_limit,
            snapshot.investigation_limit - safety_cushion,
        )
        if ceiling <= snapshot.spent:
            raise RuntimeError("No live API attempts remain under the safety limits")
        return ceiling

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
    try:
        payload: object = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Live API ledger is corrupt") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Live API ledger is corrupt")
    spent = payload.get("spent")
    if isinstance(spent, bool) or not isinstance(spent, int) or spent < 0:
        raise RuntimeError("Live API ledger spent value is corrupt")
    return spent


def _sync_directory(path: Path) -> None:
    """Flush a ledger directory entry after a durable reservation."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
