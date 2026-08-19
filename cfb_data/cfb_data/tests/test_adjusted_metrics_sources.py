"""Test endpoint-owned Adjusted Metrics operations and public recipe sources."""

from __future__ import annotations

from typing import TypedDict

from cfb_data.adjusted_metrics.models.pydantic.responses import (
    AdjustedTeamMetrics,
    KickerPAAR,
    PlayerWeightedEPA,
)
from cfb_data.adjusted_metrics.sources import (
    adjusted_player_passing,
    adjusted_player_rushing,
    adjusted_team_metrics,
    kicker_paar_metrics,
)
from cfb_data.analytics import workflow
from cfb_data.analytics._compiler import _compile_recipe


class _AdjustedMetricSourceRefs(TypedDict):
    """Describe one reference to every public Adjusted Metrics source."""

    team: list[AdjustedTeamMetrics]
    passing: list[PlayerWeightedEPA]
    rushing: list[PlayerWeightedEPA]
    kicking: list[KickerPAAR]


@workflow(id="tests.source_faithful_adjusted_metrics", revision=1)
def _source_faithful_adjusted_metrics(year: int) -> _AdjustedMetricSourceRefs:
    """Build every Adjusted Metrics source through its public callable."""
    return {
        "team": adjusted_team_metrics(year=year),
        "passing": adjusted_player_passing(year=year),
        "rushing": adjusted_player_rushing(year=year),
        "kicking": kicker_paar_metrics(year=year),
    }


def test_adjusted_metric_sources_use_their_domain_operations() -> None:
    """Derive Adjusted Metrics identities and costs from endpoint contracts."""
    graph = _compile_recipe(_source_faithful_adjusted_metrics, (), {"year": 2024})

    source_nodes = [node for node in graph.nodes if node.kind == "source"]
    assert [node.declaration.recipe_id for node in source_nodes] == [
        "cfbd.adjusted_metrics.team_season",
        "cfbd.adjusted_metrics.player_passing",
        "cfbd.adjusted_metrics.player_rushing",
        "cfbd.adjusted_metrics.kicker_paar",
    ]
    assert all(node.declaration.operation is not None for node in source_nodes)
    assert all(node.declaration.source_cost == 1 for node in source_nodes)
