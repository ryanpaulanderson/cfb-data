"""Provide the independently authored game-summary dataset recipe.

``game_summaries`` reads the public ``cfb_data.games.sources.games`` source and
produces one row per selected game, keyed by ``game_id``. It preserves future,
incomplete, and completed games. Total points, absolute margin, result state,
and winner/loser identifiers are populated only when the source marks a game
complete and reports both scores; a missing score is never treated as zero.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games.models.pydantic.responses import Game, GamePlayoff
from cfb_data.games.sources import games
from pydantic import BaseModel, ConfigDict, Field


class GameResultState(StrEnum):
    """Classify a result supported by completion and both scores."""

    home_win = "home_win"
    away_win = "away_win"
    tie = "tie"


class GameSummary(BaseModel):
    """Represent one source-faithful game with conservative result fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int = Field(
        ge=0,
        description="Stable CFBD game identifier; normalized from source field id.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    season: int = Field(
        ge=0,
        description="Season containing the game.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    week: int = Field(
        ge=0,
        description="Season week containing the game.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    season_type: SeasonType = Field(
        description="Source season phase.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    start_date: datetime = Field(
        description="Scheduled game instant normalized to UTC by the source contract.",
        json_schema_extra={"semantic_type": "time"},
    )
    start_time_tbd: bool = Field(description="Whether the start time remains TBD.")
    completed: bool = Field(description="Source completion evidence.")
    neutral_site: bool = Field(description="Whether the game uses a neutral site.")
    conference_game: bool = Field(
        description="Whether the source classifies the game as a conference game."
    )
    attendance: int | None = Field(
        default=None,
        ge=0,
        description="Reported attendance, when available.",
        json_schema_extra={"semantic_type": "measure", "unit": "people"},
    )
    venue_id: int | None = Field(
        default=None,
        ge=0,
        description="Source venue identifier, when available.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    venue: str | None = Field(
        default=None,
        description="Source venue name, when available.",
        json_schema_extra={"semantic_type": "text"},
    )
    home_id: int = Field(
        ge=0,
        description="Stable home-team identifier.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    home_team: str = Field(description="Source home-team name.")
    home_conference: str | None = Field(
        default=None,
        description="Source home-team conference.",
    )
    home_classification: Classification | None = Field(
        default=None,
        description="Source home-team classification.",
    )
    home_points: int | None = Field(
        default=None,
        ge=0,
        description="Reported home score; missing scores remain null.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    home_line_scores: list[float] | None = Field(
        default=None,
        description="Source-ordered home scoring-period values.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    home_postgame_win_probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Source postgame home win probability.",
        json_schema_extra={"semantic_type": "measure", "unit": "ratio"},
    )
    home_pregame_elo: int | None = Field(
        default=None,
        description="Source home-team pregame Elo.",
        json_schema_extra={"semantic_type": "measure"},
    )
    home_postgame_elo: int | None = Field(
        default=None,
        description="Source home-team postgame Elo.",
        json_schema_extra={"semantic_type": "measure"},
    )
    away_id: int = Field(
        ge=0,
        description="Stable away-team identifier.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    away_team: str = Field(description="Source away-team name.")
    away_conference: str | None = Field(
        default=None,
        description="Source away-team conference.",
    )
    away_classification: Classification | None = Field(
        default=None,
        description="Source away-team classification.",
    )
    away_points: int | None = Field(
        default=None,
        ge=0,
        description="Reported away score; missing scores remain null.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    away_line_scores: list[float] | None = Field(
        default=None,
        description="Source-ordered away scoring-period values.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    away_postgame_win_probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Source postgame away win probability.",
        json_schema_extra={"semantic_type": "measure", "unit": "ratio"},
    )
    away_pregame_elo: int | None = Field(
        default=None,
        description="Source away-team pregame Elo.",
        json_schema_extra={"semantic_type": "measure"},
    )
    away_postgame_elo: int | None = Field(
        default=None,
        description="Source away-team postgame Elo.",
        json_schema_extra={"semantic_type": "measure"},
    )
    excitement_index: float | None = Field(
        default=None,
        description="Source excitement index.",
        json_schema_extra={"semantic_type": "measure"},
    )
    highlights: str | None = Field(
        default=None,
        description="Source highlights reference.",
        json_schema_extra={"semantic_type": "text"},
    )
    notes: str | None = Field(
        default=None,
        description="Source game notes.",
        json_schema_extra={"semantic_type": "text"},
    )
    playoff: GamePlayoff | None = Field(
        default=None,
        description="Validated nested playoff context, when available.",
    )
    result_state: GameResultState | None = Field(
        default=None,
        description="Derived result only when completion and both scores prove it.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    total_points: int | None = Field(
        default=None,
        ge=0,
        description="Derived combined score only for a proven result.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    margin: int | None = Field(
        default=None,
        ge=0,
        description="Derived absolute score margin only for a proven result.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    winner_id: int | None = Field(
        default=None,
        ge=0,
        description="Winning team identifier; ties and unproven results remain null.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    loser_id: int | None = Field(
        default=None,
        ge=0,
        description="Losing team identifier; ties and unproven results remain null.",
        json_schema_extra={"semantic_type": "identifier"},
    )


@step(
    id="cfbd.game_summaries.normalize",
    revision=1,
    output=GameSummary,
    deterministic=True,
)
def normalize_games(rows: list[Game]) -> list[GameSummary]:
    """Normalize validated source games and derive conservative results.

    :param rows: Validated source games in upstream order.
    :return: Game summaries in declared deterministic order.
    """
    summaries = [_normalize_game(row) for row in rows]
    return sorted(
        summaries,
        key=lambda row: (row.season, row.week, row.game_id),
    )


@dataset(
    id="cfbd.game_summaries",
    revision=1,
    row=GameSummary,
    grain="one selected game",
    keys=("game_id",),
    order_by=("season", "week", "game_id"),
    partition_by=("season",),
    event_time="start_date",
)
def game_summaries(
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: SeasonType | None = None,
    team: str | None = None,
    home: str | None = None,
    away: str | None = None,
    conference: str | None = None,
    classification: Classification | None = None,
    game_id: int | None = None,
    competition: PlayoffCompetition | None = None,
    round: PlayoffRound | None = None,
) -> RecipeRef[list[GameSummary]]:
    """Build game summaries from the registered Games source.

    :param year: Season year, required unless ``game_id`` is supplied.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional participating-team selector.
    :param home: Optional home-team selector.
    :param away: Optional away-team selector.
    :param conference: Optional participating-conference selector.
    :param classification: Optional classification selector.
    :param game_id: Optional exact game identifier.
    :param competition: Optional playoff competition.
    :param round: Optional playoff round.
    :return: A reference to the validated game-summary dataset.
    """
    return normalize_games(
        games(
            year=year,
            week=week,
            season_type=season_type,
            team=team,
            home=home,
            away=away,
            conference=conference,
            classification=classification,
            game_id=game_id,
            competition=competition,
            round=round,
        )
    )


def _normalize_game(game: Game) -> GameSummary:
    result_state, total_points, margin, winner_id, loser_id = _result(game)
    return GameSummary(
        game_id=game.id,
        season=game.season,
        week=game.week,
        season_type=game.season_type,
        start_date=game.start_date,
        start_time_tbd=game.start_time_tbd,
        completed=game.completed,
        neutral_site=game.neutral_site,
        conference_game=game.conference_game,
        attendance=game.attendance,
        venue_id=game.venue_id,
        venue=game.venue,
        home_id=game.home_id,
        home_team=game.home_team,
        home_conference=game.home_conference,
        home_classification=game.home_classification,
        home_points=game.home_points,
        home_line_scores=game.home_line_scores,
        home_postgame_win_probability=game.home_postgame_win_probability,
        home_pregame_elo=game.home_pregame_elo,
        home_postgame_elo=game.home_postgame_elo,
        away_id=game.away_id,
        away_team=game.away_team,
        away_conference=game.away_conference,
        away_classification=game.away_classification,
        away_points=game.away_points,
        away_line_scores=game.away_line_scores,
        away_postgame_win_probability=game.away_postgame_win_probability,
        away_pregame_elo=game.away_pregame_elo,
        away_postgame_elo=game.away_postgame_elo,
        excitement_index=game.excitement_index,
        highlights=game.highlights,
        notes=game.notes,
        playoff=game.playoff,
        result_state=result_state,
        total_points=total_points,
        margin=margin,
        winner_id=winner_id,
        loser_id=loser_id,
    )


def _result(
    game: Game,
) -> tuple[GameResultState | None, int | None, int | None, int | None, int | None]:
    if not game.completed or game.home_points is None or game.away_points is None:
        return None, None, None, None, None
    total = game.home_points + game.away_points
    margin = abs(game.home_points - game.away_points)
    if game.home_points == game.away_points:
        return GameResultState.tie, total, margin, None, None
    if game.home_points > game.away_points:
        return GameResultState.home_win, total, margin, game.home_id, game.away_id
    return GameResultState.away_win, total, margin, game.away_id, game.home_id


__all__ = ["GameResultState", "GameSummary", "game_summaries"]
