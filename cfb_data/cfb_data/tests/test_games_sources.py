"""Tests for endpoint-owned Games operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games


@dataset(
    id="tests.source_faithful_games",
    revision=1,
    row=Game,
    grain="one game",
    keys=("id",),
    order_by=("season", "week", "id"),
)
def _source_faithful_games(year: int) -> RecipeRef[list[Game]]:
    """Build one source-faithful Games dataset for contract testing."""
    return games(year=year)


def test_public_games_source_derives_endpoint_owned_identity() -> None:
    """Expose operation identity without duplicating route contract metadata."""
    assert games.kind == "source"
    assert games.id == "cfbd.games.list"
    assert games.revision == 1


def test_games_source_compiles_without_endpoint_or_provider_io() -> None:
    """Compile the public domain source through the ordinary dataset path."""
    graph = _compile_recipe(_source_faithful_games, (), {"year": 2024})

    assert [node.kind for node in graph.nodes] == ["source", "dataset"]
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
    assert source_node.dependencies == ()
