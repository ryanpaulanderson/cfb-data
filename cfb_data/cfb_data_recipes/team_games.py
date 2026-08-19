"""Provide the independently authored team-game perspective dataset.

``team_games`` composes the public ``game_summaries`` recipe into exactly two
base rows per selected game, keyed by ``(game_id, team_id)``. Conventional
``/games/teams`` statistics, advanced box metrics, havoc, and game PPA are
explicit enrichments. Requested statistics are resolved only within the
validated game context; they may enrich rows but can never define or change
the base row universe.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games.models.pydantic.responses import TeamGameStat, TeamGameStats
from cfb_data.games.sources import team_game_stats
from cfb_data.metrics.models.pydantic.responses import (
    TeamGamePPAUnit,
    TeamGamePredictedPointsAdded,
)
from cfb_data.metrics.sources import team_game_ppa
from cfb_data.stats.models.pydantic.responses import (
    AdvancedGameDefense,
    AdvancedGameOffense,
    AdvancedGameStat,
    GameHavocStats,
    GameHavocUnit,
)
from cfb_data.stats.sources import advanced_game_stats, game_havoc_stats
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
    """Describe whether a team-game enrichment was requested and found."""

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
    advanced_stats_coverage: TeamStatsCoverage = Field(
        description="Explicit advanced-stat enrichment availability."
    )
    advanced_offense: AdvancedGameOffense | None = Field(
        default=None,
        description="Source advanced offense metrics when requested.",
    )
    advanced_defense: AdvancedGameDefense | None = Field(
        default=None,
        description="Source advanced defense metrics when requested.",
    )
    havoc_coverage: TeamStatsCoverage = Field(
        description="Explicit havoc enrichment availability."
    )
    havoc_offense: GameHavocUnit | None = Field(
        default=None,
        description="Source offensive havoc metrics when requested.",
    )
    havoc_defense: GameHavocUnit | None = Field(
        default=None,
        description="Source defensive havoc metrics when requested.",
    )
    ppa_coverage: TeamStatsCoverage = Field(
        description="Explicit game-PPA enrichment availability."
    )
    ppa_offense: TeamGamePPAUnit | None = Field(
        default=None,
        description="Source offensive predicted-points-added metrics.",
    )
    ppa_defense: TeamGamePPAUnit | None = Field(
        default=None,
        description="Source defensive predicted-points-added metrics.",
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
    advanced: list[AdvancedGameStat] | None,
    havoc: list[GameHavocStats] | None,
    ppa: list[TeamGamePredictedPointsAdded] | None,
    requested_team: str | None,
) -> list[TeamGame]:
    """Expand games and attach complete game-context enrichments.

    :param summaries: Validated base game summaries.
    :param statistics: Requested team-stat responses, or ``None`` when omitted.
    :param advanced: Requested advanced-stat rows, or ``None`` when omitted.
    :param havoc: Requested havoc rows, or ``None`` when omitted.
    :param ppa: Requested game-PPA rows, or ``None`` when omitted.
    :param requested_team: Optional team selector defining required perspectives.
    :return: Exactly two deterministic perspective rows per game.
    :raises ValueError: If requested enrichment is duplicated or inconsistent.
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
    if advanced is not None:
        rows = _attach_advanced_stats(rows, advanced, requested_team=requested_team)
    if havoc is not None:
        rows = _attach_havoc(rows, havoc, requested_team=requested_team)
    if ppa is not None:
        rows = _attach_ppa(rows, ppa, requested_team=requested_team)
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
    include_advanced_stats: bool = False,
    include_havoc: bool = False,
    include_ppa: bool = False,
    exclude_garbage_time: bool | None = None,
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
    :param include_advanced_stats: Request advanced team-game statistics.
    :param include_havoc: Request team-game havoc statistics.
    :param include_ppa: Request team-game predicted-points-added metrics.
    :param exclude_garbage_time: Optional source policy for advanced stats and PPA.
    :return: A reference to the validated team-game dataset.
    :raises ValueError: If game PPA is requested without a season year.
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
    advanced = (
        advanced_game_stats(
            year=year,
            team=team,
            week=week,
            exclude_garbage_time=exclude_garbage_time,
            season_type=season_type,
        )
        if include_advanced_stats
        else None
    )
    havoc = (
        game_havoc_stats(
            year=year,
            team=team,
            week=week,
            season_type=season_type,
        )
        if include_havoc
        else None
    )
    if include_ppa and year is None:
        raise ValueError("Game PPA enrichment requires an explicit season year")
    ppa = (
        team_game_ppa(
            year=year,
            week=week,
            season_type=season_type,
            team=team,
            conference=conference,
            exclude_garbage_time=exclude_garbage_time,
            classification=classification,
        )
        if include_ppa and year is not None
        else None
    )
    return normalize_team_games(
        summaries,
        statistics=statistics,
        advanced=advanced,
        havoc=havoc,
        ppa=ppa,
        requested_team=team,
    )


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
        advanced_stats_coverage=TeamStatsCoverage.not_requested,
        advanced_offense=None,
        advanced_defense=None,
        havoc_coverage=TeamStatsCoverage.not_requested,
        havoc_offense=None,
        havoc_defense=None,
        ppa_coverage=TeamStatsCoverage.not_requested,
        ppa_offense=None,
        ppa_defense=None,
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


