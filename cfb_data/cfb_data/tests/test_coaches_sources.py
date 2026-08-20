"""Test endpoint-owned Coaches operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.coaches.models.pydantic.responses import CoachTenure, DetailedCoachSeason
from cfb_data.coaches.sources import coach_seasons, coach_tenures


@dataset(
    id="tests.source_faithful_coach_seasons",
    revision=1,
    row=DetailedCoachSeason,
    grain="one coach team season",
    keys=("year",),
)
def _source_faithful_coach_seasons(year: int) -> RecipeRef[list[DetailedCoachSeason]]:
    return coach_seasons(year=year)


@dataset(
    id="tests.source_faithful_coach_tenures",
    revision=1,
    row=CoachTenure,
    grain="one coach team tenure",
    keys=("id",),
)
def _source_faithful_coach_tenures(year: int) -> RecipeRef[list[CoachTenure]]:
    return coach_tenures(year=year)


def test_coach_sources_use_their_domain_operations() -> None:
    """Derive identities and costs from existing client contracts."""
    seasons = _compile_recipe(_source_faithful_coach_seasons, (), {"year": 2024})
    tenures = _compile_recipe(_source_faithful_coach_tenures, (), {"year": 2024})

    assert coach_seasons.id == "cfbd.coaches.seasons"
    assert coach_tenures.id == "cfbd.coaches.tenures"
    assert seasons.nodes[0].declaration.operation is not None
    assert tenures.nodes[0].declaration.operation is not None
    assert seasons.nodes[0].declaration.source_cost == 1
    assert tenures.nodes[0].declaration.source_cost == 1
