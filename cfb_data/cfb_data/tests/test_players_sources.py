"""Test endpoint-owned Players operations and public recipe sources."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.players.models.pydantic.responses import PlayerUsage, ReturningProduction
from cfb_data.players.sources import player_usage, returning_production
from pandas import DataFrame

from cfb_data import CFBDClient

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


@dataset(
    id="tests.source_faithful_player_usage",
    revision=1,
    row=PlayerUsage,
    grain="one player season usage record",
    keys=("season", "team", "id"),
)
def _source_faithful_player_usage(year: int) -> RecipeRef[list[PlayerUsage]]:
    """Build the player-usage source through its public callable."""
    return player_usage(year=year)


@dataset(
    id="tests.source_faithful_returning_production",
    revision=1,
    row=ReturningProduction,
    grain="one team returning-production season",
    keys=("season", "team"),
)
def _source_faithful_returning_production(
    year: int,
) -> RecipeRef[list[ReturningProduction]]:
    """Build returning production through its public source callable."""
    return returning_production(year=year)


def test_player_usage_source_uses_its_domain_operation() -> None:
    """Derive stable identity and cost from the shared endpoint contract."""
    graph = _compile_recipe(_source_faithful_player_usage, (), {"year": 2024})

    assert player_usage.id == "cfbd.players.usage"
    assert player_usage.revision == 1
    assert graph.nodes[0].declaration.operation is not None
    assert graph.nodes[0].declaration.source_cost == 1


def test_returning_production_source_uses_its_domain_operation() -> None:
    """Derive returning-production identity from the endpoint contract."""
    graph = _compile_recipe(
        _source_faithful_returning_production,
        (),
        {"year": 2024},
    )

    assert returning_production.id == "cfbd.players.returning_production"
    assert returning_production.revision == 1
    assert graph.nodes[0].declaration.operation is not None
    assert graph.nodes[0].declaration.source_cost == 1


@pytest.mark.asyncio
async def test_player_usage_source_preserves_endpoint_rows_without_manipulation(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Keep usage data source-shaped until an explicit analytics step."""
    payload = [
        {
            "season": 2024,
            "id": "001",
            "name": "Example Player",
            "position": "QB",
            "team": "Penn State",
            "conference": "Big Ten",
            "usage": {
                "overall": 0.7,
                "pass": 0.8,
                "rush": 0.5,
                "firstDown": 0.6,
                "secondDown": 0.7,
                "thirdDown": 0.8,
                "standardDowns": 0.65,
                "passingDowns": 0.75,
            },
        }
    ]

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/player/usage"
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "source-fidelity-key",
            base_url=base_url,
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            endpoint = await client.players.usage(year=2024)
            recipe: DataFrame = await _source_faithful_player_usage(client, year=2024)

    assert recipe.to_dict(orient="records") == endpoint.to_dict(orient="records")
