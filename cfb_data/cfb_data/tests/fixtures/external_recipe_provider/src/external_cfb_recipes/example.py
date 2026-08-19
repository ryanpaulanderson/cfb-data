"""Define an external dataset solely through the public authoring surface."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from pydantic import BaseModel


class ExternalSeason(BaseModel):
    """Represent one external-provider season row."""

    year: int
    label: str


@step(id="external.make_season", revision=1, output=ExternalSeason)
def make_season(year: int) -> list[ExternalSeason]:
    """Build one deterministic external test row."""
    return [ExternalSeason(year=year, label=f"Season {year}")]


@dataset(
    id="external.season",
    revision=1,
    row=ExternalSeason,
    grain="one season",
    keys=("year",),
    order_by=("year",),
)
def external_season(year: int) -> RecipeRef[list[ExternalSeason]]:
    """Build an external dataset graph."""
    return make_season(year)
