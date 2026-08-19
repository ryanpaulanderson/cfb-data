"""Provide the independently authored game-summary dataset recipe.

``game_summaries`` reads the public ``cfb_data.games.sources.games`` source and
produces one row per selected game, keyed by ``game_id``. It preserves future,
incomplete, and completed games. Total points, absolute margin, result state,
and winner/loser identifiers are populated only when the source marks a game
complete and reports both scores; a missing score is never treated as zero.
Broadcasts and Tier 1 weather are explicit enrichments with per-game coverage;
neither enrichment may add or remove a base game.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, require_one, step, value
from cfb_data.enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)
from cfb_data.games.models.pydantic.responses import (
    Game,
    GameMedia,
    GamePlayoff,
    GameWeather,
)
from cfb_data.games.sources import game_media, game_weather, games
from pydantic import BaseModel, ConfigDict, Field


class GameResultState(StrEnum):
    """Classify a result supported by completion and both scores."""

    home_win = "home_win"
    away_win = "away_win"
    tie = "tie"


class GameEnrichmentCoverage(StrEnum):
    """Describe whether one optional game enrichment was found."""

    not_requested = "not_requested"
    empty = "empty"
    present = "present"


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
    media_coverage: GameEnrichmentCoverage = Field(
        default=GameEnrichmentCoverage.not_requested,
        description="Explicit broadcast enrichment availability.",
    )
    media: list[GameMedia] | None = Field(
        default=None,
        description="Source-ordered broadcast outlets when requested.",
    )
    weather_coverage: GameEnrichmentCoverage = Field(
        default=GameEnrichmentCoverage.not_requested,
        description="Explicit Tier 1 weather enrichment availability.",
    )
    weather: GameWeather | None = Field(
        default=None,
        description="Validated game weather when requested and available.",
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
    revision=2,
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


@step(
    id="cfbd.game_summaries.attach_enrichments",
    revision=1,
    output=GameSummary,
    deterministic=True,
)
def attach_game_enrichments(
    summaries: list[GameSummary],
    *,
    media: list[GameMedia] | None,
    weather: list[GameWeather] | None,
) -> list[GameSummary]:
    """Attach requested media and weather without changing base rows.

    :param summaries: Validated game-summary base universe.
    :param media: Requested source media, or ``None`` when omitted.
    :param weather: Requested source weather, or ``None`` when omitted.
    :return: The same ordered game universe with explicit enrichment coverage.
    :raises ValueError: If enrichment identity is duplicated or conflicts.
    """
    enriched = summaries
    if media is not None:
        enriched = _attach_media(enriched, media)
    if weather is not None:
        enriched = _attach_weather(enriched, weather)
    return enriched


@dataset(
    id="cfbd.game_summaries",
    revision=2,
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
    include_media: bool = False,
    media_type: MediaType | None = None,
    include_weather: bool = False,
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
    :param include_media: Request source-faithful game broadcasts.
    :param media_type: Optional broadcast-medium selector for requested media.
    :param include_weather: Request Tier 1 game weather.
    :return: A reference to the validated game-summary dataset.
    :raises ValueError: If an enrichment lacks a safe bounded selector shape.
    """
    summaries = normalize_games(
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
    if media_type is not None and not include_media:
        raise ValueError("media_type requires include_media=True")

    requested_media: RecipeRef[list[GameMedia]] | None = None
    if include_media and game_id is not None:
        context = require_one(summaries)
        requested_media = game_media(
            year=value(context, path=("season",), expected_type=int),
            week=value(context, path=("week",), expected_type=int),
            team=value(context, path=("home_team",), expected_type=str),
            media_type=media_type,
        )
    elif include_media:
        if year is None:
            raise ValueError("Media enrichment requires a season or exact game ID")
        if any(selector is not None for selector in (home, away, competition, round)):
            raise ValueError(
                "Media enrichment does not support home, away, or playoff selectors"
            )
        requested_media = game_media(
            year=year,
            week=week,
            season_type=season_type,
            team=team,
            conference=conference,
            media_type=media_type,
            classification=classification,
        )

    requested_weather: RecipeRef[list[GameWeather]] | None = None
    if include_weather and game_id is not None:
        requested_weather = game_weather(game_id=game_id)
    elif include_weather:
        if year is None:
            raise ValueError("Weather enrichment requires a season or exact game ID")
        if any(selector is not None for selector in (home, away, competition, round)):
            raise ValueError(
                "Weather enrichment does not support home, away, or playoff selectors"
            )
        requested_weather = game_weather(
            year=year,
            week=week,
            season_type=season_type,
            team=team,
            conference=conference,
            classification=classification,
        )

    if requested_media is None and requested_weather is None:
        return summaries
    return attach_game_enrichments(
        summaries,
        media=requested_media,
        weather=requested_weather,
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


def _attach_media(
    summaries: list[GameSummary],
    media: list[GameMedia],
) -> list[GameSummary]:
    """Attach source-ordered broadcasts by stable game ID.

    :param summaries: Complete base game universe.
    :param media: Validated media rows returned for the declared selector.
    :return: The unchanged base universe with media coverage and rows attached.
    :raises ValueError: If media are duplicated, conflicting, or out of scope.
    """
    base = {summary.game_id: summary for summary in summaries}
    indexed: dict[int, list[GameMedia]] = {}
    observed: set[tuple[int, MediaType, str]] = set()
    for item in media:
        key = (item.id, item.media_type, item.outlet)
        if key in observed:
            raise ValueError("Game media contain a duplicate game/type/outlet key")
        observed.add(key)
        summary = base.get(item.id)
        if summary is None:
            raise ValueError("Game media fall outside the base row universe")
        _validate_game_enrichment(
            summary,
            season=item.season,
            week=item.week,
            season_type=item.season_type,
            start_time=item.start_time,
            home_team=item.home_team,
            home_conference=item.home_conference,
            away_team=item.away_team,
            away_conference=item.away_conference,
            label="Game media",
        )
        indexed.setdefault(item.id, []).append(item)
    return [
        summary.model_copy(
            update={
                "media_coverage": (
                    GameEnrichmentCoverage.present
                    if summary.game_id in indexed
                    else GameEnrichmentCoverage.empty
                ),
                "media": indexed.get(summary.game_id, []),
            }
        )
        for summary in summaries
    ]


def _attach_weather(
    summaries: list[GameSummary],
    weather: list[GameWeather],
) -> list[GameSummary]:
    """Attach at most one weather observation by stable game ID.

    :param summaries: Complete base game universe.
    :param weather: Validated weather rows returned for the declared selector.
    :return: The unchanged base universe with weather coverage attached.
    :raises ValueError: If weather is duplicated, conflicting, or out of scope.
    """
    base = {summary.game_id: summary for summary in summaries}
    indexed: dict[int, GameWeather] = {}
    for item in weather:
        if item.id in indexed:
            raise ValueError("Game weather contains a duplicate game key")
        summary = base.get(item.id)
        if summary is None:
            raise ValueError("Game weather falls outside the base row universe")
        _validate_game_enrichment(
            summary,
            season=item.season,
            week=item.week,
            season_type=item.season_type,
            start_time=item.start_time,
            home_team=item.home_team,
            home_conference=item.home_conference,
            away_team=item.away_team,
            away_conference=item.away_conference,
            label="Game weather",
        )
        if (
            summary.venue_id is not None
            and item.venue_id != summary.venue_id
            or summary.venue is not None
            and item.venue != summary.venue
        ):
            raise ValueError("Game weather conflicts with the selected venue")
        indexed[item.id] = item
    return [
        summary.model_copy(
            update={
                "weather_coverage": (
                    GameEnrichmentCoverage.present
                    if summary.game_id in indexed
                    else GameEnrichmentCoverage.empty
                ),
                "weather": indexed.get(summary.game_id),
            }
        )
        for summary in summaries
    ]


def _validate_game_enrichment(
    summary: GameSummary,
    *,
    season: int,
    week: int,
    season_type: SeasonType,
    start_time: datetime,
    home_team: str,
    home_conference: str | None,
    away_team: str,
    away_conference: str | None,
    label: str,
) -> None:
    """Validate common source context before attaching an enrichment.

    :param summary: Selected base game.
    :param season: Enrichment season.
    :param week: Enrichment week.
    :param season_type: Enrichment season phase.
    :param start_time: Enrichment scheduled instant.
    :param home_team: Enrichment home-team name.
    :param home_conference: Enrichment home conference, when reported.
    :param away_team: Enrichment away-team name.
    :param away_conference: Enrichment away conference, when reported.
    :param label: Safe enrichment label for a validation error.
    :raises ValueError: If stable game context conflicts.
    """
    if (
        season != summary.season
        or week != summary.week
        or season_type != summary.season_type
        or start_time != summary.start_date
        or _normalized_team(home_team) != _normalized_team(summary.home_team)
        or _normalized_team(away_team) != _normalized_team(summary.away_team)
        or (
            home_conference is not None
            and summary.home_conference is not None
            and home_conference != summary.home_conference
        )
        or (
            away_conference is not None
            and summary.away_conference is not None
            and away_conference != summary.away_conference
        )
    ):
        raise ValueError(f"{label} conflict with the selected game context")


def _normalized_team(value: str) -> str:
    """Return a deterministic comparison form for one source team name.

    :param value: Source team name.
    :return: Whitespace-normalized, case-insensitive text.
    """
    return " ".join(value.split()).casefold()


__all__ = [
    "GameEnrichmentCoverage",
    "GameResultState",
    "GameSummary",
    "game_summaries",
]
