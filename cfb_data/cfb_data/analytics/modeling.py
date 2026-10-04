"""Fit reusable centered additive models from native reduced statistics.

Observations stay partitioned. Only explicitly bounded coefficient-scale
statistics cross the numerical fitting boundary. Predictions return to native
table expressions and inherit global identity and cardinality checks.
"""

from __future__ import annotations

from enum import StrEnum

import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from ._recipes import step
from .errors import CFBDTransformError
from .tables import Table, concat_tables


class EffectObservation(BaseModel):
    """Declare one categorical design contribution to an observation.

    Each observation has exactly one intercept and one level per effect block.
    Signed ``value`` allows prevention effects without changing their meaning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    observation_id: str
    cluster_id: str
    block: str
    level: str
    value: float
    response: float
    weight: float = Field(gt=0)


class DesignTerm(BaseModel):
    """Bind an observed categorical column to a signed model effect block."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    block: str = Field(min_length=1)
    column: str = Field(min_length=1)
    multiplier: float = Field(default=1.0, allow_inf_nan=False)


class StatisticKind(StrEnum):
    """Describe an additive model's reduced equation entry."""

    gram = "gram"
    rhs = "rhs"
    exposure = "exposure"
    total = "total"


class ModelStatistic(BaseModel):
    """Declare one reduced entry in an additive model's normal equations."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: StatisticKind
    block: str
    level: str
    other_block: str
    other_level: str
    value: float


class BlockPenalty(BaseModel):
    """Bind a strictly positive ridge penalty to one centered effect block."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    block: str = Field(min_length=1)
    penalty: float = Field(gt=0, allow_inf_nan=False)


class ModelCoefficient(BaseModel):
    """Expose one fitted effect and the common numerical diagnostics.

    Variance is a conditional model approximation, not a game-cluster confidence
    interval. Rank deficiency remains visible even when ridge ensures a solve.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    block: str
    level: str
    estimate: float
    exposure: float
    penalty: float
    conditional_variance: float | None
    data_rank: int
    parameter_count: int
    constraint_count: int
    observations: int
    clusters: int
    effective_observations: float
    condition_number: float
    residual_variance: float | None
    equation_residual: float
    prior_dependent: bool


class ModelPrediction(BaseModel):
    """Expose one prediction with its observed response and support evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    observation_id: str
    cluster_id: str
    response: float
    weight: float
    prediction: float | None
    residual: float | None
    unsupported_levels: int


