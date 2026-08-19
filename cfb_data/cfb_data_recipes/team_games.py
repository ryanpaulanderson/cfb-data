"""Provide the independently authored team-game perspective dataset.

``team_games`` composes the public ``game_summaries`` recipe into exactly two
base rows per selected game, keyed by ``(game_id, team_id)``. Conventional
``/games/teams`` statistics are an explicit enrichment. Requested statistics
must match every base perspective by game and stable team ID; they may enrich
the rows but can never define or change the base row universe.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games.models.pydantic.responses import TeamGameStat, TeamGameStats
from cfb_data.games.sources import team_game_stats
from pydantic import BaseModel, ConfigDict, Field

from cfb_data_recipes.game_summaries import (
    GameResultState,
    GameSummary,
    game_summaries,
)


class TeamGameResult(StrEnum):
    """Classify one proven team-perspective result."""

    win = "win"
    loss = "loss"
    tie = "tie"


class TeamStatsCoverage(StrEnum):
    """Describe whether conventional team statistics were requested and found."""

    not_requested = "not_requested"
    empty = "empty"
    present = "present"


class TeamGame(BaseModel):
    """Represent one stable team perspective within one selected game."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    season_type: SeasonType = Field(json_schema_extra={"semantic_type": "dimension"})
    start_date: datetime = Field(json_schema_extra={"semantic_type": "time"})
    completed: bool = Field(description="Source completion evidence.")
    neutral_site: bool = Field(description="Whether the game uses a neutral site.")
    conference_game: bool = Field(
        description="Whether the source classifies the game as a conference game."
    )
    venue_id: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "identifier"},
    )
    venue: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "text"},
    )
    team_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    classification: Classification | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_away: str = Field(pattern="^(home|away)$")
    perspective_ordinal: int = Field(
        ge=0,
        le=1,
        description="Zero for the home perspective and one for the away perspective.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    opponent_id: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "identifier"},
    )
    opponent: str = Field(json_schema_extra={"semantic_type": "dimension"})
    opponent_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    opponent_classification: Classification | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    opponent_points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    result: TeamGameResult | None = Field(
        default=None,
        description="Team result only when completion and both scores prove it.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    total_points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    margin: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    point_differential: int | None = Field(
        default=None,
        description="Signed team score minus opponent score for a proven result.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    team_stats_coverage: TeamStatsCoverage = Field(
        description="Explicit conventional-stat enrichment availability."
    )
    team_stats: list[TeamGameStat] | None = Field(
        default=None,
        description="Source-ordered conventional statistics when requested.",
    )


@step(
    id="cfbd.team_games.normalize",
    revision=1,
    output=TeamGame,
    deterministic=True,
)
def normalize_team_games(
    summaries: list[GameSummary],
    *,
    statistics: list[TeamGameStats] | None,
) -> list[TeamGame]:
    """Expand games and attach complete ID-matched conventional statistics.

    :param summaries: Validated base game summaries.
    :param statistics: Requested team-stat responses, or ``None`` when omitted.
    :return: Exactly two deterministic perspective rows per game.
    :raises ValueError: If requested enrichment is duplicated or incomplete.
    """
    rows = [
        perspective
        for summary in summaries
        for perspective in (
            _perspective(summary, home=True),
            _perspective(summary, home=False),
        )
    ]
    if statistics is not None:
        rows = _attach_team_stats(rows, statistics)
    return sorted(
        rows,
        key=lambda row: (
            row.season,
            row.week,
            row.game_id,
            row.perspective_ordinal,
        ),
    )


@dataset(
    id="cfbd.team_games",
    revision=1,
    row=TeamGame,
    grain="one team perspective per selected game",
    keys=("game_id", "team_id"),
    order_by=("season", "week", "game_id", "perspective_ordinal"),
    partition_by=("season",),
    event_time="start_date",
)
def team_games(
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
    include_team_stats: bool = False,
) -> RecipeRef[list[TeamGame]]:
    """Build two team-perspective rows per selected game.

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
    :param include_team_stats: Request conventional nested team statistics.
    :return: A reference to the validated team-game dataset.
    """
    summaries = game_summaries(
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
    statistics = (
        team_game_stats(
            year=year,
            week=week,
            season_type=season_type,
            team=team,
            conference=conference,
            game_id=game_id,
            classification=classification,
        )
        if include_team_stats
        else None
    )
    return normalize_team_games(summaries, statistics=statistics)


def _perspective(summary: GameSummary, *, home: bool) -> TeamGame:
    team_id = summary.home_id if home else summary.away_id
    points = summary.home_points if home else summary.away_points
    opponent_points = summary.away_points if home else summary.home_points
    return TeamGame(
        game_id=summary.game_id,
        season=summary.season,
        week=summary.week,
        season_type=summary.season_type,
        start_date=summary.start_date,
        completed=summary.completed,
        neutral_site=summary.neutral_site,
        conference_game=summary.conference_game,
        venue_id=summary.venue_id,
        venue=summary.venue,
        team_id=team_id,
        team=summary.home_team if home else summary.away_team,
        conference=summary.home_conference if home else summary.away_conference,
        classification=(
            summary.home_classification if home else summary.away_classification
        ),
        home_away="home" if home else "away",
        perspective_ordinal=0 if home else 1,
        opponent_id=summary.away_id if home else summary.home_id,
        opponent=summary.away_team if home else summary.home_team,
        opponent_conference=(
            summary.away_conference if home else summary.home_conference
        ),
        opponent_classification=(
            summary.away_classification if home else summary.home_classification
        ),
        points=points,
        opponent_points=opponent_points,
        result=_team_result(summary, team_id),
        total_points=summary.total_points,
        margin=summary.margin,
        point_differential=(
            points - opponent_points
            if summary.result_state is not None
            and points is not None
            and opponent_points is not None
            else None
        ),
        team_stats_coverage=TeamStatsCoverage.not_requested,
        team_stats=None,
    )


def _team_result(summary: GameSummary, team_id: int) -> TeamGameResult | None:
    if summary.result_state is None:
        return None
    if summary.result_state is GameResultState.tie:
        return TeamGameResult.tie
    return TeamGameResult.win if summary.winner_id == team_id else TeamGameResult.loss


def _attach_team_stats(
    rows: list[TeamGame],
    responses: list[TeamGameStats],
) -> list[TeamGame]:
    indexed: dict[tuple[int, int], tuple[str, list[TeamGameStat]]] = {}
    for response in responses:
        for team in response.teams:
            key = (response.id, team.team_id)
            if key in indexed:
                raise ValueError("Team statistics contain a duplicate game/team key")
            indexed[key] = (team.home_away, team.stats)

    enriched: list[TeamGame] = []
    for row in rows:
        match = indexed.get((row.game_id, row.team_id))
        if match is None:
            raise ValueError("Requested team statistics are incomplete")
        source_side, stats = match
        if source_side != row.home_away:
            raise ValueError("Team statistics conflict with the game-side identity")
        enriched.append(
            row.model_copy(
                update={
                    "team_stats_coverage": (
                        TeamStatsCoverage.present if stats else TeamStatsCoverage.empty
                    ),
                    "team_stats": stats,
                }
            )
        )
    return enriched


__all__ = [
    "TeamGame",
    "TeamGameResult",
    "TeamStatsCoverage",
    "team_games",
]
