"""Validate the fail-closed cumulative live-call ledger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cfb_data.tests._live_budget import LiveCallLedger


def test_authorized_ceiling_preserves_session_and_operational_limits(
    tmp_path: Path,
) -> None:
    """Cap one session below both the requested spend and safety cushion."""
    ledger = LiveCallLedger(
        tmp_path / "ledger.json",
        initial_spent=651,
        absolute_limit=1000,
        investigation_limit=800,
    )

    assert (
        ledger.authorized_ceiling(
            maximum_new_attempts=90,
            safety_cushion=25,
        )
        == 741
    )

    constrained = LiveCallLedger(
        tmp_path / "constrained.json",
        initial_spent=760,
        absolute_limit=1000,
        investigation_limit=800,
    )
    assert (
        constrained.authorized_ceiling(
            maximum_new_attempts=90,
            safety_cushion=25,
        )
        == 775
    )


def test_session_ceiling_is_checked_under_the_ledger_lock(tmp_path: Path) -> None:
    """Permit no more concurrent reservations than one authorized session."""
    ledger = LiveCallLedger(
        tmp_path / "ledger.json",
        initial_spent=10,
        absolute_limit=1000,
        investigation_limit=800,
    )

    def reserve(index: int) -> bool:
        try:
            ledger.reserve("/games", authorized_ceiling=15)
        except RuntimeError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=10) as executor:
        outcomes = tuple(executor.map(reserve, range(10)))

    assert sum(outcomes) == 5
    assert ledger.snapshot().spent == 15


def test_corruption_and_invalid_budget_inputs_fail_closed(tmp_path: Path) -> None:
    """Reject malformed state and invalid ceilings without undercounting."""
    path = tmp_path / "ledger.json"
    path.write_text("not-json", encoding="utf-8")
    ledger = LiveCallLedger(path)

    with pytest.raises(RuntimeError, match="corrupt"):
        ledger.snapshot()
    with pytest.raises(RuntimeError, match="corrupt"):
        ledger.reserve("/games")
    with pytest.raises(ValueError, match="authorized_ceiling"):
        ledger.reserve("/games", authorized_ceiling=True)
    with pytest.raises(ValueError, match="maximum_new_attempts"):
        ledger.authorized_ceiling(maximum_new_attempts=0, safety_cushion=25)
    with pytest.raises(ValueError, match="safety_cushion"):
        ledger.authorized_ceiling(maximum_new_attempts=1, safety_cushion=-1)
