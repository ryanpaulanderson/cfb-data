"""Tests for endpoint-owned Games operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.games.models.pydantic.responses import (
    Game,
    PlayerGameStats,
    TeamGameStats,
)
from cfb_data.games.sources import games, player_game_stats, team_game_stats


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


@dataset(
    id="tests.source_faithful_team_game_stats",
    revision=1,
    row=TeamGameStats,
    grain="one game with nested team statistics",
    keys=("id",),
)
def _source_faithful_team_game_stats(
    game_id: int,
) -> RecipeRef[list[TeamGameStats]]:
    """Build the conventional team-stat source through its public callable."""
    return team_game_stats(game_id=game_id)


@dataset(
    id="tests.source_faithful_player_game_stats",
    revision=1,
    row=PlayerGameStats,
    grain="one game with nested player statistics",
    keys=("id",),
)
def _source_faithful_player_game_stats(
    game_id: int,
) -> RecipeRef[list[PlayerGameStats]]:
    """Build the player-stat source through its public callable."""
    return player_game_stats(game_id=game_id)


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


def test_team_game_stats_source_uses_its_domain_operation() -> None:
    """Derive team-stat route identity from the same operation as the resource."""
    graph = _compile_recipe(
        _source_faithful_team_game_stats,
        (),
        {"game_id": 401628515},
    )

    assert team_game_stats.id == "cfbd.games.team_stats"
    assert team_game_stats.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1


def test_player_game_stats_source_uses_its_domain_operation() -> None:
    """Derive player-stat route identity from the same operation as the resource."""
    graph = _compile_recipe(
        _source_faithful_player_game_stats,
        (),
        {"game_id": 401628515},
    )

    assert player_game_stats.id == "cfbd.games.player_stats"
    assert player_game_stats.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
