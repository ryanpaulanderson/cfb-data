"""Estimate college Adjusted Line Yards jointly across opponents and situations.

Raw plays supply all observations. Native table reductions build constrained
ridge equations; the engine collects only bounded coefficient statistics.
Team ratings use a common weighted rushing-YPC baseline. They are our college
all-carrier variant, not a reproduction of a vendor's proprietary ALY model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, TypedDict

import narwhals.stable.v2 as nw
import pandas as pd
from cfb_data.analytics import RecipeRef, Table, concat_tables, dataset, step, workflow
from cfb_data.analytics.modeling import (
    BlockPenalty,
    DesignTerm,
    EffectObservation,
    ModelCoefficient,
    ModelStatistic,
    additive_cluster_uncertainty,
    additive_statistics,
    categorical_design,
    cluster_score_statistics,
    fit_additive_model,
    predict_additive_model,
)
from cfb_data.enums import Classification, SeasonType
from pydantic import BaseModel, ConfigDict, Field

from .scrimmage_plays import (
    MetricCoverage,
    ScrimmagePlay,
    TeamUnit,
    scrimmage_plays,
    validate_partitions,
)
from .team_games import team_games

_FEATURE_REVISION: Final = 1
_TERMS: Final = (
    DesignTerm(block="offense", column="offense_id"),
    DesignTerm(block="defense", column="defense_id", multiplier=-1),
    DesignTerm(block="situation", column="situation"),
    DesignTerm(block="quarter", column="period"),
    DesignTerm(block="clock", column="clock_band"),
    DesignTerm(block="venue", column="venue_perspective"),
    DesignTerm(block="score_time", column="score_time"),
)


class ALYParameters(BaseModel):
    """Declare frozen penalties in weighted-observation units and optional decay.

    A penalty of ``k`` adds ``k`` to the relevant normal-equation diagonal.
    The half-life is measured in calendar days relative to the latest training
    game. Passing this object selects it explicitly without retrospective tuning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    team_penalty: float = Field(gt=0, allow_inf_nan=False)
    context_penalty: float = Field(gt=0, allow_inf_nan=False)
    half_life_days: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class CalibrationPolicy(StrEnum):
    """Identify explicit parameters or forward-week model selection."""

    explicit = "explicit"
    rolling = "rolling"


class RushObservation(ScrimmagePlay):
    """Declare a fully typed evaluated rush and its versioned model context."""

    observation_id: str
    cluster_id: str
    response: float
    weight: float
    situation: str
    clock_band: str
    score_time: str
    weighted_yards: float
    weighted_line: float


class ALYCalibration(BaseModel):
    """Expose candidate validation evidence without gathering validation plays."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: int
    team_penalty: float
    context_penalty: float
    half_life_days: float | None
    policy: CalibrationPolicy
    folds: int
    evaluated_plays: int
    unsupported_plays: int
    squared_error: float
    mean_squared_error: float | None
    selected: bool


class _FoldScore(BaseModel):
    """Carry one bounded forward-validation reduction."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: int
    folds: int
    evaluated_plays: int
    unsupported_plays: int
    squared_error: float


class ALYModel(ModelCoefficient):
    """Expose frozen selected coefficients and their complete fitting identity."""

    season: int
    training_last_week: int
    feature_revision: int
    candidate_id: int
    team_penalty: float
    context_penalty: float
    half_life_days: float | None
    policy: CalibrationPolicy
    mean_squared_error: float | None
    weighted_raw_yards_per_rush: float
    weighted_raw_line_yards_per_rush: float
    cluster_standard_error: float | None
    uses_earlier_team_prior: bool


