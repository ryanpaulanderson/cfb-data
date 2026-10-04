"""Calculate turnover-aware college Success Rate from raw historical plays.

The workflow exposes play evidence and both game and season products. Rates
divide successful evaluated plays by evaluated plays; unknown evidence is
separate and never becomes failure, success or a silently complete denominator.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, concat_tables, dataset, step, workflow
from cfb_data.enums import Classification, SeasonType
from pydantic import BaseModel, ConfigDict

from .scrimmage_plays import (
    MetricCoverage,
    TeamUnit,
    scrimmage_plays,
    validate_partitions,
)
from .team_games import team_games


class SuccessSplit(StrEnum):
    """Describe the all-play, rushing or dropback summary population."""

    all = "all"
    rush = "rush"
    dropback = "dropback"


class SuccessCounts(BaseModel):
    """Expose counts, rate and evidence for one team/unit/split population."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    season: int
    team_id: int
    team: str
    unit: TeamUnit
    split: SuccessSplit
    source_rows: int
    evaluated_plays: int
    unknown_plays: int
    excluded_plays: int
    eligible_plays: int
    successful_plays: int
    unallocated_unknown_plays: int
    success_rate: float | None
    coverage: MetricCoverage


class GameSuccessRate(SuccessCounts):
    """Expose one game-scoped Success Rate or defensive rate allowed."""

    game_id: int
    week: int
    completed: bool


class SeasonSuccessRate(SuccessCounts):
    """Expose a season rate calculated from pooled counts, not game averages."""

    games: int
    unavailable_games: int


class SuccessRateRefs(TypedDict):
    """Declare the workflow's explicit play, game and season outputs."""

    plays: RecipeRef[Table]
    team_games: RecipeRef[Table]
    team_seasons: RecipeRef[Table]


def _summarize_counts(rows: Table) -> Table:
    """Derive nullable ratios and coverage from explicit population counts."""
    return rows.with_columns(
        (nw.col("evaluated_plays") + nw.col("unknown_plays")).alias("eligible_plays"),
        nw.when(nw.col("evaluated_plays") > 0)
        .then(nw.col("successful_plays") / nw.col("evaluated_plays"))
        .otherwise(nw.lit(None))
        .alias("success_rate"),
        nw.when(nw.col("__source_available") == 0)
        .then(nw.lit("unavailable"))
        .when(
            (nw.col("unknown_plays") > 0)
            | (nw.col("unallocated_unknown_plays") > 0)
            | (nw.col("__unavailable_games") > 0)
        )
        .then(nw.lit("partial"))
        .when(nw.col("evaluated_plays") == 0)
        .then(nw.lit("empty"))
        .otherwise(nw.lit("present"))
        .alias("coverage"),
    ).require(
        (nw.col("successful_plays") <= nw.col("evaluated_plays"))
        & (
            nw.col("source_rows")
            == nw.col("evaluated_plays")
            + nw.col("unknown_plays")
            + nw.col("excluded_plays")
        ),
        message="Success Rate populations do not reconcile",
    )


@step(id="cfbd.success_rate.game_counts", revision=1, output=GameSuccessRate)
def game_success_counts(
    features: Table, games: Table, *, weeks: tuple[int, ...]
) -> Table:
    """Aggregate native success evidence onto the declared team-game universe.

    :param features: Shared validated play features, including exclusions.
    :param games: Authoritative two-perspective games without advanced enrichment.
    :param weeks: Explicit source weeks defining the result universe.
    :return: Game/unit/split counts, nullable rates and coverage.
    """
    long: list[Table] = []
    universes: list[Table] = []
    selected_games = games.filter(nw.col("week").is_in(weeks))
    for unit, identity, display in (
        ("offense", "offense_id", "offense"),
        ("defense", "defense_id", "defense"),
    ):
        side = features.with_columns(
            nw.col(identity).alias("team_id"),
            nw.col(display).alias("team"),
            nw.lit(unit).alias("unit"),
        )
        for split in ("all", "rush", "dropback"):
            population = (
                side if split == "all" else side.filter(nw.col("play_family") == split)
            )
            long.append(
                population.with_columns(nw.lit(split).alias("split")).select(
                    "game_id",
                    "team_id",
                    "unit",
                    "split",
                    "success_status",
                    "successful",
                )
            )
            universes.append(
                selected_games.select(
                    "season", "team_id", "team", "game_id", "week", "completed"
                ).with_columns(nw.lit(unit).alias("unit"), nw.lit(split).alias("split"))
            )
    counts = (
        concat_tables(long)
        .with_columns(
            (nw.col("success_status") == "evaluated")
            .cast(nw.Int64)
            .alias("__evaluated"),
            (nw.col("success_status") == "unknown").cast(nw.Int64).alias("__unknown"),
            (nw.col("success_status") == "excluded").cast(nw.Int64).alias("__excluded"),
            nw.col("successful").fill_null(False).cast(nw.Int64).alias("__successful"),
        )
        .aggregate(
            keys=("game_id", "team_id", "unit", "split"),
            expressions=(
                nw.len().alias("source_rows"),
                nw.col("__evaluated").sum().alias("evaluated_plays"),
                nw.col("__unknown").sum().alias("unknown_plays"),
                nw.col("__excluded").sum().alias("excluded_plays"),
                nw.col("__successful").sum().alias("successful_plays"),
            ),
        )
    )
    evidence: list[Table] = []
    for unit, identity in (("offense", "offense_id"), ("defense", "defense_id")):
        evidence.append(
            features.with_columns(
                nw.col(identity).alias("team_id"),
                nw.lit(unit).alias("unit"),
                (
                    (nw.col("play_family") == "unknown")
                    & (nw.col("success_status") == "unknown")
                )
                .cast(nw.Int64)
                .alias("__unallocated"),
            ).aggregate(
                keys=("game_id", "team_id", "unit"),
                expressions=(
                    nw.len().alias("__source_available"),
                    nw.col("__unallocated").sum().alias("unallocated_unknown_plays"),
                ),
            )
        )
    result = (
        concat_tables(universes)
        .join(
            counts, on=("game_id", "team_id", "unit", "split"), cardinality="one_to_one"
        )
        .join(
            concat_tables(evidence),
            on=("game_id", "team_id", "unit"),
            cardinality="many_to_one",
        )
    )
    count_columns = (
        "source_rows",
        "evaluated_plays",
        "unknown_plays",
        "excluded_plays",
        "successful_plays",
        "unallocated_unknown_plays",
        "__source_available",
    )
    result = result.with_columns(
        *(
            nw.col(name).fill_null(0).cast(nw.Int64).alias(name)
            for name in count_columns
        ),
        nw.lit(0).alias("__unavailable_games"),
    )
    return (
        _summarize_counts(result)
        .select(*GameSuccessRate.model_fields)
        .sort("season", "game_id", "team_id", "unit", "split")
    )


