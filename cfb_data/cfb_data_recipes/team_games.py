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

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, concat_tables, dataset, step
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    TeamGameStat,
)
from cfb_data.games.sources import advanced_box_score, team_game_stats
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
from cfb_data.teams.identity import normalize_team_identity_text
from pydantic import BaseModel, ConfigDict, Field

from cfb_data_recipes.game_summaries import (
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
    advanced_box_coverage: TeamStatsCoverage = Field(
        description="Explicit exact-game advanced-box availability."
    )
    advanced_box: AdvancedBoxScore | None = Field(
        default=None,
        description="Complete validated advanced box score when requested.",
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
    revision=2,
    output=TeamGame,
    deterministic=True,
)
def normalize_team_games(
    summaries: Table,
    *,
    statistics: Table | None,
    advanced_box: Table | None,
    advanced_box_game_id: int | None,
    advanced: Table | None,
    havoc: Table | None,
    ppa: Table | None,
    requested_team: str | None,
) -> Table:
    """Expand two native perspectives and join declared game evidence.

    :param summaries: Validated game summaries defining the universe.
    :param statistics: Requested conventional statistics or omitted source.
    :param advanced_box: Requested exact-game box or omitted source.
    :param advanced_box_game_id: Explicit box request identity.
    :param advanced: Requested advanced metrics or omitted source.
    :param havoc: Requested havoc evidence or omitted source.
    :param ppa: Requested PPA evidence or omitted source.
    :param requested_team: Team selector defining required metric perspectives.
    :return: Exactly two globally checked perspectives per game.
    """
    base = concat_tables(
        (_perspective(summaries, home=True), _perspective(summaries, home=False))
    )
    base = _attach_team_stats(base, statistics)
    if advanced_box is None:
        base = base.with_columns(
            nw.lit(None).alias("advanced_box"),
            nw.lit("not_requested").alias("advanced_box_coverage"),
        )
    else:
        base = _attach_advanced_box(
            base, advanced_box, requested_game_id=advanced_box_game_id
        )
    base = base.normalize_text("team", into="__team_key").normalize_text(
        "opponent", into="__opponent_key"
    )
    required = (
        nw.lit(True)
        if requested_team is None
        else nw.col("__team_key") == normalize_team_identity_text(requested_team)
    )
    base = base.with_columns(required.cast(nw.Boolean).alias("__required"))
    if requested_team is not None and any(
        source is not None for source in (advanced, havoc, ppa)
    ):
        selected = base.aggregate(
            keys=("game_id",),
            expressions=(nw.col("__required").sum().alias("__required_count"),),
        ).require(
            nw.col("__required_count") == 1,
            message="Requested team enrichment cannot be resolved within every game",
        )
        base = base.join(selected, on=("game_id",), cardinality="many_to_one")
    context = base.select(
        "game_id",
        "__team_key",
        "season",
        "week",
        "season_type",
        "__opponent_key",
        "conference",
        "opponent_conference",
    )
    for prefix, source, model in (
        ("advanced_stats", advanced, AdvancedGameStat),
        ("havoc", havoc, GameHavocStats),
        ("ppa", ppa, TeamGamePredictedPointsAdded),
    ):
        base = _attach_named_metrics(
            base, source, context=context, prefix=prefix, model=model
        )
    return base.select(*TeamGame.model_fields).sort(
        "season", "week", "game_id", "perspective_ordinal"
    )


@dataset(
    id="cfbd.team_games",
    revision=2,
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
    include_advanced_box: bool = False,
    include_advanced_stats: bool = False,
    include_havoc: bool = False,
    include_ppa: bool = False,
    exclude_garbage_time: bool | None = None,
) -> RecipeRef[Table]:
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
    :param include_advanced_box: Request the exact-game nested advanced box score.
    :param include_advanced_stats: Request advanced team-game statistics.
    :param include_havoc: Request team-game havoc statistics.
    :param include_ppa: Request team-game predicted-points-added metrics.
    :param exclude_garbage_time: Optional source policy for advanced stats and PPA.
    :return: A reference to the validated team-game dataset.
    :raises ValueError: If an enrichment lacks its required bounded selector.
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
    if include_advanced_box and game_id is None:
        raise ValueError("Advanced box enrichment requires an exact game ID")
    box = (
        advanced_box_score(game_id=game_id)
        if include_advanced_box and game_id is not None
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
        advanced_box=box,
        advanced_box_game_id=game_id,
        advanced=advanced,
        havoc=havoc,
        ppa=ppa,
        requested_team=team,
    )


def _perspective(summaries: Table, *, home: bool) -> Table:
    """Project one side with result calculations gated by proven scores."""
    side, opponent = ("home", "away") if home else ("away", "home")
    proven = ~nw.col("result_state").is_null()
    result = (
        nw.when(~proven)
        .then(nw.lit(None))
        .when(nw.col("result_state") == "tie")
        .then(nw.lit("tie"))
        .when(nw.col("winner_id") == nw.col(f"{side}_id"))
        .then(nw.lit("win"))
        .otherwise(nw.lit("loss"))
    )
    common = (
        "game_id",
        "season",
        "week",
        "season_type",
        "start_date",
        "completed",
        "neutral_site",
        "conference_game",
        "venue_id",
        "venue",
        "total_points",
        "margin",
    )
    return summaries.select(
        *common,
        nw.col(f"{side}_id").alias("team_id"),
        nw.col(f"{side}_team").alias("team"),
        nw.col(f"{side}_conference").alias("conference"),
        nw.col(f"{side}_classification").alias("classification"),
        nw.col(f"{opponent}_id").alias("opponent_id"),
        nw.col(f"{opponent}_team").alias("opponent"),
        nw.col(f"{opponent}_conference").alias("opponent_conference"),
        nw.col(f"{opponent}_classification").alias("opponent_classification"),
        nw.col(f"{side}_points").alias("points"),
        nw.col(f"{opponent}_points").alias("opponent_points"),
        nw.lit(side).alias("home_away"),
        nw.lit(0 if home else 1).alias("perspective_ordinal"),
        result.alias("result"),
        nw.when(proven)
        .then(nw.col(f"{side}_points") - nw.col(f"{opponent}_points"))
        .otherwise(nw.lit(None))
        .alias("point_differential"),
    )


def _attach_team_stats(base: Table, source: Table | None) -> Table:
    """Require both stable team-side keys and preserve ordered source lists."""
    if source is None:
        return base.with_columns(
            nw.lit(None).alias("team_stats"),
            nw.lit("not_requested").alias("team_stats_coverage"),
        )
    keys = ("game_id", "team_id")
    expanded = (
        source.rename({"id": "game_id"})
        .explode_records(
            "teams",
            fields={
                "team_id": "team_id",
                "home_away": "__source_side",
                "stats": "team_stats",
            },
            ordinal="__team_position",
            dtypes={"team_id": "int64"},
        )
        .require_unique(
            keys, message="Team statistics contain duplicate game/team keys"
        )
    )
    expanded = (
        expanded.list_lengths({"team_stats": "__stat_count"})
        .with_columns(nw.lit(True).alias("__stats_match"))
        .select(*keys, "__source_side", "team_stats", "__stat_count", "__stats_match")
    )
    joined = (
        base.join(expanded, on=keys, cardinality="one_to_one")
        .require(
            nw.col("__stats_match").fill_null(False),
            message="Requested team statistics are incomplete",
        )
        .require(
            nw.col("home_away") == nw.col("__source_side"),
            message="Team statistics conflict with game-side identity",
        )
    )
    return joined.with_columns(
        nw.when(nw.col("__stat_count") > 0)
        .then(nw.lit("present"))
        .otherwise(nw.lit("empty"))
        .alias("team_stats_coverage")
    )


def _attach_advanced_box(
    base: Table, source: Table, *, requested_game_id: int | None
) -> Table:
    """Broadcast one exact-game box after global cardinality and context checks."""
    if requested_game_id is None:
        raise ValueError("Advanced box enrichment requires an exact game ID")
    size = Table(source.frame.select(nw.len().alias("__box_count"))).require(
        nw.col("__box_count") == 1,
        message="Advanced box enrichment requires exactly one response",
    )
    base_size = Table(base.frame.select(nw.len().alias("__base_count"))).require(
        nw.col("__base_count") == 2,
        message="Advanced box enrichment requires one two-perspective game",
    )
    base = base.require(
        nw.col("game_id") == requested_game_id,
        message="Advanced box game identity conflicts",
    )
    packed = (
        source.pack(
            columns={name: name for name in AdvancedBoxScore.model_fields},
            into="advanced_box",
        )
        .nested(
            "game_info",
            fields={
                "home_team": "__box_home",
                "away_team": "__box_away",
                "home_points": "__box_home_points",
                "away_points": "__box_away_points",
            },
        )
        .normalize_text("__box_home", into="__home_key")
        .normalize_text("__box_away", into="__away_key")
        .with_columns(nw.lit(requested_game_id).alias("game_id"))
        .select(
            "game_id",
            "advanced_box",
            "__home_key",
            "__away_key",
            "__box_home_points",
            "__box_away_points",
        )
    )
    joined = (
        base.join(packed, on=("game_id",), cardinality="many_to_one")
        .join(size, how="cross", cardinality="many_to_many")
        .join(base_size, how="cross", cardinality="many_to_many")
        .normalize_text("team", into="__box_team_key")
    )
    home = nw.col("home_away") == "home"
    name = nw.when(home).then(nw.col("__home_key")).otherwise(nw.col("__away_key"))
    points = (
        nw.when(home)
        .then(nw.col("__box_home_points"))
        .otherwise(nw.col("__box_away_points"))
    )
    return joined.require(
        (nw.col("__box_team_key") == name)
        & (nw.col("points").is_null() | (nw.col("points") == points)),
        message="Advanced box score conflicts with the selected game",
    ).with_columns(nw.lit("present").alias("advanced_box_coverage"))


def _attach_named_metrics(
    base: Table,
    source: Table | None,
    *,
    context: Table,
    prefix: str,
    model: type[BaseModel],
) -> Table:
    """Apply explicit game/opponent/conference matching with sparse coverage."""
    keys = ("game_id", "__team_key")
    output = f"__{prefix}_payload"
    coverage = f"{prefix}_coverage"
    if source is not None:
        source_context = context.select(
            *keys,
            *(
                nw.col(name).alias(f"__expected_{name}")
                for name in (
                    "season",
                    "week",
                    "season_type",
                    "__opponent_key",
                    "conference",
                    "opponent_conference",
                )
            ),
        ).with_columns(nw.lit(True).alias("__game_match"))
        source = (
            source.normalize_text("team", into="__team_key")
            .normalize_text("opponent", into="__source_opponent")
            .join(source_context, on=keys, cardinality="many_to_one")
        )
        predicate = nw.col("__game_match").fill_null(False) & (
            nw.col("__source_opponent") == nw.col("__expected___opponent_key")
        )
        for name in ("season", "week", "season_type"):
            predicate = predicate & (nw.col(name) == nw.col(f"__expected_{name}"))
        for name in ("conference", "opponent_conference"):
            if name in model.model_fields:
                predicate = predicate & (
                    nw.col(f"__expected_{name}").is_null()
                    | (nw.col(name) == nw.col(f"__expected_{name}"))
                )
        source = source.require(
            predicate, message=f"{prefix} conflicts with the selected game context"
        )
    joined = base.enrich(
        source,
        on=keys,
        output=output,
        coverage=coverage,
        fields={"offense": "offense", "defense": "defense"},
        message=f"{prefix} contains duplicate or outside game/team keys",
    )
    if source is not None:
        size = Table(source.frame.select(nw.len().alias("__source_size")))
        joined = joined.join(size, how="cross", cardinality="many_to_many").require(
            (nw.col("__source_size") == 0)
            | (nw.col("__required") == nw.lit(False))
            | (nw.col(coverage) == "present"),
            message=f"Requested {prefix} is incomplete",
        )
        joined = joined.with_columns(
            nw.when(
                (nw.col(coverage) == "empty") & (nw.col("__required") == nw.lit(False))
            )
            .then(nw.lit("not_requested"))
            .otherwise(nw.col(coverage))
            .alias(coverage)
        ).drop("__source_size")
    destination = "advanced" if prefix == "advanced_stats" else prefix
    return joined.nested(
        output,
        fields={
            "offense": f"{destination}_offense",
            "defense": f"{destination}_defense",
        },
    )


__all__ = ["TeamGame", "TeamGameResult", "TeamStatsCoverage", "team_games"]