def _normalize_team_name(value: str) -> str:
    """Return the deterministic comparison form for a source team name.

    :param value: Source-provided or analyst-provided team name.
    :return: Whitespace-normalized, case-insensitive comparison text.
    """
    return " ".join(value.split()).casefold()


def _required_enrichment_keys(
    rows: list[TeamGame],
    *,
    requested_team: str | None,
) -> set[tuple[int, str]]:
    """Return game-scoped team keys that a requested enrichment must cover.

    :param rows: Complete base team-game perspectives.
    :param requested_team: Optional analyst team selector.
    :return: Required game/name keys within the base universe.
    :raises ValueError: If a team selector cannot be resolved in every game.
    """
    if requested_team is None:
        return {(row.game_id, _normalize_team_name(row.team)) for row in rows}

    requested_name = _normalize_team_name(requested_team)
    required = {
        (row.game_id, requested_name)
        for row in rows
        if _normalize_team_name(row.team) == requested_name
    }
    game_ids = {row.game_id for row in rows}
    if {game_id for game_id, _ in required} != game_ids:
        raise ValueError(
            "Requested team enrichment cannot be resolved within every game"
        )
    return required


def _validate_named_enrichment(
    row: TeamGame,
    *,
    season: int,
    week: int,
    season_type: SeasonType,
    opponent: str,
    label: str,
) -> None:
    """Validate one name-keyed source row against its base game perspective.

    :param row: Base team-game perspective matched within one game.
    :param season: Enrichment season.
    :param week: Enrichment week.
    :param season_type: Enrichment season phase.
    :param opponent: Enrichment opponent name.
    :param label: Safe enrichment label for validation errors.
    :raises ValueError: If source identity conflicts with the base game.
    """
    if (
        season != row.season
        or week != row.week
        or season_type != row.season_type
        or _normalize_team_name(opponent) != _normalize_team_name(row.opponent)
    ):
        raise ValueError(f"{label} conflicts with the selected game context")


def _attach_advanced_stats(
    rows: list[TeamGame],
    responses: list[AdvancedGameStat],
    *,
    requested_team: str | None,
) -> list[TeamGame]:
    """Attach advanced metrics using game-scoped team names.

    :param rows: Complete base team-game perspectives.
    :param responses: Validated advanced-stat source rows.
    :param requested_team: Optional analyst team selector.
    :return: The unchanged base universe with advanced metrics attached.
    :raises ValueError: If source rows are duplicated, conflicting, or partial.
    """
    required = _required_enrichment_keys(rows, requested_team=requested_team)
    base = {(row.game_id, _normalize_team_name(row.team)): row for row in rows}
    indexed: dict[tuple[int, str], AdvancedGameStat] = {}
    for response in responses:
        key = (response.game_id, _normalize_team_name(response.team))
        if key in indexed:
            raise ValueError("Advanced statistics contain a duplicate game/team key")
        row = base.get(key)
        if row is None:
            raise ValueError("Advanced statistics fall outside the base row universe")
        _validate_named_enrichment(
            row,
            season=response.season,
            week=response.week,
            season_type=response.season_type,
            opponent=response.opponent,
            label="Advanced statistics",
        )
        indexed[key] = response
    if responses and not required.issubset(indexed):
        raise ValueError("Requested advanced statistics are incomplete")
    enriched: list[TeamGame] = []
    for row in rows:
        key = (row.game_id, _normalize_team_name(row.team))
        match = indexed.get(key)
        enriched.append(
            row.model_copy(
                update={
                    "advanced_stats_coverage": (
                        TeamStatsCoverage.present
                        if match is not None
                        else (
                            TeamStatsCoverage.empty
                            if key in required
                            else TeamStatsCoverage.not_requested
                        )
                    ),
                    "advanced_offense": match.offense if match is not None else None,
                    "advanced_defense": match.defense if match is not None else None,
                }
            )
        )
    return enriched


