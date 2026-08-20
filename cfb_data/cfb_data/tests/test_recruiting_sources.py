"""Test endpoint-owned Recruiting operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)
from cfb_data.recruiting.sources import recruiting_players, recruiting_teams


@dataset(
    id="tests.source_faithful_recruits",
    revision=1,
    row=Recruit,
    grain="one recruit",
    keys=("id",),
)
def _source_faithful_recruits(year: int) -> RecipeRef[list[Recruit]]:
    return recruiting_players(year=year)


@dataset(
    id="tests.source_faithful_recruiting_teams",
    revision=1,
    row=TeamRecruitingRanking,
    grain="one team class ranking",
    keys=("year", "team"),
)
def _source_faithful_recruiting_teams(
    year: int,
) -> RecipeRef[list[TeamRecruitingRanking]]:
    return recruiting_teams(year=year)


def test_recruiting_sources_use_their_domain_operations() -> None:
    """Derive identities and costs from existing client contracts."""
    players = _compile_recipe(_source_faithful_recruits, (), {"year": 2024})
    teams = _compile_recipe(_source_faithful_recruiting_teams, (), {"year": 2024})

    assert recruiting_players.id == "cfbd.recruiting.players"
    assert recruiting_teams.id == "cfbd.recruiting.teams"
    assert players.nodes[0].declaration.operation is not None
    assert teams.nodes[0].declaration.operation is not None
    assert players.nodes[0].declaration.source_cost == 1
    assert teams.nodes[0].declaration.source_cost == 1
