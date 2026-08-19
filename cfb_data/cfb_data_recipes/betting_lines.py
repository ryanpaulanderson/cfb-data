"""Provide the independently authored betting-lines dataset recipe.

``betting_lines`` flattens validated game/provider nesting into one quote per
game, provider, and source ordinal. Open and current values retain their source
names and nulls. The recipe does not choose a provider, relabel a value as a
closing line, or derive ATS and total outcomes without a quote-selection policy.
"""

from __future__ import annotations

from datetime import datetime

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.betting.sources import betting_lines as betting_lines_source
from cfb_data.enums import Classification, SeasonType
from pydantic import BaseModel, ConfigDict, Field


class BettingLine(BaseModel):
    """Represent one provider quote for one game."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    season_type: SeasonType = Field(json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    start_date: datetime = Field(json_schema_extra={"semantic_type": "time"})
    home_team_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    home_team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    home_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_classification: Classification | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_score: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    away_team_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    away_team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    away_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    away_classification: Classification | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    away_score: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    provider: str = Field(json_schema_extra={"semantic_type": "dimension"})
    source_ordinal: int = Field(ge=0)
    spread: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    formatted_spread: str = Field(json_schema_extra={"semantic_type": "text"})
    spread_open: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    over_under: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    over_under_open: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    home_moneyline: int | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure"},
    )
    away_moneyline: int | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure"},
    )


@step(
    id="cfbd.betting_lines.flatten",
    revision=1,
    output=BettingLine,
    deterministic=True,
)
def flatten_betting_lines(games: list[BettingGame]) -> list[BettingLine]:
    """Flatten provider quotes while preserving source order and nulls.

    :param games: Validated betting games with nested provider quotes.
    :return: Provider quote rows in deterministic game/source order.
    """
    rows: list[BettingLine] = []
    for game in games:
        for source_ordinal, line in enumerate(game.lines):
            rows.append(
                BettingLine(
                    game_id=game.id,
                    season=game.season,
                    season_type=game.season_type,
                    week=game.week,
                    start_date=game.start_date,
                    home_team_id=game.home_team_id,
                    home_team=game.home_team,
                    home_conference=game.home_conference,
                    home_classification=game.home_classification,
                    home_score=game.home_score,
                    away_team_id=game.away_team_id,
                    away_team=game.away_team,
                    away_conference=game.away_conference,
                    away_classification=game.away_classification,
                    away_score=game.away_score,
                    provider=line.provider,
                    source_ordinal=source_ordinal,
                    spread=line.spread,
                    formatted_spread=line.formatted_spread,
                    spread_open=line.spread_open,
                    over_under=line.over_under,
                    over_under_open=line.over_under_open,
                    home_moneyline=line.home_moneyline,
                    away_moneyline=line.away_moneyline,
                )
            )
    return sorted(
        rows,
        key=lambda row: (row.season, row.week, row.game_id, row.source_ordinal),
    )


@dataset(
    id="cfbd.betting_lines",
    revision=1,
    row=BettingLine,
    grain="one provider quote per game and source ordinal",
    keys=("game_id", "provider", "source_ordinal"),
    order_by=("season", "week", "game_id", "source_ordinal"),
    partition_by=("season",),
    event_time="start_date",
)
def betting_lines(
    *,
    game_id: int | None = None,
    season: int | None = None,
    season_type: SeasonType | None = None,
    week: int | None = None,
    team: str | None = None,
    home: str | None = None,
    away: str | None = None,
    conference: str | None = None,
    provider: str | None = None,
) -> RecipeRef[list[BettingLine]]:
    """Build flattened historical provider quotes.

    :param game_id: Optional exact game identifier.
    :param season: Optional season year when game ID is absent.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param team: Optional participating-team selector.
    :param home: Optional home-team selector.
    :param away: Optional away-team selector.
    :param conference: Optional participating-conference selector.
    :param provider: Optional source provider selector.
    :return: A reference to the validated betting-lines dataset.
    """
    return flatten_betting_lines(
        betting_lines_source(
            game_id=game_id,
            year=season,
            season_type=season_type,
            week=week,
            team=team,
            home=home,
            away=away,
            conference=conference,
            provider=provider,
        )
    )


__all__ = ["BettingLine", "betting_lines"]