def _attach_havoc(
    rows: list[TeamGame],
    responses: list[GameHavocStats],
    *,
    requested_team: str | None,
) -> list[TeamGame]:
    """Attach havoc metrics using game-scoped team names.

    :param rows: Complete base team-game perspectives.
    :param responses: Validated havoc source rows.
    :param requested_team: Optional analyst team selector.
    :return: The unchanged base universe with havoc metrics attached.
    :raises ValueError: If source rows are duplicated, conflicting, or partial.
    """
    required = _required_enrichment_keys(rows, requested_team=requested_team)
    base = {(row.game_id, _normalize_team_name(row.team)): row for row in rows}
    indexed: dict[tuple[int, str], GameHavocStats] = {}
    for response in responses:
        key = (response.game_id, _normalize_team_name(response.team))
        if key in indexed:
            raise ValueError("Havoc statistics contain a duplicate game/team key")
        row = base.get(key)
        if row is None:
            raise ValueError("Havoc statistics fall outside the base row universe")
        _validate_named_enrichment(
            row,
            season=response.season,
            week=response.week,
            season_type=response.season_type,
            opponent=response.opponent,
            label="Havoc statistics",
        )
        if row.conference is not None and response.conference != row.conference:
            raise ValueError("Havoc statistics conflict with the team conference")
        if (
            row.opponent_conference is not None
            and response.opponent_conference != row.opponent_conference
        ):
            raise ValueError("Havoc statistics conflict with the opponent conference")
        indexed[key] = response
    if responses and not required.issubset(indexed):
        raise ValueError("Requested havoc statistics are incomplete")
    enriched: list[TeamGame] = []
    for row in rows:
        key = (row.game_id, _normalize_team_name(row.team))
        match = indexed.get(key)
        enriched.append(
            row.model_copy(
                update={
                    "havoc_coverage": (
                        TeamStatsCoverage.present
                        if match is not None
                        else (
                            TeamStatsCoverage.empty
                            if key in required
                            else TeamStatsCoverage.not_requested
                        )
                    ),
                    "havoc_offense": match.offense if match is not None else None,
                    "havoc_defense": match.defense if match is not None else None,
                }
            )
        )
    return enriched


def _attach_ppa(
    rows: list[TeamGame],
    responses: list[TeamGamePredictedPointsAdded],
    *,
    requested_team: str | None,
) -> list[TeamGame]:
    """Attach game PPA using game-scoped team names.

    :param rows: Complete base team-game perspectives.
    :param responses: Validated game-PPA source rows.
    :param requested_team: Optional analyst team selector.
    :return: The unchanged base universe with PPA metrics attached.
    :raises ValueError: If source rows are duplicated, conflicting, or partial.
    """
    required = _required_enrichment_keys(rows, requested_team=requested_team)
    base = {(row.game_id, _normalize_team_name(row.team)): row for row in rows}
    indexed: dict[tuple[int, str], TeamGamePredictedPointsAdded] = {}
    for response in responses:
        key = (response.game_id, _normalize_team_name(response.team))
        if key in indexed:
            raise ValueError("Game PPA contains a duplicate game/team key")
        row = base.get(key)
        if row is None:
            raise ValueError("Game PPA falls outside the base row universe")
        _validate_named_enrichment(
            row,
            season=response.season,
            week=response.week,
            season_type=response.season_type,
            opponent=response.opponent,
            label="Game PPA",
        )
        if row.conference is not None and response.conference != row.conference:
            raise ValueError("Game PPA conflicts with the team conference")
        indexed[key] = response
    if responses and not required.issubset(indexed):
        raise ValueError("Requested game PPA is incomplete")
    enriched: list[TeamGame] = []
    for row in rows:
        key = (row.game_id, _normalize_team_name(row.team))
        match = indexed.get(key)
        enriched.append(
            row.model_copy(
                update={
                    "ppa_coverage": (
                        TeamStatsCoverage.present
                        if match is not None
                        else (
                            TeamStatsCoverage.empty
                            if key in required
                            else TeamStatsCoverage.not_requested
                        )
                    ),
                    "ppa_offense": match.offense if match is not None else None,
                    "ppa_defense": match.defense if match is not None else None,
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
