"""Test endpoint-owned Teams operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.teams.models.pydantic.responses import (
    RosterPlayer,
    Team,
    TeamATS,
    TeamTalent,
)
from cfb_data.teams.sources import roster, team_ats, team_talent, teams


@dataset(
    id="tests.source_faithful_teams",
    revision=1,
    row=Team,
    grain="one team",
    keys=("id",),
)
def _source_faithful_teams(year: int) -> RecipeRef[list[Team]]:
    """Build the Teams source through its public callable."""
    return teams(year=year)


@dataset(
    id="tests.source_faithful_roster",
    revision=1,
    row=RosterPlayer,
    grain="one roster membership",
    keys=("team", "id"),
)
def _source_faithful_roster(year: int) -> RecipeRef[list[RosterPlayer]]:
    """Build the Roster source through its public callable."""
    return roster(year=year)


@dataset(
    id="tests.source_faithful_team_ats",
    revision=1,
    row=TeamATS,
    grain="one team ATS season",
    keys=("year", "team_id"),
)
def _source_faithful_team_ats(year: int) -> RecipeRef[list[TeamATS]]:
    """Build the team ATS source through its public callable."""
    return team_ats(year=year)


@dataset(
    id="tests.source_faithful_team_talent",
    revision=1,
    row=TeamTalent,
    grain="one team talent season",
    keys=("year", "team"),
)
def _source_faithful_team_talent(year: int) -> RecipeRef[list[TeamTalent]]:
    """Build the team talent source through its public callable."""
    return team_talent(year=year)


def test_teams_sources_use_their_domain_operations() -> None:
    """Derive stable identities and costs from shared endpoint contracts."""
    teams_graph = _compile_recipe(_source_faithful_teams, (), {"year": 2024})
    roster_graph = _compile_recipe(_source_faithful_roster, (), {"year": 2024})

    assert teams.id == "cfbd.teams.list"
    assert roster.id == "cfbd.teams.roster"
    assert teams_graph.nodes[0].declaration.operation is not None
    assert roster_graph.nodes[0].declaration.operation is not None
    assert teams_graph.nodes[0].declaration.source_cost == 1
    assert roster_graph.nodes[0].declaration.source_cost == 1


def test_team_enrichment_sources_use_their_domain_operations() -> None:
    """Derive ATS and talent identity from shared endpoint contracts."""
    ats_graph = _compile_recipe(_source_faithful_team_ats, (), {"year": 2024})
    talent_graph = _compile_recipe(_source_faithful_team_talent, (), {"year": 2024})

    assert team_ats.id == "cfbd.teams.ats"
    assert team_talent.id == "cfbd.teams.talent"
    assert ats_graph.nodes[0].declaration.operation is not None
    assert talent_graph.nodes[0].declaration.operation is not None
    assert ats_graph.nodes[0].declaration.source_cost == 1
    assert talent_graph.nodes[0].declaration.source_cost == 1
