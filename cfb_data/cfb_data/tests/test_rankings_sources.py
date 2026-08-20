"""Test endpoint-owned Rankings operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.rankings.models.pydantic.responses import PollWeek
from cfb_data.rankings.sources import rankings


@dataset(
    id="tests.source_faithful_rankings",
    revision=1,
    row=PollWeek,
    grain="one poll week",
    keys=("season", "season_type", "week"),
)
def _source_faithful_rankings(year: int) -> RecipeRef[list[PollWeek]]:
    """Build the Rankings source through its public callable."""
    return rankings(year=year)


def test_rankings_source_uses_its_domain_operation() -> None:
    """Derive identity and cost from the existing client contract."""
    graph = _compile_recipe(_source_faithful_rankings, (), {"year": 2024})

    assert rankings.id == "cfbd.rankings.list"
    assert rankings.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
