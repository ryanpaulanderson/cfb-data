"""Black-box tests for immutable automatic recipe discovery."""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType

import pytest
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeDiscoveryError,
    RecipeRef,
    RecipeSnapshot,
    dataset,
    discover_recipes,
)
from cfb_data.tests._analytics_fixtures import (
    DatasetRow as _DatasetRow,
)
from cfb_data.tests._analytics_fixtures import (
    game_summaries as _game_summaries,
)


def test_direct_imports_appear_in_an_immutable_snapshot() -> None:
    """Discover stable directly imported recipes without a registration call."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))

    assert isinstance(snapshot, RecipeSnapshot)
    assert snapshot.count >= 2
    assert len(snapshot.fingerprint) == 64
    with pytest.raises(AttributeError):
        snapshot.fingerprint = "changed"


def test_snapshot_identity_is_independent_of_repeated_discovery() -> None:
    """Deduplicate module-bound candidates and freeze deterministic identity."""
    config = AnalyticsConfig(discover_installed=False)
    first = discover_recipes(config)
    second = discover_recipes(config)

    assert first.count == second.count
    assert first.fingerprint == second.fingerprint


def test_concurrent_discovery_observes_complete_snapshots() -> None:
    """Serialize registration and snapshot creation under one process lock."""
    config = AnalyticsConfig(discover_installed=False)
    with ThreadPoolExecutor(max_workers=4) as executor:
        snapshots = tuple(executor.map(lambda _: discover_recipes(config), range(8)))

    assert len({snapshot.count for snapshot in snapshots}) == 1
    assert len({snapshot.fingerprint for snapshot in snapshots}) == 1


def test_core_import_and_disabled_discovery_do_not_load_official_provider() -> None:
    """Keep endpoint-only and explicitly disabled discovery provider-free."""
    script = """
import sys
import cfb_data
from cfb_data.analytics import AnalyticsConfig, discover_recipes
assert 'cfb_data_recipes' not in sys.modules
discover_recipes(AnalyticsConfig(discover_installed=False))
assert 'cfb_data_recipes' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_default_discovery_loads_official_provider_through_its_entry_point() -> None:
    """Load the official package only through ordinary trusted discovery."""
    script = """
import sys
from cfb_data.analytics import discover_recipes
assert 'cfb_data_recipes' not in sys.modules
discover_recipes()
assert 'cfb_data_recipes' in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_conflicting_exact_identities_fail_closed() -> None:
    """Refuse import-order conflict resolution for stable recipe identities."""
    module_name = "cfb_data_test_conflicting_provider"
    module = ModuleType(module_name)
    sys.modules[module_name] = module

    def first(year: int) -> RecipeRef[list[_DatasetRow]]:
        return _game_summaries(year=year)

    def second(year: int) -> RecipeRef[list[_DatasetRow]]:
        return _game_summaries(year=year, team="Penn State")

    first.__module__ = module_name
    second.__module__ = module_name
    first.__qualname__ = "first"
    second.__qualname__ = "second"
    module.first = dataset(
        id="tests.conflict",
        revision=1,
        row=_DatasetRow,
        grain="one game",
        keys=("game_id",),
    )(first)
    module.second = dataset(
        id="tests.conflict",
        revision=1,
        row=_DatasetRow,
        grain="one game",
        keys=("game_id",),
    )(second)
    try:
        with pytest.raises(CFBDRecipeDiscoveryError, match="Conflicting"):
            discover_recipes(AnalyticsConfig(discover_installed=False))
    finally:
        del sys.modules[module_name]
