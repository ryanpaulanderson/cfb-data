"""Test endpoint-owned Metrics operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability
from cfb_data.metrics.sources import play_win_probabilities


@dataset(
    id="tests.source_faithful_play_probabilities",
    revision=1,
    row=PlayWinProbability,
    grain="one play probability",
    keys=("game_id", "play_id"),
)
def _source_faithful_play_probabilities(
    game_id: int,
) -> RecipeRef[list[PlayWinProbability]]:
    """Build the Metrics source through its public callable."""
    return play_win_probabilities(game_id=game_id)


def test_play_probability_source_uses_its_domain_operation() -> None:
    """Derive route identity from the same operation as the client resource."""
    graph = _compile_recipe(
        _source_faithful_play_probabilities,
        (),
        {"game_id": 401628515},
    )

    assert play_win_probabilities.id == "cfbd.metrics.play_win_probabilities"
    assert play_win_probabilities.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