class TeamLineYards(BaseModel):
    """Expose observed rushing populations and normalized team strength.

    Defensive ``effect`` is prevention: larger is stronger. Defensive
    ``adjusted_line_yards`` is allowed yardage: smaller is stronger. Standard
    errors describe the effect conditional on chosen penalties and team priors,
    not uncertainty in the baseline or hyperparameter selection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    season: int
    team_id: int
    team: str
    unit: TeamUnit
    games: int
    unavailable_games: int
    source_rows: int
    evaluated_rushes: int
    unknown_plays: int
    excluded_plays: int
    unknown_score_rushes: int
    unknown_clock_rushes: int
    raw_yards_per_rush: float | None
    raw_line_yards_per_rush: float | None
    adjusted_line_yards: float | None
    effect: float | None
    cluster_standard_error: float | None
    weighted_raw_yards_per_rush: float | None
    data_rank: int | None
    parameter_count: int | None
    constraint_count: int | None
    prior_dependent: bool | None
    coverage: MetricCoverage


class LineYardsRefs(TypedDict):
    """Name the evidence, calibration, frozen model and team products."""

    plays: RecipeRef[Table]
    calibration: RecipeRef[Table]
    model: RecipeRef[Table]
    team_seasons: RecipeRef[Table]


@step(id="cfbd.line_yards.observations", revision=1, output=RushObservation)
def rush_observations(
    features: Table,
    *,
    last_week: int,
    holdout_week: int | None = None,
    parameters: ALYParameters,
) -> Table:
    """Create versioned rush context and calendar-decayed training observations.

    :param features: Shared unfiltered play evidence for the declared population.
    :param last_week: Last included training week.
    :param holdout_week: Optional validation week; train before its earliest game.
    :param parameters: Frozen candidate controlling calendar-day weights.
    :return: One evaluated rush per observation with explicit unknown context.
    """
    rows = features.filter(
        (nw.col("rush_status") == "evaluated") & (nw.col("week") <= last_week)
    ).with_columns(nw.col("start_date").dt.timestamp("ms").alias("__time"))
    if holdout_week is not None:
        cutoff = (
            features.filter(nw.col("week") == holdout_week)
            .with_columns(
                nw.col("start_date").dt.timestamp("ms").alias("__cutoff_time")
            )
            .select(nw.col("__cutoff_time").min().alias("__cutoff"))
        )
        rows = rows.join(cutoff, how="cross").filter(
            nw.col("__time") < nw.col("__cutoff")
        )
    if parameters.half_life_days is None:
        rows = rows.with_columns(nw.lit(1.0).alias("weight"))
    else:
        anchor = rows.select(nw.col("__time").max().alias("__anchor"))
        rows = rows.join(anchor, how="cross").with_columns(
            (
                nw.lit(2.0)
                ** (
                    (nw.col("__time") - nw.col("__anchor"))
                    / (86400000 * parameters.half_life_days)
                )
            ).alias("weight")
        )
    distance = (
        nw.when(nw.col("distance") <= 2)
        .then(nw.lit("1-2"))
        .when(nw.col("distance") <= 5)
        .then(nw.lit("3-5"))
        .when(nw.col("distance") <= 10)
        .then(nw.lit("6-10"))
        .when(nw.col("distance") <= 15)
        .then(nw.lit("11-15"))
        .otherwise(nw.lit("16+"))
    )
    field = (
        nw.when(nw.col("yards_to_goal") <= 5)
        .then(nw.lit("1-5"))
        .when(nw.col("yards_to_goal") <= 10)
        .then(nw.lit("6-10"))
        .when(nw.col("yards_to_goal") <= 20)
        .then(nw.lit("11-20"))
        .when(nw.col("yards_to_goal") <= 50)
        .then(nw.lit("21-50"))
        .when(nw.col("yards_to_goal") <= 80)
        .then(nw.lit("51-80"))
        .otherwise(nw.lit("81-99"))
    )
    clock = (
        nw.when(nw.col("clock_seconds").is_null())
        .then(nw.lit("unknown"))
        .when(nw.col("period").is_in((2, 4)) & (nw.col("clock_seconds") <= 120))
        .then(nw.lit("late_half"))
        .otherwise(nw.lit("ordinary"))
    )
    score = (
        nw.when(nw.col("preplay_score_margin").is_null())
        .then(nw.lit("unknown"))
        .when(nw.col("preplay_score_margin") < -14)
        .then(nw.lit("trailing_15+"))
        .when(nw.col("preplay_score_margin") < -7)
        .then(nw.lit("trailing_8-14"))
        .when(nw.col("preplay_score_margin") < 0)
        .then(nw.lit("trailing_1-7"))
        .when(nw.col("preplay_score_margin") == 0)
        .then(nw.lit("tied"))
        .when(nw.col("preplay_score_margin") <= 7)
        .then(nw.lit("leading_1-7"))
        .when(nw.col("preplay_score_margin") <= 14)
        .then(nw.lit("leading_8-14"))
        .otherwise(nw.lit("leading_15+"))
    )
    return (
        rows.with_columns(
            nw.concat_str(
                nw.col("game_id").cast(nw.String), nw.col("play_id"), separator=":"
            ).alias("observation_id"),
            nw.col("game_id").cast(nw.String).alias("cluster_id"),
            nw.col("line_yards").alias("response"),
            nw.concat_str(
                nw.col("down").cast(nw.String), distance, field, separator=":"
            ).alias("situation"),
            clock.alias("clock_band"),
            nw.concat_str(
                score, nw.col("period").cast(nw.String), clock, separator=":"
            ).alias("score_time"),
        )
        .with_columns(
            (nw.col("weight") * nw.col("yards_gained")).alias("weighted_yards"),
            (nw.col("weight") * nw.col("response")).alias("weighted_line"),
        )
        .select(*RushObservation.model_fields)
        .sort("observation_id")
    )


@step(id="cfbd.line_yards.prior", revision=1, output=ModelCoefficient)
def earlier_team_prior(model: Table, *, year: int) -> Table:
    """Validate historical prior identity and retain only team effects.

    :param model: An earlier frozen ALY model from this feature revision.
    :param year: Target season; same-season and future models are rejected.
    :return: Earlier team effect means, recentered by the shared fitting step.
    """
    return (
        model.require(
            (nw.col("season") < year)
            & (nw.col("feature_revision") == _FEATURE_REVISION),
            message="ALY prior must precede the target season and match its feature revision",
        )
        .filter(nw.col("block").is_in(("offense", "defense")))
        .select(*ModelCoefficient.model_fields)
    )


@step(id="cfbd.line_yards.fold_score", revision=1, output=_FoldScore)
def fold_score(predictions: Table, *, candidate_id: int) -> Table:
    """Reduce held-out squared error and unsupported-level evidence natively.

    :param predictions: Predictions from strictly earlier training games.
    :param candidate_id: Stable candidate ordinal defining deterministic ties.
    :return: One scalar fold summary; no evaluated observations means no support.
    """
    rows = predictions.with_columns(
        (~nw.col("prediction").is_null()).cast(nw.Int64).alias("__evaluated"),
        (nw.col("unsupported_levels") > 0).cast(nw.Int64).alias("__unsupported"),
        (nw.col("residual").fill_null(0) ** 2).alias("__squared_error"),
    ).select(
        nw.col("__evaluated").sum().alias("evaluated_plays"),
        nw.col("__unsupported").sum().alias("unsupported_plays"),
        nw.col("__squared_error").sum().alias("squared_error"),
    )
    return rows.with_columns(
        nw.lit(candidate_id).alias("candidate_id"),
        (nw.col("evaluated_plays") > 0).cast(nw.Int64).alias("folds"),
    ).select(*_FoldScore.model_fields)


@step(id="cfbd.line_yards.calibrate", revision=1, output=ALYCalibration)
def calibrate(
    scores: tuple[Table, ...] | None,
    *,
    candidates: tuple[ALYParameters, ...],
    explicit: bool,
) -> Table:
    """Choose the lowest pooled forward-week prediction error with stable ties.

    :param scores: Bounded per-fold native reductions; empty for explicit policy.
    :param candidates: Finite declared candidate configurations.
    :param explicit: Whether the caller froze exactly one configuration.
    :return: Every candidate and selection evidence; no support selects none.
    """
    configs = pd.DataFrame(
        [
            {
                "candidate_id": index,
                **candidate.model_dump(),
                "policy": "explicit" if explicit else "rolling",
            }
            for index, candidate in enumerate(candidates)
        ]
    )
    configs["half_life_days"] = configs["half_life_days"].astype("Float64")
    rows = Table.from_pandas(configs)
    if explicit:
        rows = rows.with_columns(
            nw.lit(0).alias("folds"),
            nw.lit(0).alias("evaluated_plays"),
            nw.lit(0).alias("unsupported_plays"),
            nw.lit(0.0).alias("squared_error"),
            nw.lit(None, dtype=nw.Float64).alias("mean_squared_error"),
            nw.lit(True).alias("selected"),
        )
    else:
        if not scores:
            raise ValueError("Rolling calibration requires declared fold scores")
        totals = concat_tables(scores).aggregate(
            keys=("candidate_id",),
            expressions=tuple(
                nw.col(name).sum().alias(name)
                for name in (
                    "folds",
                    "evaluated_plays",
                    "unsupported_plays",
                    "squared_error",
                )
            ),
        )
        rows = rows.join(
            totals, on=("candidate_id",), cardinality="one_to_one"
        ).with_columns(
            nw.when(nw.col("evaluated_plays") > 0)
            .then(nw.col("squared_error") / nw.col("evaluated_plays"))
            .otherwise(nw.lit(None, dtype=nw.Float64))
            .cast(nw.Float64)
            .alias("mean_squared_error")
        )
        chosen = (
            rows.filter(nw.col("evaluated_plays") > 0)
            .sort("mean_squared_error", "candidate_id")
            .with_row_index("__rank")
            .filter(nw.col("__rank") == 0)
            .select("candidate_id")
            .with_columns(nw.lit(True).alias("selected"))
        )
        rows = rows.join(
            chosen, on=("candidate_id",), cardinality="one_to_one"
        ).with_columns(nw.col("selected").fill_null(False).cast(nw.Boolean))
    return rows.select(*ALYCalibration.model_fields).sort("candidate_id")


def _select_candidate(tables: tuple[Table, ...], calibration: Table) -> Table:
    """Select one native candidate relation without observing play rows in Python.

    :param tables: Candidate tables in stable calibration ordinal order.
    :param calibration: Declared candidate selection evidence.
    :return: The selected native table or a typed empty relation when unsupported.
    """
    tagged = concat_tables(
        tuple(
            table.with_columns(nw.lit(index).alias("__candidate"))
            for index, table in enumerate(tables)
        )
    )
    selected = calibration.filter(nw.col("selected").cast(nw.Boolean)).select(
        nw.col("candidate_id").alias("__candidate")
    )
    return tagged.join(
        selected, on=("__candidate",), how="inner", cardinality="many_to_one"
    ).drop("__candidate")


@step(id="cfbd.line_yards.select_observations", revision=1, output=RushObservation)
def select_observations(tables: tuple[Table, ...], calibration: Table) -> Table:
    """Select the calibrated native rush population.

    :param tables: Candidate rushing observations.
    :param calibration: Explicit parameter selection evidence.
    :return: Selected observations with their declared schema.
    """
    return _select_candidate(tables, calibration)


@step(id="cfbd.line_yards.select_design", revision=1, output=EffectObservation)
def select_design(tables: tuple[Table, ...], calibration: Table) -> Table:
    """Select the calibrated native design contributions.

    :param tables: Candidate categorical designs.
    :param calibration: Explicit parameter selection evidence.
    :return: Selected signed contributions with their declared schema.
    """
    return _select_candidate(tables, calibration)


@step(id="cfbd.line_yards.select_statistics", revision=1, output=ModelStatistic)
def select_statistics(tables: tuple[Table, ...], calibration: Table) -> Table:
    """Select the calibrated native sufficient statistics.

    :param tables: Candidate coefficient reductions.
    :param calibration: Explicit parameter selection evidence.
    :return: Selected normal equations with their declared schema.
    """
    return _select_candidate(tables, calibration)


@step(id="cfbd.line_yards.select_coefficients", revision=1, output=ModelCoefficient)
def select_coefficients(tables: tuple[Table, ...], calibration: Table) -> Table:
    """Select the calibrated centered coefficient relation.

    :param tables: Candidate fitted models.
    :param calibration: Explicit parameter selection evidence.
    :return: Selected coefficients with their declared schema.
    """
    return _select_candidate(tables, calibration)


@step(id="cfbd.line_yards.publish_model", revision=1, output=ALYModel)
def publish_model(
    coefficients: Table,
    observations: Table,
    uncertainty: Table,
    calibration: Table,
    *,
    year: int,
    last_week: int,
    uses_prior: bool,
) -> Table:
    """Attach selected parameters, normalization and cluster evidence to the fit.

    :param coefficients: Selected centered offense/defense/context coefficients.
    :param observations: The exact selected weighted training rushes.
    :param uncertainty: Conditional game-cluster coefficient uncertainty.
    :param calibration: Visible candidate evidence including the selected row.
    :param year: Season identity.
    :param last_week: Last source week admitted to the final fit.
    :param uses_prior: Whether an earlier-season team prior was requested.
    :return: Frozen coefficient product suitable for later-season prior references.
    """
    baseline = (
        observations.select(
            nw.col("weighted_yards").sum().alias("__yards"),
            nw.col("weighted_line").sum().alias("__line"),
            nw.col("weight").sum().alias("__weight"),
        )
        .with_columns(
            (nw.col("__yards") / nw.col("__weight")).alias(
                "weighted_raw_yards_per_rush"
            ),
            (nw.col("__line") / nw.col("__weight")).alias(
                "weighted_raw_line_yards_per_rush"
            ),
        )
        .select("weighted_raw_yards_per_rush", "weighted_raw_line_yards_per_rush")
    )
    selected = calibration.filter(nw.col("selected").cast(nw.Boolean)).select(
        "candidate_id",
        "team_penalty",
        "context_penalty",
        "half_life_days",
        "policy",
        "mean_squared_error",
    )
    return (
        coefficients.join(
            uncertainty.select("block", "level", "cluster_standard_error"),
            on=("block", "level"),
            cardinality="one_to_one",
        )
        .join(baseline, how="cross")
        .join(selected, how="cross")
        .with_columns(
            nw.lit(year).alias("season"),
            nw.lit(last_week).alias("training_last_week"),
            nw.lit(_FEATURE_REVISION).alias("feature_revision"),
            nw.lit(uses_prior).alias("uses_earlier_team_prior"),
        )
        .select(*ALYModel.model_fields)
        .sort("block", "level")
    )


@step(id="cfbd.line_yards.team_ratings", revision=1, output=TeamLineYards)
def team_ratings(
    features: Table,
    games: Table,
    model: Table,
    *,
    weeks: tuple[int, ...],
    team: str | None,
) -> Table:
    """Normalize joint effects onto the declared season/team/unit universe.

    :param features: All source plays including unknown and excluded actions.
    :param games: Authoritative participants defining the team universe.
    :param model: Frozen selected model or a typed empty unsupported model.
    :param weeks: Explicit source partitions included in the population.
    :param team: Optional output filter applied after population fitting.
    :return: Team ratings, observed averages and explicit evidence coverage.
    """
    products: list[Table] = []
    for unit, identity in (("offense", "offense_id"), ("defense", "defense_id")):
        rows = features.with_columns(
            nw.col(identity).alias("team_id"),
            (nw.col("rush_status") == "evaluated").cast(nw.Int64).alias("__evaluated"),
            (nw.col("rush_status") == "unknown").cast(nw.Int64).alias("__unknown"),
            (nw.col("rush_status") == "excluded").cast(nw.Int64).alias("__excluded"),
            (
                (nw.col("rush_status") == "evaluated")
                & (nw.col("score_context") == "unknown")
            )
            .cast(nw.Int64)
            .alias("__score_unknown"),
            ((nw.col("rush_status") == "evaluated") & nw.col("clock_seconds").is_null())
            .cast(nw.Int64)
            .alias("__clock_unknown"),
            nw.when(nw.col("rush_status") == "evaluated")
            .then(nw.col("yards_gained"))
            .otherwise(nw.lit(0))
            .alias("__yards"),
            nw.col("line_yards").fill_null(0).alias("__line"),
        )
        per_game = rows.aggregate(
            keys=("game_id", "team_id"),
            expressions=(
                nw.len().alias("source_rows"),
                nw.col("__evaluated").sum().alias("evaluated_rushes"),
                nw.col("__unknown").sum().alias("unknown_plays"),
                nw.col("__excluded").sum().alias("excluded_plays"),
                nw.col("__score_unknown").sum().alias("unknown_score_rushes"),
                nw.col("__clock_unknown").sum().alias("unknown_clock_rushes"),
                nw.col("__yards").sum().alias("__yards"),
                nw.col("__line").sum().alias("__line"),
            ),
        )
        universe = (
            games.filter(nw.col("week").is_in(weeks))
            .select("season", "game_id", "team_id", "team")
            .join(per_game, on=("game_id", "team_id"), cardinality="one_to_one")
            .with_columns(
                nw.col("source_rows").is_null().cast(nw.Int64).alias("__unavailable")
            )
        )
        measures = (
            "source_rows",
            "evaluated_rushes",
            "unknown_plays",
            "excluded_plays",
            "unknown_score_rushes",
            "unknown_clock_rushes",
            "__yards",
            "__line",
        )
        totals = universe.with_columns(
            *(nw.col(name).fill_null(0).alias(name) for name in measures)
        ).aggregate(
            keys=("season", "team_id", "team"),
            expressions=(
                *(nw.col(name).sum().alias(name) for name in measures),
                nw.len().alias("games"),
                nw.col("__unavailable").sum().alias("unavailable_games"),
            ),
        )
        effects = model.filter(nw.col("block") == unit).select(
            nw.col("level").cast(nw.Int64).alias("team_id"),
            nw.col("estimate").alias("effect"),
            "cluster_standard_error",
            "weighted_raw_yards_per_rush",
            "data_rank",
            "parameter_count",
            "constraint_count",
            "prior_dependent",
        )
        result = totals.join(
            effects, on=("team_id",), cardinality="one_to_one"
        ).with_columns(
            nw.lit(unit).alias("unit"),
            nw.when(nw.col("evaluated_rushes") > 0)
            .then(nw.col("__yards") / nw.col("evaluated_rushes"))
            .otherwise(nw.lit(None))
            .alias("raw_yards_per_rush"),
            nw.when(nw.col("evaluated_rushes") > 0)
            .then(nw.col("__line") / nw.col("evaluated_rushes"))
            .otherwise(nw.lit(None))
            .alias("raw_line_yards_per_rush"),
            (
                nw.col("weighted_raw_yards_per_rush")
                + (1 if unit == "offense" else -1) * nw.col("effect")
            ).alias("adjusted_line_yards"),
            nw.when(nw.col("source_rows") == 0)
            .then(nw.lit("unavailable"))
            .when(
                (nw.col("unknown_plays") > 0)
                | (nw.col("unavailable_games") > 0)
                | ((nw.col("evaluated_rushes") > 0) & nw.col("effect").is_null())
            )
            .then(nw.lit("partial"))
            .when(nw.col("evaluated_rushes") == 0)
            .then(nw.lit("empty"))
            .otherwise(nw.lit("present"))
            .alias("coverage"),
        )
        products.append(result.select(*TeamLineYards.model_fields))
    result = concat_tables(products)
    if team is not None:
        result = (
            result.normalize_text("team", into="__team")
            .filter(nw.col("__team") == " ".join(team.split()).casefold())
            .drop("__team")
        )
    return result.sort("season", "team_id", "unit")


@dataset(
    id="cfbd.line_yards.calibration",
    revision=1,
    row=ALYCalibration,
    grain="one ALY candidate and forward-validation evidence",
    keys=("candidate_id",),
    order_by=("candidate_id",),
)
def aly_calibration(
    *,
    scores: tuple[RecipeRef[Table], ...] | None,
    candidates: tuple[ALYParameters, ...],
    explicit: bool,
) -> RecipeRef[Table]:
    """Build the named calibration evidence product.

    :param scores: Native fold-score references.
    :param candidates: Explicit finite search space.
    :param explicit: Caller-selected policy.
    :return: Validated candidate evidence reference.
    """
    return calibrate(scores, candidates=candidates, explicit=explicit)


@dataset(
    id="cfbd.line_yards.model",
    revision=1,
    row=ALYModel,
    grain="one frozen centered ALY coefficient",
    keys=("block", "level"),
    order_by=("block", "level"),
)
def aly_model(
    *,
    coefficients: RecipeRef[Table],
    observations: RecipeRef[Table],
    uncertainty: RecipeRef[Table],
    calibration: RecipeRef[Table],
    year: int,
    last_week: int,
    uses_prior: bool,
) -> RecipeRef[Table]:
    """Build the named frozen model and numerical diagnostics product.

    :param coefficients: Selected fit.
    :param observations: Exact selected weighted observations.
    :param uncertainty: Game-cluster uncertainty reference.
    :param calibration: Parameter selection evidence.
    :param year: Season identity.
    :param last_week: Last admitted source week.
    :param uses_prior: Whether earlier-season team means were requested.
    :return: Frozen model reference with normalization and uncertainty.
    """
    return publish_model(
        coefficients,
        observations,
        uncertainty,
        calibration,
        year=year,
        last_week=last_week,
        uses_prior=uses_prior,
    )


@dataset(
    id="cfbd.line_yards.team_seasons",
    revision=1,
    row=TeamLineYards,
    grain="one team/season/unit opponent-adjusted College ALY",
    keys=("season", "team_id", "unit"),
    order_by=("season", "team_id", "unit"),
)
def team_season_line_yards(
    *,
    features: RecipeRef[Table],
    games: RecipeRef[Table],
    model: RecipeRef[Table],
    weeks: tuple[int, ...],
    team: str | None,
) -> RecipeRef[Table]:
    """Build the named normalized team-strength product.

    :param features: Shared source play evidence.
    :param games: Population participants.
    :param model: Frozen joint model.
    :param weeks: Explicit source partitions.
    :param team: Output-only team selector.
    :return: Validated team-season rating reference.
    """
    return team_ratings(features, games, model, weeks=weeks, team=team)


@workflow(id="cfbd.line_yards", revision=1)
def line_yards(
    *,
    year: int,
    weeks: tuple[int, ...],
    parameters: ALYParameters | None = None,
    candidates: tuple[ALYParameters, ...] | None = None,
    team: str | None = None,
    prior_model: RecipeRef[Table] | None = None,
    season_type: SeasonType = SeasonType.regular,
    classification: Classification | None = None,
    max_parameters: int = 768,
) -> LineYardsRefs:
    """Build raw evidence and full opponent/situation-adjusted College ALY.

    :param year: Season year.
    :param weeks: Explicit source weeks; automatic tuning needs at least two.
    :param parameters: Optional frozen penalties/decay, bypassing auto selection.
    :param candidates: Optional search grid of at most eight unique candidates.
    :param team: Output-only filter; the full selected population is fitted.
    :param prior_model: Optional earlier-season frozen model reference.
    :param season_type: Source phase.
    :param classification: Optional population classification filter.
    :param max_parameters: Coefficient bound controlling dense fitting resources.
    :return: Named plays, calibration, frozen model and team-season references.
    :raises cfb_data.analytics.CFBDRecipeCompilationError: If selectors, configuration or bounds are invalid.
    """
    validate_partitions(year, weeks)
    if isinstance(max_parameters, bool) or not 2 <= max_parameters <= 1024:
        raise ValueError("max_parameters must be between two and 1024")
    if parameters is not None and candidates is not None:
        raise ValueError("Supply either frozen parameters or a candidate grid")
    if parameters is None and len(weeks) < 2:
        raise ValueError(
            "Automatic ALY calibration needs at least two explicit weeks; otherwise supply frozen parameters"
        )
    grid = (parameters,) if parameters is not None else candidates
    if grid is None:
        grid = tuple(
            ALYParameters(
                team_penalty=team_ridge,
                context_penalty=context_ridge,
                half_life_days=decay,
            )
            for team_ridge, context_ridge in (
                (16.0, 64.0),
                (64.0, 256.0),
                (256.0, 1024.0),
            )
            for decay in (None, 28.0)
        )
    if not 1 <= len(grid) <= 8 or len(set(grid)) != len(grid):
        raise ValueError("ALY calibration requires one to eight distinct candidates")
    ordered_weeks = tuple(sorted(weeks))
    features = scrimmage_plays(
        year=year,
        weeks=ordered_weeks,
        season_type=season_type,
        classification=classification,
    )
    games = team_games(
        year=year, season_type=season_type, classification=classification
    )
    prior = None if prior_model is None else earlier_team_prior(prior_model, year=year)
    observations: list[RecipeRef[Table]] = []
    designs: list[RecipeRef[Table]] = []
    statistics: list[RecipeRef[Table]] = []
    coefficients: list[RecipeRef[Table]] = []
    scores: list[RecipeRef[Table]] = []
    for candidate_id, candidate in enumerate(grid):
        candidate_name = f"candidate-{candidate_id}"
        penalties = tuple(
            BlockPenalty(
                block=term.block,
                penalty=candidate.team_penalty
                if term.block in {"offense", "defense"}
                else candidate.context_penalty,
            )
            for term in _TERMS
        )
        rows = rush_observations.as_(f"{candidate_name}-observations")(
            features, last_week=ordered_weeks[-1], parameters=candidate
        )
        design = categorical_design.as_(f"{candidate_name}-design")(rows, terms=_TERMS)
        stats = additive_statistics.as_(f"{candidate_name}-statistics")(design)
        fitted = fit_additive_model.as_(f"{candidate_name}-fit")(
            stats, penalties=penalties, max_parameters=max_parameters, prior=prior
        )
        observations.append(rows)
        designs.append(design)
        statistics.append(stats)
        coefficients.append(fitted)
        if parameters is None:
            for position in range(max(1, len(ordered_weeks) - 2), len(ordered_weeks)):
                holdout = ordered_weeks[position]
                fold_name = f"{candidate_name}-fold-{holdout}"
                train = rush_observations.as_(f"{fold_name}-train-observations")(
                    features,
                    last_week=ordered_weeks[position - 1],
                    holdout_week=holdout,
                    parameters=candidate,
                )
                train_design = categorical_design.as_(f"{fold_name}-train-design")(
                    train, terms=_TERMS
                )
                train_fit = fit_additive_model.as_(f"{fold_name}-fit")(
                    additive_statistics.as_(f"{fold_name}-statistics")(train_design),
                    penalties=penalties,
                    max_parameters=max_parameters,
                    prior=prior,
                )
                validation = rush_observations.as_(
                    f"{fold_name}-validation-observations"
                )(features, last_week=holdout, parameters=candidate)
                validation = validation_week.as_(f"{fold_name}-week")(
                    validation, week=holdout
                )
                prediction = predict_additive_model.as_(f"{fold_name}-predict")(
                    categorical_design.as_(f"{fold_name}-validation-design")(
                        validation, terms=_TERMS
                    ),
                    train_fit,
                )
                scores.append(
                    fold_score.as_(f"{fold_name}-score")(
                        prediction, candidate_id=candidate_id
                    )
                )
    calibration = aly_calibration(
        scores=tuple(scores) if scores else None,
        candidates=grid,
        explicit=parameters is not None,
    )
    selected_observations = select_observations(tuple(observations), calibration)
    selected_design = select_design(tuple(designs), calibration)
    selected_statistics = select_statistics(tuple(statistics), calibration)
    selected_coefficients = select_coefficients(tuple(coefficients), calibration)
    uncertainty = additive_cluster_uncertainty(
        selected_statistics,
        selected_coefficients,
        cluster_score_statistics(selected_design, selected_coefficients),
        max_parameters=max_parameters,
    )
    model = aly_model(
        coefficients=selected_coefficients,
        observations=selected_observations,
        uncertainty=uncertainty,
        calibration=calibration,
        year=year,
        last_week=ordered_weeks[-1],
        uses_prior=prior_model is not None,
    )
    return {
        "plays": features,
        "calibration": calibration,
        "model": model,
        "team_seasons": team_season_line_yards(
            features=features, games=games, model=model, weeks=ordered_weeks, team=team
        ),
    }


@step(id="cfbd.line_yards.validation_week", revision=1, output=RushObservation)
def validation_week(observations: Table, *, week: int) -> Table:
    """Select a declared validation week within a native observation relation.

    :param observations: Evaluated rushing observations with source week evidence.
    :param week: Explicit held-out week.
    :return: Only held-out observations.
    """
    return observations.filter(nw.col("week") == week)


__all__ = ["ALYModel", "ALYParameters", "TeamLineYards", "line_yards"]
