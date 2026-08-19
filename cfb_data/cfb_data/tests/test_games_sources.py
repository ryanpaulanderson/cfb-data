"""Tests for endpoint-owned Games operations and public recipe sources."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    Game,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)
from cfb_data.games.sources import (
    advanced_box_score,
    games,
    player_game_stats,
    team_game_stats,
    team_records,
)

from cfb_data import CFBDClient

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


@dataset(
    id="tests.source_faithful_advanced_box_score",
    revision=1,
    row=AdvancedBoxScore,
    grain="one advanced game box score",
    keys=(),
)
def _source_faithful_advanced_box_score(
    game_id: int,
) -> RecipeRef[list[AdvancedBoxScore]]:
    """Build the one-object Games source through its public callable."""
    return advanced_box_score(game_id=game_id)


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


@dataset(
    id="tests.source_faithful_team_records",
    revision=1,
    row=TeamRecords,
    grain="one team season",
    keys=("year", "team_id"),
)
def _source_faithful_team_records(year: int) -> RecipeRef[list[TeamRecords]]:
    """Build the Records source through its public callable."""
    return team_records(year=year)


def test_public_games_source_derives_endpoint_owned_identity() -> None:
    """Expose operation identity without duplicating route contract metadata."""
    assert games.kind == "source"
    assert games.id == "cfbd.games.list"
    assert games.revision == 1


@pytest.mark.asyncio
async def test_one_object_source_shares_resource_contract_and_runtime(
    api_server: ServerFactory,
    advanced_box_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Normalize one HTTP object through the ordinary source row path."""

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/game/box/advanced"
        return web.json_response(advanced_box_response)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "source-fidelity-key",
            base_url=base_url,
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            endpoint = await client.games.advanced_box_score(game_id=401628347)
            recipe = await _source_faithful_advanced_box_score(
                client,
                game_id=401628347,
            )

    assert len(recipe) == 1
    assert recipe.loc[0, "game_info"] == endpoint.game_info.model_dump(mode="python")


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


def test_team_records_source_uses_its_domain_operation() -> None:
    """Derive Records identity and cost from the client endpoint contract."""
    graph = _compile_recipe(_source_faithful_team_records, (), {"year": 2024})

    assert team_records.id == "cfbd.games.team_records"
    assert team_records.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
