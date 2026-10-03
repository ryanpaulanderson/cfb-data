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

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, require_one, step, value
from cfb_data.analytics.tables import SOURCE_ORDINAL
from cfb_data.enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)
from cfb_data.games.models.pydantic.responses import (
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
    revision=3,
    output=GameSummary,
    deterministic=True,
)
def normalize_games(rows: Table) -> Table:
    """Derive conservative game results with native masked expressions.

    :param rows: Validated source-shaped native games.
    :return: Ordered game summaries retaining null and incomplete evidence.
    """
    rows = rows.rename({"id": "game_id"})
    proven = (
        nw.col("completed")
        & ~nw.col("home_points").is_null()
        & ~nw.col("away_points").is_null()
    )
    home = nw.col("home_points") > nw.col("away_points")
    tie = nw.col("home_points") == nw.col("away_points")
    result = (
        nw.when(proven)
        .then(
            nw.when(tie)
            .then(nw.lit("tie"))
            .when(home)
            .then(nw.lit("home_win"))
            .otherwise(nw.lit("away_win"))
        )
        .otherwise(nw.lit(None))
    )
    rows = rows.with_columns(
        result.alias("result_state"),
        nw.when(proven)
        .then(nw.col("home_points") + nw.col("away_points"))
        .otherwise(nw.lit(None))
        .alias("total_points"),
        nw.when(proven)
        .then((nw.col("home_points") - nw.col("away_points")).abs())
        .otherwise(nw.lit(None))
        .alias("margin"),
        nw.when(proven & ~tie)
        .then(nw.when(home).then(nw.col("home_id")).otherwise(nw.col("away_id")))
        .otherwise(nw.lit(None))
        .alias("winner_id"),
        nw.when(proven & ~tie)
        .then(nw.when(home).then(nw.col("away_id")).otherwise(nw.col("home_id")))
        .otherwise(nw.lit(None))
        .alias("loser_id"),
        nw.lit("not_requested").alias("media_coverage"),
        nw.lit(None).alias("media"),
        nw.lit("not_requested").alias("weather_coverage"),
        nw.lit(None).alias("weather"),
    )
    return rows.select(*GameSummary.model_fields).sort("season", "week", "game_id")


@step(
    id="cfbd.game_summaries.select_exact_media",
    revision=2,
    output=GameMedia,
    deterministic=True,
)
def select_exact_game_media(rows: Table, *, game_id: int) -> Table:
    """Filter one game's media while retaining source retrieval semantics.

    :param rows: Validated media table for the containing API partition.
    :param game_id: Exact selected game identifier.
    :return: Native source-ordered media table.
    """
    return rows.filter(nw.col("id") == game_id).select(*GameMedia.model_fields)


@step(
    id="cfbd.game_summaries.attach_enrichments",
    revision=3,
    output=GameSummary,
    deterministic=True,
)
def attach_game_enrichments(
    summaries: Table, *, media: Table | None, weather: Table | None
) -> Table:
    """Join requested media and weather without changing the game universe.

    :param summaries: Validated native game-summary universe.
    :param media: Requested native broadcasts, or omitted.
    :param weather: Requested native weather, or omitted.
    :return: Native game table carrying context and coverage checks.
    """
    rows = summaries
    if media is not None:
        evidence = _checked_game_evidence(summaries, media, label="Game media")
        evidence = evidence.require_unique(
            ("game_id", "media_type", "outlet"),
            message="Game media contain a duplicate game/type/outlet key",
        )
        packed = evidence.pack(
            columns={
                **{name: name for name in GameMedia.model_fields},
                SOURCE_ORDINAL: SOURCE_ORDINAL,
            },
            into="__media_record",
        )
        grouped = packed.ordered_records(
            keys=("game_id",),
            column="__media_record",
            into="__media_records",
            ordinal_field=SOURCE_ORDINAL,
        ).with_columns(nw.lit(True).alias("__media_present"))
        rows = rows.drop("media", "media_coverage").join(
            grouped, on=("game_id",), cardinality="one_to_one"
        )
        rows = (
            rows.rename({"__media_records": "media"})
            .fill_empty_lists("media")
            .with_columns(
                nw.when(nw.col("__media_present").fill_null(False))
                .then(nw.lit("present"))
                .otherwise(nw.lit("empty"))
                .alias("media_coverage")
            )
        )
    if weather is not None:
        evidence = _checked_game_evidence(
            summaries, weather, label="Game weather", venue=True
        )
        rows = rows.drop("weather", "weather_coverage").enrich(
            evidence,
            on=("game_id",),
            output="weather",
            coverage="weather_coverage",
            fields={name: name for name in GameWeather.model_fields},
            outside="reject",
            completeness="sparse",
            message="Game weather contains duplicate or outside-universe game keys",
        )
    return rows.select(*GameSummary.model_fields).sort("season", "week", "game_id")


@dataset(
    id="cfbd.game_summaries",
    revision=3,
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
) -> RecipeRef[Table]:
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

    requested_media: RecipeRef[Table] | None = None
    if include_media and game_id is not None:
        context: RecipeRef[GameSummary] = require_one(summaries)
        requested_media = select_exact_game_media(
            game_media(
                year=value(context, path=("season",), expected_type=int),
                week=value(context, path=("week",), expected_type=int),
                season_type=value(
                    context,
                    path=("season_type",),
                    expected_type=SeasonType,
                ),
                team=value(context, path=("home_team",), expected_type=str),
                media_type=media_type,
            ),
            game_id=game_id,
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

    requested_weather: RecipeRef[Table] | None = None
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


def _checked_game_evidence(
    base: Table, evidence: Table, *, label: str, venue: bool = False
) -> Table:
    """Require common game context through native comparisons and an ID join."""
    comparison_fields = (
        "season",
        "week",
        "season_type",
        "start_date",
        "home_team",
        "away_team",
        "home_conference",
        "away_conference",
        "venue_id",
        "venue",
    )
    context = base.select(
        "game_id", *(nw.col(name).alias(f"__base_{name}") for name in comparison_fields)
    ).with_columns(nw.lit(True).alias("__base_present"))
    joined = (
        evidence.with_columns(nw.col("id").alias("game_id"))
        .join(context, on=("game_id",), cardinality="many_to_one")
        .require(
            nw.col("__base_present").fill_null(False),
            message=f"{label} fall outside the base row universe",
        )
    )
    predicate = (
        (nw.col("season") == nw.col("__base_season"))
        & (nw.col("week") == nw.col("__base_week"))
        & (nw.col("season_type") == nw.col("__base_season_type"))
        & (nw.col("start_time") == nw.col("__base_start_date"))
    )
    for side in ("home", "away"):
        joined = joined.normalize_text(
            f"{side}_team", into=f"__source_{side}"
        ).normalize_text(f"__base_{side}_team", into=f"__expected_{side}")
        predicate = predicate & (
            nw.col(f"__source_{side}") == nw.col(f"__expected_{side}")
        )
        source = nw.col(f"{side}_conference")
        expected = nw.col(f"__base_{side}_conference")
        predicate = predicate & (
            source.is_null() | expected.is_null() | (source == expected)
        )
    if venue:
        for field in ("venue_id", "venue"):
            predicate = predicate & (
                nw.col(f"__base_{field}").is_null()
                | (nw.col(field) == nw.col(f"__base_{field}"))
            )
    return joined.require(
        predicate, message=f"{label} conflict with the selected game context"
    )


__all__ = [
    "GameEnrichmentCoverage",
    "GameResultState",
    "GameSummary",
    "game_summaries",
]
