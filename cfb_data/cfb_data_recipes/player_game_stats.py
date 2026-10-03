"""Provide the independently authored long-form player-game-stat dataset.

``player_game_stats`` composes ``game_summaries`` with the public nested
``/games/players`` source. The source has no team ID, so each team is resolved
only within its validated game context through the explicit home/away side.
Every athlete statistic remains a display string, including compound values
such as ``7/9``; the recipe never guesses a numeric interpretation.
"""

from __future__ import annotations

from datetime import datetime

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.games.sources import player_game_stats as player_game_stats_source
from pydantic import BaseModel, ConfigDict, Field

from cfb_data_recipes.game_summaries import game_summaries


class PlayerGameStat(BaseModel):
    """Represent one athlete statistic observation in one team/game context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    season_type: SeasonType = Field(json_schema_extra={"semantic_type": "dimension"})
    start_date: datetime = Field(json_schema_extra={"semantic_type": "time"})
    team_id: int = Field(
        ge=0,
        description="Stable team ID resolved from the validated game side.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    team: str = Field(
        description="Source team name retained from the player-stat response.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    classification: Classification | None = Field(
        default=None,
        description="Classification carried by the matching game side.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_away: str = Field(pattern="^(home|away)$")
    team_ordinal: int = Field(
        ge=0,
        le=1,
        description="Zero for the home side and one for the away side.",
    )
    team_points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    athlete_id: str = Field(json_schema_extra={"semantic_type": "identifier"})
    athlete_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    category: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat_type: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat: str = Field(
        description="Source display statistic preserved without numeric coercion.",
        json_schema_extra={"semantic_type": "text"},
    )
    category_ordinal: int = Field(ge=0)
    stat_type_ordinal: int = Field(ge=0)
    athlete_ordinal: int = Field(ge=0)


@step(
    id="cfbd.player_game_stats.flatten",
    revision=2,
    output=PlayerGameStat,
    deterministic=True,
)
def flatten_player_game_stats(summaries: Table, nested: Table) -> Table:
    """Compose native structural explosions and a globally checked context join.

    :param summaries: Validated game context table with stable side IDs.
    :param nested: Validated nested player-statistics table.
    :return: Source-ordered long-form athlete/statistic observations.
    """
    context = summaries.select(
        "game_id",
        "season",
        "week",
        "season_type",
        "start_date",
        "home_id",
        "away_id",
        "home_classification",
        "away_classification",
    ).with_columns(nw.lit(True).alias("__context"))
    context = context.require_unique(
        ("game_id",), message="Game summaries contain a duplicate game ID"
    )
    rows = (
        nested.rename({"id": "game_id"})
        .join(context, on=("game_id",), cardinality="many_to_one")
        .require(
            nw.col("__context").fill_null(False),
            message="Player statistics have no matching game context",
        )
    )
    rows = rows.explode_records(
        "teams",
        fields={
            "team": "team",
            "conference": "conference",
            "home_away": "home_away",
            "points": "team_points",
            "categories": "__categories",
        },
        ordinal="__side",
    )
    rows = rows.explode_records(
        "__categories",
        fields={"name": "category", "types": "__types"},
        ordinal="category_ordinal",
    )
    rows = rows.explode_records(
        "__types",
        fields={"name": "stat_type", "athletes": "__athletes"},
        ordinal="stat_type_ordinal",
    )
    rows = rows.explode_records(
        "__athletes",
        fields={"id": "athlete_id", "name": "athlete_name", "stat": "stat"},
        ordinal="athlete_ordinal",
    )
    home = nw.col("home_away") == "home"
    return (
        rows.with_columns(
            nw.when(home)
            .then(nw.col("home_id"))
            .otherwise(nw.col("away_id"))
            .cast(nw.Int64)
            .alias("team_id"),
            nw.when(home)
            .then(nw.col("home_classification"))
            .otherwise(nw.col("away_classification"))
            .alias("classification"),
            nw.when(home).then(nw.lit(0)).otherwise(nw.lit(1)).alias("team_ordinal"),
        )
        .select(*PlayerGameStat.model_fields)
        .sort(
            "season",
            "week",
            "game_id",
            "team_ordinal",
            "category_ordinal",
            "stat_type_ordinal",
            "athlete_ordinal",
        )
    )


@dataset(
    id="cfbd.player_game_stats",
    revision=2,
    row=PlayerGameStat,
    grain="one athlete statistic observation in one team/game context",
    keys=("game_id", "team_id", "athlete_id", "category", "stat_type"),
    order_by=(
        "season",
        "week",
        "game_id",
        "team_ordinal",
        "category_ordinal",
        "stat_type_ordinal",
        "athlete_ordinal",
    ),
    partition_by=("season",),
    event_time="start_date",
)
def player_game_stats(
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: SeasonType | None = None,
    team: str | None = None,
    conference: str | None = None,
    category: str | None = None,
    game_id: int | None = None,
    classification: Classification | None = None,
) -> RecipeRef[Table]:
    """Build long-form player-game statistic observations.

    :param year: Season year used for grouped retrieval.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param category: Optional source statistic-category selector.
    :param game_id: Optional exact game identifier.
    :param classification: Optional classification selector.
    :return: A reference to the validated long-form dataset.
    """
    summaries = game_summaries(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        classification=classification,
        game_id=game_id,
    )
    nested = player_game_stats_source(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        category=category,
        game_id=game_id,
        classification=classification,
    )
    return flatten_player_game_stats(summaries, nested)


__all__ = ["PlayerGameStat", "player_game_stats"]
