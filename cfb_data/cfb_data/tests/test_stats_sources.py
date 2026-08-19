"""Test endpoint-owned Stats operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
)
from cfb_data.stats.sources import (
    advanced_season_stats,
    player_season_stats,
    team_season_stats,
)


@dataset(
    id="tests.source_faithful_player_season_stats",
    revision=1,
    row=PlayerStat,
    grain="one player statistic",
    keys=("season", "team", "player_id", "category", "stat_type"),
)
def _source_faithful_player_season_stats(year: int) -> RecipeRef[list[PlayerStat]]:
    """Build player season statistics through their public source."""
    return player_season_stats(year=year)


@dataset(
    id="tests.source_faithful_team_season_stats",
    revision=1,
    row=TeamStat,
    grain="one team statistic",
    keys=("season", "team", "stat_name"),
)
def _source_faithful_team_season_stats(year: int) -> RecipeRef[list[TeamStat]]:
    """Build conventional season statistics through their public source."""
    return team_season_stats(year=year)


@dataset(
    id="tests.source_faithful_advanced_season_stats",
    revision=1,
    row=AdvancedSeasonStat,
    grain="one team season",
    keys=("season", "team"),
)
def _source_faithful_advanced_season_stats(
    year: int,
) -> RecipeRef[list[AdvancedSeasonStat]]:
    """Build advanced season statistics through their public source."""
    return advanced_season_stats(year=year)


def test_season_stat_sources_use_their_domain_operations() -> None:
    """Derive identities and costs from the existing client contracts."""
    conventional = _compile_recipe(
        _source_faithful_team_season_stats,
        (),
        {"year": 2024},
    )
    advanced = _compile_recipe(
        _source_faithful_advanced_season_stats,
        (),
        {"year": 2024},
    )
    players = _compile_recipe(
        _source_faithful_player_season_stats,
        (),
        {"year": 2024},
    )

    assert player_season_stats.id == "cfbd.stats.player_season"
    assert team_season_stats.id == "cfbd.stats.team_season"
    assert advanced_season_stats.id == "cfbd.stats.advanced_season"
    assert conventional.nodes[0].declaration.operation is not None
    assert advanced.nodes[0].declaration.operation is not None
    assert players.nodes[0].declaration.operation is not None
    assert conventional.nodes[0].declaration.source_cost == 1
    assert advanced.nodes[0].declaration.source_cost == 1
    assert players.nodes[0].declaration.source_cost == 1