class ModelUncertainty(BaseModel):
    """Expose a game-cluster sandwich standard error conditional on fixed priors."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    block: str
    level: str
    cluster_standard_error: float | None
    clusters: int


@step(id="cfb.modeling.categorical_design", revision=1, output=EffectObservation)
def categorical_design(observations: Table, *, terms: tuple[DesignTerm, ...]) -> Table:
    """Expand bounded categorical contributions through native projections.

    :param observations: One row per observation with identity, response and weight.
    :param terms: Unique non-intercept blocks referencing nonnull categorical columns.
    :return: Partitioned long design with an explicit intercept contribution.
    :raises ValueError: If block declarations are repeated or unbounded.
    :raises CFBDTransformError: If observed identities or categories are invalid.
    """
    if (
        len(terms) > 15
        or len({term.block for term in terms}) != len(terms)
        or any(term.block == "intercept" for term in terms)
    ):
        raise ValueError("Design requires at most 15 distinct non-intercept blocks")
    if not {term.column for term in terms} <= set(observations.columns):
        raise CFBDTransformError("Categorical design references unavailable columns")
    base = observations.require_unique(
        ("observation_id",), message="Model observations repeat identity keys"
    )
    base = (
        base.require(
            nw.all_horizontal(
                *(~nw.col(term.column).is_null() for term in terms), ignore_nulls=False
            ),
            message="Categorical model levels must preserve missingness explicitly",
        )
        if terms
        else base
    )
    columns = ("observation_id", "cluster_id", "response", "weight")
    tables: list[Table] = [
        base.select(*columns)
        .with_columns(
            nw.lit("intercept").alias("block"),
            nw.lit("constant").alias("level"),
            nw.lit(1.0).alias("value"),
        )
        .select(*EffectObservation.model_fields)
    ]
    for term in terms:
        tables.append(
            base.select(*columns, nw.col(term.column).cast(nw.String).alias("level"))
            .with_columns(
                nw.lit(term.block).alias("block"),
                nw.lit(term.multiplier).alias("value"),
            )
            .select(*EffectObservation.model_fields)
        )
    return concat_tables(tables).sort("observation_id", "block")


@step(id="cfb.modeling.additive_statistics", revision=1, output=ModelStatistic)
def additive_statistics(design: Table, *, max_blocks: int = 16) -> Table:
    """Reduce a categorical design into native distributed sufficient statistics.

    :param design: Long design with one intercept and one entry per effect block.
    :param max_blocks: Bound on contributions and pair expansion per observation.
    :return: Sparse normal-equation entries and bounded scalar summaries.
    :raises ValueError: If the contribution bound is invalid.
    :raises CFBDTransformError: If design identities or values conflict.
    """
    if isinstance(max_blocks, bool) or not 1 <= max_blocks <= 32:
        raise ValueError("max_blocks must be between one and 32")
    checked = design.require_unique(
        ("observation_id", "block"), message="Model design repeats an effect block"
    ).require(
        (nw.col("weight") > 0)
        & nw.col("weight").is_finite()
        & nw.col("response").is_finite()
        & nw.col("value").is_finite()
        & ~nw.col("cluster_id").is_null()
        & ~nw.col("level").is_null(),
        message="Model design contains invalid numeric observations",
    )
    checked = checked.with_columns(
        (nw.col("block") == "intercept").cast(nw.Int64).alias("__intercept"),
        (nw.col("weight") * nw.col("value") * nw.col("response")).alias("__rhs"),
    )
    groups = (
        checked.aggregate(
            keys=("observation_id",),
            expressions=(
                nw.len().alias("blocks"),
                nw.col("response").min().alias("__response_min"),
                nw.col("response").max().alias("__response_max"),
                nw.col("weight").min().alias("__weight_min"),
                nw.col("weight").max().alias("__weight_max"),
                nw.col("cluster_id").min().alias("__cluster_min"),
                nw.col("cluster_id").max().alias("__cluster_max"),
                nw.col("__intercept").sum().alias("intercepts"),
            ),
        )
        .join(
            checked.select(nw.col("block").n_unique().alias("__expected_blocks")),
            how="cross",
        )
        .require(
            (nw.col("blocks") <= max_blocks)
            & (nw.col("blocks") == nw.col("__expected_blocks"))
            & (nw.col("__response_min") == nw.col("__response_max"))
            & (nw.col("__weight_min") == nw.col("__weight_max"))
            & (nw.col("__cluster_min") == nw.col("__cluster_max"))
            & (nw.col("intercepts") == 1),
            message="Model design violates observation consistency or expansion bounds",
        )
    )
    checked = checked.join(
        groups.select("observation_id"),
        on=("observation_id",),
        cardinality="many_to_one",
    ).require(
        (nw.col("block") != "intercept") | (nw.col("value") == 1),
        message="Model intercept contributions must equal one",
    )
    other = checked.select("observation_id", "block", "level", "value").rename(
        {"block": "other_block", "level": "other_level", "value": "other_value"}
    )
    gram = (
        checked.join(other, on=("observation_id",), cardinality="many_to_many")
        .with_columns(
            (nw.col("weight") * nw.col("value") * nw.col("other_value")).alias("__gram")
        )
        .aggregate(
            keys=("block", "level", "other_block", "other_level"),
            expressions=(nw.col("__gram").sum().alias("value"),),
        )
        .with_columns(nw.lit("gram").alias("kind"))
    )
    rhs = checked.aggregate(
        keys=("block", "level"),
        expressions=(nw.col("__rhs").sum().alias("value"),),
    )
    exposure = checked.aggregate(
        keys=("block", "level"),
        expressions=(nw.col("weight").sum().alias("value"),),
    )
    tables: list[Table] = [gram.select(*ModelStatistic.model_fields)]
    for kind, table in (("rhs", rhs), ("exposure", exposure)):
        tables.append(
            table.with_columns(
                nw.lit(kind).alias("kind"),
                nw.lit("").alias("other_block"),
                nw.lit("").alias("other_level"),
            ).select(*ModelStatistic.model_fields)
        )
    base = checked.filter(nw.col("block") == "intercept")
    totals: tuple[tuple[str, nw.Expr], ...] = (
        ("observations", nw.len().cast(nw.Float64)),
        ("clusters", nw.col("cluster_id").n_unique().cast(nw.Float64)),
        ("weight", nw.col("weight").sum()),
        ("weight_squared", (nw.col("weight") ** 2).sum()),
        ("response_squared", (nw.col("weight") * nw.col("response") ** 2).sum()),
    )
    for name, expression in totals:
        tables.append(
            base.select(expression.alias("value"))
            .with_columns(
                nw.lit("total").alias("kind"),
                nw.lit(name).alias("block"),
                nw.lit("").alias("level"),
                nw.lit("").alias("other_block"),
                nw.lit("").alias("other_level"),
            )
            .select(*ModelStatistic.model_fields)
        )
    return concat_tables(tables).sort(
        "kind", "block", "level", "other_block", "other_level"
    )


@step(id="cfb.modeling.fit_additive", revision=1, output=ModelCoefficient, dask=False)
def fit_additive_model(
    statistics: Table,
    *,
    penalties: tuple[BlockPenalty, ...],
    max_parameters: int = 768,
    prior: Table | None = None,
) -> Table:
    """Solve a bounded exposure-centered ridge system on the coordinator.

    :param statistics: Previously reduced and persisted normal-equation table.
    :param penalties: Exactly one positive penalty per non-intercept block.
    :param max_parameters: Maximum coefficient count, bounding dense memory.
    :param prior: Optional earlier coefficients with block, level and estimate.
    :return: Coefficient table with conditioning, rank and uncertainty diagnostics.
    :raises ValueError: If coefficient bounds or penalty declarations are invalid.
    :raises CFBDTransformError: If equations or numerical invariants are invalid.
    """
    if isinstance(max_parameters, bool) or not 2 <= max_parameters <= 1024:
        raise ValueError("max_parameters must be between two and 1024")
    if len({penalty.block for penalty in penalties}) != len(penalties):
        raise ValueError("Penalty blocks must be unique")
    frame = (
        statistics.require_unique(
            ("kind", "block", "level", "other_block", "other_level"),
            message="Model statistics repeat equation keys",
        )
        .require(
            nw.col("value").is_finite(),
            message="Model statistics contain nonfinite values",
        )
        .collect_bounded(max_rows=max_parameters**2 + 2 * max_parameters + 5)
    )
    coefficients = frame.loc[frame["kind"] == "rhs", ["block", "level"]].sort_values(
        ["block", "level"], ignore_index=True
    )
    size = len(coefficients)
    if size == 0:
        return _coefficient_table(pd.DataFrame(columns=ModelCoefficient.model_fields))
    if size > max_parameters:
        raise CFBDTransformError("Model coefficient bound was exceeded")
    index = pd.MultiIndex.from_frame(coefficients)
    if index.has_duplicates:
        raise CFBDTransformError("Model statistics repeat coefficient keys")
    blocks: tuple[str, ...] = tuple(coefficients["block"].drop_duplicates())
    declared: dict[str, float] = {item.block: item.penalty for item in penalties}
    if set(blocks) - {"intercept"} != set(declared):
        raise CFBDTransformError("Penalty blocks do not match the fitted design")
    intercept_indices = np.flatnonzero(coefficients["block"].to_numpy() == "intercept")
    if len(intercept_indices) != 1:
        raise CFBDTransformError("Model statistics require one intercept coefficient")
    gram = _gram_matrix(frame, index)
    rhs = _aligned_values(frame, "rhs", index)
    exposure = _aligned_values(frame, "exposure", index)
    totals = frame.loc[frame["kind"] == "total"].set_index("block")["value"]
    if set(totals.index) != {
        "observations",
        "clusters",
        "weight",
        "weight_squared",
        "response_squared",
    }:
        raise CFBDTransformError("Model statistics omit required scalar summaries")
    if (
        totals["observations"] < 1
        or totals["observations"] != int(totals["observations"])
        or totals["clusters"] < 1
        or totals["clusters"] > totals["observations"]
        or totals["clusters"] != int(totals["clusters"])
    ):
        raise CFBDTransformError(
            "Model statistics contain invalid observation or cluster counts"
        )
    observations = int(totals["observations"])
    clusters = int(totals["clusters"])
    weight = float(totals["weight"])
    squared_weight = float(totals["weight_squared"])
    if weight <= 0 or squared_weight <= 0 or (exposure <= 0).any():
        raise CFBDTransformError("Model statistics have no positive evidence weight")
    prior_values: NDArray[np.float64] = np.zeros(size, dtype=np.float64)
    if prior is not None:
        prior_frame = prior.collect_bounded(max_rows=max_parameters)
        earlier = coefficients.merge(
            prior_frame[["block", "level", "estimate"]],
            on=["block", "level"],
            how="left",
            validate="one_to_one",
        )
        prior_values = earlier["estimate"].fillna(0).to_numpy(dtype=float)
    penalty_values: NDArray[np.float64] = np.zeros(size, dtype=np.float64)
    constraint = _centering_matrix(coefficients, exposure)
    for block in blocks:
        if block == "intercept":
            continue
        mask = coefficients["block"].to_numpy() == block
        prior_values[mask] -= float(
            exposure[mask] @ prior_values[mask] / exposure[mask].sum()
        )
        penalty_values[mask] = declared[block]
    normal = gram + np.diag(penalty_values)
    constraint_count = len(constraint)
    system = np.block(
        [
            [normal, constraint.T],
            [constraint, np.zeros((constraint_count, constraint_count), dtype=float)],
        ]
    )
    target = np.r_[rhs + penalty_values * prior_values, np.zeros(constraint_count)]
    try:
        solution = np.linalg.solve(system, target)
        inverse = np.linalg.solve(system, np.eye(len(system)))[:size, :size]
    except np.linalg.LinAlgError as exc:
        raise CFBDTransformError(
            "Centered model normal equations cannot be solved"
        ) from exc
    estimate = solution[:size]
    residual = float(np.max(np.abs(system @ solution - target)))
    if not np.isfinite(solution).all() or residual > 1e-7 * max(
        1.0, float(np.max(np.abs(target)))
    ):
        raise CFBDTransformError("Model solve violates its finite residual contract")
    data_rank = int(np.linalg.matrix_rank(gram))
    effective = weight**2 / squared_weight
    degrees = float(np.trace(inverse @ gram))
    error = max(
        0.0,
        float(totals["response_squared"])
        - 2 * float(estimate @ rhs)
        + float(estimate @ gram @ estimate),
    )
    variance = error / (effective - degrees) if effective > degrees else None
    covariance = inverse @ gram @ inverse.T
    result = coefficients.copy()
    result["estimate"] = estimate
    result["exposure"] = exposure
    result["penalty"] = penalty_values
    result["conditional_variance"] = (
        np.maximum(0.0, np.diag(covariance)) * variance
        if variance is not None
        else None
    )
    result["data_rank"] = data_rank
    result["parameter_count"] = size
    result["constraint_count"] = constraint_count
    result["observations"] = observations
    result["clusters"] = clusters
    result["effective_observations"] = effective
    result["condition_number"] = float(np.linalg.cond(system))
    result["residual_variance"] = variance
    result["equation_residual"] = residual
    result["prior_dependent"] = data_rank < size - constraint_count
    return _coefficient_table(result)


@step(id="cfb.modeling.predict_additive", revision=1, output=ModelPrediction)
def predict_additive_model(design: Table, coefficients: Table) -> Table:
    """Predict natively with average effects for explicitly unsupported levels.

    :param design: Validated long design in the same block/value convention.
    :param coefficients: Frozen model coefficients from earlier fitting data.
    :return: One prediction per observation with unsupported-level counts.
    """
    return _prediction_table(design, coefficients)


def _prediction_table(design: Table, coefficients: Table) -> Table:
    """Compose the shared native prediction graph without recursive recipe capture."""
    joined = design.join(
        coefficients.select("block", "level", "estimate"),
        on=("block", "level"),
        cardinality="many_to_one",
    ).with_columns(
        (nw.col("value") * nw.col("estimate").fill_null(0)).alias("__contribution"),
        nw.col("estimate").is_null().cast(nw.Int64).alias("__unsupported"),
        ((nw.col("block") == "intercept") & ~nw.col("estimate").is_null())
        .cast(nw.Int64)
        .alias("__intercept_present"),
    )
    predicted = (
        joined.aggregate(
            keys=("observation_id", "cluster_id", "response", "weight"),
            expressions=(
                nw.col("__contribution").sum().alias("__prediction"),
                nw.col("__unsupported").sum().alias("unsupported_levels"),
                nw.col("__intercept_present").sum().alias("__intercept"),
            ),
        )
        .with_columns(
            nw.when(nw.col("__intercept") == 1)
            .then(nw.col("__prediction"))
            .otherwise(nw.lit(None))
            .alias("prediction"),
        )
        .with_columns((nw.col("response") - nw.col("prediction")).alias("residual"))
    )
    return predicted.select(*ModelPrediction.model_fields).sort("observation_id")


@step(id="cfb.modeling.cluster_scores", revision=1, output=ModelStatistic)
def cluster_score_statistics(design: Table, coefficients: Table) -> Table:
    """Reduce correlated residual contributions into a native sandwich matrix.

    :param design: The model's evaluated training observations and cluster IDs.
    :param coefficients: Coefficients fitted to that exact design.
    :return: A bounded coefficient-scale outer-product matrix and cluster count.
    :raises CFBDTransformError: If training predictions lack model support.
    """
    predictions = _prediction_table(design, coefficients).require(
        ~nw.col("prediction").is_null() & (nw.col("unsupported_levels") == 0),
        message="Cluster uncertainty requires complete training-model support",
    )
    joined = design.join(
        predictions.select("observation_id", "residual"),
        on=("observation_id",),
        cardinality="many_to_one",
    )
    scores = joined.with_columns(
        (nw.col("weight") * nw.col("value") * nw.col("residual")).alias(
            "__score_contribution"
        )
    ).aggregate(
        keys=("cluster_id", "block", "level"),
        expressions=(nw.col("__score_contribution").sum().alias("__score"),),
    )
    other = scores.rename(
        {"block": "other_block", "level": "other_level", "__score": "__other_score"}
    )
    matrix = (
        scores.join(other, on=("cluster_id",), cardinality="many_to_many")
        .with_columns(
            (nw.col("__score") * nw.col("__other_score")).alias("__outer_product")
        )
        .aggregate(
            keys=("block", "level", "other_block", "other_level"),
            expressions=(nw.col("__outer_product").sum().alias("value"),),
        )
        .with_columns(nw.lit("gram").alias("kind"))
        .select(*ModelStatistic.model_fields)
    )
    total = (
        scores.select(nw.col("cluster_id").n_unique().cast(nw.Float64).alias("value"))
        .with_columns(
            nw.lit("total").alias("kind"),
            nw.lit("clusters").alias("block"),
            nw.lit("").alias("level"),
            nw.lit("").alias("other_block"),
            nw.lit("").alias("other_level"),
        )
        .select(*ModelStatistic.model_fields)
    )
    return concat_tables((matrix, total)).sort(
        "kind", "block", "level", "other_block", "other_level"
    )


@step(
    id="cfb.modeling.cluster_uncertainty",
    revision=1,
    output=ModelUncertainty,
    dask=False,
)
def additive_cluster_uncertainty(
    statistics: Table,
    coefficients: Table,
    cluster_scores: Table,
    *,
    max_parameters: int = 768,
) -> Table:
    """Calculate finite-cluster-corrected uncertainty from reduced matrices.

    :param statistics: Persisted training normal equations.
    :param coefficients: Fitted coefficients and centering exposures.
    :param cluster_scores: Native cluster-score outer-product reduction.
    :param max_parameters: Declared coefficient bound shared with the fit.
    :return: Conditional cluster standard errors; fewer than two clusters is unknown.
    :raises CFBDTransformError: If bounded equations are inconsistent.
    """
    model = coefficients.collect_bounded(max_rows=max_parameters)
    model = model.sort_values(["block", "level"], ignore_index=True)
    result = model[["block", "level"]].copy()
    if model.empty:
        result["cluster_standard_error"] = pd.Series(dtype="Float64")
        result["clusters"] = pd.Series(dtype="Int64")
        return Table(nw.from_native(result).lazy())
    index = pd.MultiIndex.from_frame(result)
    original = statistics.collect_bounded(
        max_rows=max_parameters**2 + 2 * max_parameters + 5
    )
    scores = cluster_scores.collect_bounded(max_rows=max_parameters**2 + 1)
    clusters = int(scores.loc[scores["kind"] == "total", "value"].iloc[0])
    if clusters < 2:
        result["cluster_standard_error"] = pd.Series(
            [None] * len(result), dtype="Float64"
        )
    else:
        gram = _gram_matrix(original, index)
        meat = _gram_matrix(scores, index)
        exposure = np.asarray(model["exposure"].to_numpy(), dtype=np.float64)
        penalty = np.asarray(model["penalty"].to_numpy(), dtype=np.float64)
        constraint = _centering_matrix(model, exposure)
        size = len(model)
        system = np.block(
            [
                [gram + np.diag(penalty), constraint.T],
                [constraint, np.zeros((len(constraint), len(constraint)), dtype=float)],
            ]
        )
        inverse = np.linalg.solve(system, np.eye(len(system)))[:size, :size]
        covariance = inverse @ meat @ inverse.T * clusters / (clusters - 1)
        diagonal = np.diag(covariance)
        if not np.isfinite(diagonal).all() or (diagonal < -1e-8).any():
            raise CFBDTransformError(
                "Cluster covariance violates its finite variance contract"
            )
        result["cluster_standard_error"] = np.sqrt(np.maximum(diagonal, 0))
    result["clusters"] = clusters
    result["block"] = result["block"].astype("string")
    result["level"] = result["level"].astype("string")
    result["cluster_standard_error"] = result["cluster_standard_error"].astype(
        "Float64"
    )
    result["clusters"] = result["clusters"].astype("Int64")
    return Table(nw.from_native(result).lazy())


def _gram_matrix(frame: pd.DataFrame, index: pd.MultiIndex) -> NDArray[np.float64]:
    """Decode an explicitly bounded sparse coefficient matrix."""
    matrix = frame.loc[frame["kind"] == "gram"]
    left = index.get_indexer(pd.MultiIndex.from_frame(matrix[["block", "level"]]))
    right = index.get_indexer(
        pd.MultiIndex.from_frame(
            matrix[["other_block", "other_level"]].rename(
                columns={"other_block": "block", "other_level": "level"}
            )
        )
    )
    if (left < 0).any() or (right < 0).any():
        raise CFBDTransformError("Model matrix references unavailable coefficients")
    result: NDArray[np.float64] = np.zeros((len(index), len(index)), dtype=np.float64)
    result[left, right] = matrix["value"].to_numpy(dtype=float)
    if not np.isfinite(result).all() or not np.allclose(result, result.T, atol=1e-9):
        raise CFBDTransformError("Model normal equations are nonfinite or asymmetric")
    return result


def _centering_matrix(
    coefficients: pd.DataFrame, exposure: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Build normalized exposure constraints for bounded categorical blocks."""
    rows: list[NDArray[np.float64]] = []
    for block in coefficients["block"].drop_duplicates():
        if block == "intercept":
            continue
        mask = coefficients["block"].to_numpy() == block
        row: NDArray[np.float64] = np.zeros(len(coefficients), dtype=np.float64)
        row[mask] = exposure[mask] / exposure[mask].sum()
        rows.append(row)
    return np.asarray(rows, dtype=np.float64).reshape((-1, len(coefficients)))


