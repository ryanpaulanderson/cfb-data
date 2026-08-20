"""Test endpoint-owned Metrics operations and public recipe sources."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.metrics.models.pydantic.responses import (
    PlayWinProbability,
    TeamGamePredictedPointsAdded,
)
from cfb_data.metrics.sources import play_win_probabilities, team_game_ppa

from cfb_data import CFBDClient

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


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


@dataset(
    id="tests.source_faithful_team_game_ppa",
    revision=1,
    row=TeamGamePredictedPointsAdded,
    grain="one team perspective PPA record per game",
    keys=("game_id", "team"),
)
def _source_faithful_team_game_ppa(
    year: int,
) -> RecipeRef[list[TeamGamePredictedPointsAdded]]:
    """Build the team-game PPA source through its public callable."""
    return team_game_ppa(year=year)


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


def test_ppa_sources_use_their_domain_operations() -> None:
    """Derive PPA route identity from the same operation as the resource."""
    graph = _compile_recipe(
        _source_faithful_team_game_ppa,
        (),
        {"year": 2024},
    )

    assert team_game_ppa.id == "cfbd.metrics.team_game_ppa"
    assert team_game_ppa.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1


@pytest.mark.asyncio
async def test_source_recipe_preserves_endpoint_rows_without_manipulation(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Keep validated retrieval source-shaped until an explicit recipe step."""
    unit = {
        "overall": 0.2,
        "passing": 0.3,
        "rushing": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
    }
    payload = [
        {
            "gameId": 401628452,
            "season": 2024,
            "week": 1,
            "seasonType": "regular",
            "team": "Michigan",
            "conference": "B1G",
            "opponent": "Fresno State",
            "offense": unit,
            "defense": unit,
        }
    ]

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/ppa/games"
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "source-fidelity-key",
            base_url=base_url,
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            endpoint = await client.metrics.team_game_ppa(year=2024)
            recipe = await _source_faithful_team_game_ppa(client, year=2024)

    assert recipe.to_dict(orient="records") == endpoint.to_dict(orient="records")
