"""Test endpoint-owned Betting operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.betting.sources import betting_lines


@dataset(
    id="tests.source_faithful_betting_lines",
    revision=1,
    row=BettingGame,
    grain="one game with nested provider lines",
    keys=("id",),
)
def _source_faithful_betting_lines(year: int) -> RecipeRef[list[BettingGame]]:
    """Build the Betting source through its public callable."""
    return betting_lines(year=year)


def test_betting_source_uses_its_domain_operation() -> None:
    """Derive identity and cost from the existing client contract."""
    graph = _compile_recipe(_source_faithful_betting_lines, (), {"year": 2024})

    assert betting_lines.id == "cfbd.betting.lines"
    assert betting_lines.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