def _aligned_values(
    frame: pd.DataFrame, kind: str, index: pd.MultiIndex
) -> NDArray[np.float64]:
    """Align bounded coefficient statistics and reject missing entries."""
    selected = frame.loc[frame["kind"] == kind].set_index(["block", "level"])
    values: NDArray[np.float64] = np.asarray(
        selected.reindex(index)["value"].to_numpy(), dtype=np.float64
    )
    if not np.isfinite(values).all():
        raise CFBDTransformError("Model coefficient statistics are incomplete")
    return values


def _coefficient_table(frame: pd.DataFrame) -> Table:
    """Return a typed coefficient relation after a bounded numerical solve."""
    frame = frame.reindex(columns=tuple(ModelCoefficient.model_fields))
    for name in ("block", "level"):
        frame[name] = frame[name].astype("string")
    for name in (
        "data_rank",
        "parameter_count",
        "constraint_count",
        "observations",
        "clusters",
    ):
        frame[name] = frame[name].astype("Int64")
    frame["prior_dependent"] = frame["prior_dependent"].astype("boolean")
    for name in set(ModelCoefficient.model_fields) - {
        "block",
        "level",
        "data_rank",
        "parameter_count",
        "constraint_count",
        "observations",
        "clusters",
        "prior_dependent",
    }:
        frame[name] = frame[name].astype("Float64")
    return Table(nw.from_native(frame).lazy())


__all__ = [
    "BlockPenalty",
    "DesignTerm",
    "EffectObservation",
    "ModelCoefficient",
    "ModelPrediction",
    "ModelStatistic",
    "ModelUncertainty",
    "additive_cluster_uncertainty",
    "additive_statistics",
    "categorical_design",
    "cluster_score_statistics",
    "fit_additive_model",
    "predict_additive_model",
]
