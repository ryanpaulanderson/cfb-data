"""Provide shared module-bound recipes for analytics black-box tests."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, SourceContext, dataset, source, step, workflow
from pydantic import BaseModel


class SourceRow(BaseModel):
    """Represent a test source row."""

    game_id: int
    year: int


class DatasetRow(BaseModel):
    """Represent a test dataset row."""

    game_id: int
    year: int


@source(id="tests.games", revision=1, output=SourceRow, cost=1)
async def games(context: SourceContext[SourceRow], *, year: int) -> list[SourceRow]:
    """Retrieve test games."""
    return await context.retrieve(year=year)


@step(id="tests.normalize", revision=1, output=DatasetRow)
def normalize(rows: list[SourceRow]) -> list[DatasetRow]:
    """Normalize test games."""
    return [DatasetRow(game_id=row.game_id, year=row.year) for row in rows]


@dataset(
    id="tests.game_summaries",
    revision=1,
    row=DatasetRow,
    grain="one game",
    keys=("game_id",),
    order_by=("year", "game_id"),
)
def game_summaries(year: int, team: str | None = None) -> RecipeRef[list[DatasetRow]]:
    """Build a test game-summary graph."""
    del team
    return normalize(games(year=year))


@workflow(id="tests.game_analysis", revision=1)
def game_analysis(year: int) -> dict[str, RecipeRef[list[DatasetRow]]]:
    """Build a test workflow graph."""
    return {"games": game_summaries(year=year)}
