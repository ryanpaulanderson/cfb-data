"""Keep exhaustive live coverage aligned with the public resource surface."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
from cfb_data.tests._live_manifest import LIVE_ENDPOINT_CASES
from cfb_data.tests.test_live_api_all import _filters, _Seeds, _update_seeds

_PACKAGE_ROOT = Path(__file__).parents[1]


def test_live_manifest_contains_each_public_rest_route_once() -> None:
    """Fail when a resource route is missing from or duplicated in the manifest."""
    implemented: set[str] = set()
    for pattern in ("*/resource.py", "*/_operations.py"):
        for path in _PACKAGE_ROOT.glob(pattern):
            tree = ast.parse(path.read_text())
            implemented.update(
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("/")
            )
    manifested = [case.endpoint for case in LIVE_ENDPOINT_CASES]
    assert len(manifested) == 74
    assert len(manifested) == len(set(manifested))
    assert set(manifested) == implemented


def test_season_overview_uses_an_id_discovered_by_player_search() -> None:
    """Keep the scalar overview case tied to a validated live search result."""
    seeds = _Seeds()
    assert "player_id" not in _filters("/player/season/overview", seeds)

    _update_seeds(
        "/player/search",
        pd.DataFrame(
            [
                {
                    "id": 4431611,
                    "name": seeds.overview_athlete_name,
                }
            ]
        ),
        seeds,
    )

    assert _filters("/player/season/overview", seeds) == {
        "year": 2023,
        "player_id": 4431611,
    }
