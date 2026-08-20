"""Define a user-owned dataset with the public recipe authoring surface."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games
from pydantic import BaseModel, ConfigDict, Field


class CompletedGame(BaseModel):
    """Represent one completed game with an explicit total-points policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    game_id: int = Field(json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(json_schema_extra={"semantic_type": "dimension"})
    home_team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    away_team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    total_points: int = Field(json_schema_extra={"semantic_type": "measure"})


@step(id="example.completed_games.normalize", revision=1, output=CompletedGame)
def normalize_completed_games(rows: list[Game]) -> list[CompletedGame]:
    """Keep completed games with both scores and derive their explicit total."""
    return [
        CompletedGame(
            game_id=row.id,
            season=row.season,
            week=row.week,
            home_team=row.home_team,
            away_team=row.away_team,
            total_points=row.home_points + row.away_points,
        )
        for row in rows
        if row.completed and row.home_points is not None and row.away_points is not None
    ]


@dataset(
    id="example.completed_games",
    revision=1,
    row=CompletedGame,
    grain="one completed game",
    keys=("game_id",),
    order_by=("season", "week", "game_id"),
    partition_by=("season",),
)
def completed_games(
    *,
    year: int,
    team: str | None = None,
) -> RecipeRef[list[CompletedGame]]:
    """Build completed game totals from validated source rows."""
    return normalize_completed_games(games(year=year, team=team))


__all__ = ["CompletedGame", "completed_games", "normalize_completed_games"]
