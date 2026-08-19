"""Test endpoint-owned Plays operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.plays.models.pydantic.responses import Play
from cfb_data.plays.sources import plays


@dataset(
    id="tests.source_faithful_plays",
    revision=1,
    row=Play,
    grain="one play",
    keys=("game_id", "id"),
)
def _source_faithful_plays(year: int, week: int) -> RecipeRef[list[Play]]:
    """Build the Plays source through its public callable."""
    return plays(year=year, week=week)


def test_plays_source_uses_its_domain_operation() -> None:
    """Derive route identity from the same operation as the client resource."""
    graph = _compile_recipe(_source_faithful_plays, (), {"year": 2024, "week": 1})

    assert plays.id == "cfbd.plays.list"
    assert plays.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
