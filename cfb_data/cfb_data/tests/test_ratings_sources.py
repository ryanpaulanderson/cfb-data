"""Test endpoint-owned Ratings operations and public recipe sources."""

from __future__ import annotations

from typing import TypedDict

from cfb_data.analytics import workflow
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.ratings.models.pydantic.responses import (
    ConferenceSP,
    ExpandedTeamSRS,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)
from cfb_data.ratings.sources import (
    conference_sp_ratings,
    core_ratings,
    elo_ratings,
    expanded_srs_ratings,
    fpi_ratings,
    sp_ratings,
    srs_ratings,
)


class _RatingSourceRefs(TypedDict):
    """Describe one reference to every public Ratings source."""

    core: list[TeamCoreRating]
    sp: list[TeamSP]
    conference_sp: list[ConferenceSP]
    srs: list[TeamSRS]
    expanded_srs: list[ExpandedTeamSRS]
    elo: list[TeamElo]
    fpi: list[TeamFPI]


@workflow(id="tests.source_faithful_ratings", revision=1)
def _source_faithful_ratings(year: int) -> _RatingSourceRefs:
    """Build every Ratings source through its public callable."""
    return {
        "core": core_ratings(year=year),
        "sp": sp_ratings(year=year),
        "conference_sp": conference_sp_ratings(year=year),
        "srs": srs_ratings(year=year),
        "expanded_srs": expanded_srs_ratings(year=year),
        "elo": elo_ratings(year=year),
        "fpi": fpi_ratings(year=year),
    }


def test_ratings_sources_use_their_domain_operations() -> None:
    """Derive all Ratings identities and costs from endpoint contracts."""
    graph = _compile_recipe(_source_faithful_ratings, (), {"year": 2024})

    source_nodes = [node for node in graph.nodes if node.kind == "source"]
    assert [node.declaration.recipe_id for node in source_nodes] == [
        "cfbd.ratings.core",
        "cfbd.ratings.sp",
        "cfbd.ratings.conference_sp",
        "cfbd.ratings.srs",
        "cfbd.ratings.expanded_srs",
        "cfbd.ratings.elo",
        "cfbd.ratings.fpi",
    ]
    assert all(node.declaration.operation is not None for node in source_nodes)
    assert all(node.declaration.source_cost == 1 for node in source_nodes)