@step(id="cfbd.success_rate.season_counts", revision=1, output=SeasonSuccessRate)
def season_success_counts(games: Table) -> Table:
    """Pool evaluated numerators and denominators across selected games.

    :param games: Validated game/unit/split Success Rate products.
    :return: Season/unit/split products preserving unavailable-game counts.
    """
    columns = (
        "source_rows",
        "evaluated_plays",
        "unknown_plays",
        "excluded_plays",
        "successful_plays",
        "unallocated_unknown_plays",
    )
    result = (
        games.with_columns(
            (nw.col("coverage") == "unavailable").cast(nw.Int64).alias("__unavailable"),
            (nw.col("coverage") != "unavailable").cast(nw.Int64).alias("__available"),
        )
        .aggregate(
            keys=("season", "team_id", "team", "unit", "split"),
            expressions=(
                *(nw.col(name).sum().alias(name) for name in columns),
                nw.len().alias("games"),
                nw.col("__unavailable").sum().alias("unavailable_games"),
                nw.col("__available").sum().alias("__source_available"),
            ),
        )
        .with_columns(nw.col("unavailable_games").alias("__unavailable_games"))
    )
    return (
        _summarize_counts(result)
        .select(*SeasonSuccessRate.model_fields)
        .sort("season", "team_id", "unit", "split")
    )


@dataset(
    id="cfbd.success_rate.team_games",
    revision=1,
    row=GameSuccessRate,
    grain="one team/game/unit/play-family Success Rate",
    keys=("game_id", "team_id", "unit", "split"),
    order_by=("season", "game_id", "team_id", "unit", "split"),
    partition_by=("season",),
)
def team_game_success_rate(
    *, features: RecipeRef[Table], games: RecipeRef[Table], weeks: tuple[int, ...]
) -> RecipeRef[Table]:
    """Build the explicit game-level analytical product.

    :param features: Shared play-feature reference.
    :param games: Authoritative game-participant reference.
    :param weeks: Selected source partitions.
    :return: A native game summary reference.
    """
    return game_success_counts(features, games, weeks=weeks)


@dataset(
    id="cfbd.success_rate.team_seasons",
    revision=1,
    row=SeasonSuccessRate,
    grain="one team/season/unit/play-family pooled Success Rate",
    keys=("season", "team_id", "unit", "split"),
    order_by=("season", "team_id", "unit", "split"),
    partition_by=("season",),
)
def team_season_success_rate(*, games: RecipeRef[Table]) -> RecipeRef[Table]:
    """Build the explicit pooled season analytical product.

    :param games: Game-level Success Rate reference.
    :return: A native season summary reference.
    """
    return season_success_counts(games)


@workflow(id="cfbd.success_rate", revision=1)
def success_rate(
    *,
    year: int,
    weeks: tuple[int, ...],
    team: str | None = None,
    season_type: SeasonType = SeasonType.regular,
    classification: Classification | None = None,
) -> SuccessRateRefs:
    """Calculate college Success Rate with named play, game and season evidence.

    :param year: Season year.
    :param weeks: Explicit unique source weeks.
    :param team: Optional participating team; both game participants remain visible.
    :param season_type: Selected source season phase.
    :param classification: Optional source classification selector.
    :return: Named play evidence, game summaries and pooled season summaries.
    :raises cfb_data.analytics.CFBDRecipeCompilationError: If source partitions are invalid.
    """
    validate_partitions(year, weeks)
    features = scrimmage_plays(
        year=year,
        weeks=weeks,
        team=team,
        season_type=season_type,
        classification=classification,
    )
    games = team_games(
        year=year, team=team, season_type=season_type, classification=classification
    )
    summaries = team_game_success_rate(features=features, games=games, weeks=weeks)
    return {
        "plays": features,
        "team_games": summaries,
        "team_seasons": team_season_success_rate(games=summaries),
    }


__all__ = [
    "GameSuccessRate",
    "SeasonSuccessRate",
    "SuccessRateRefs",
    "success_rate",
    "team_game_success_rate",
    "team_season_success_rate",
]
