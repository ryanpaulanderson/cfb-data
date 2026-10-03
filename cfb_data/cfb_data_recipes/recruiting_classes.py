"""Provide the independently authored recruiting-classes dataset recipe.

``recruiting_classes`` unions validated team rankings with individual recruit
commitments. Ranked teams with no returned commitments and commitment-only
teams both survive. Recruits without a commitment are retained in one explicit
uncommitted class bucket rather than dropped or assigned to a team.
"""

from __future__ import annotations

from enum import StrEnum

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.analytics.tables import SOURCE_ORDINAL
from cfb_data.enums import RecruitClassification
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
)
from cfb_data.recruiting.sources import recruiting_players, recruiting_teams
from pydantic import BaseModel, ConfigDict, Field


class RecruitingClassStatus(StrEnum):
    """Classify how a recruiting-class row entered the union."""

    ranked = "ranked"
    commitments_only = "commitments_only"
    uncommitted = "uncommitted"


class RecruitingClass(BaseModel):
    """Represent one team class or explicit uncommitted bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    class_year: int = Field(
        ge=1869,
        json_schema_extra={"semantic_type": "dimension"},
    )
    class_key: str = Field(
        description="Stable normalized team or uncommitted identity within a year.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    class_ordinal: int = Field(
        ge=0,
        description="Deterministic rank-aware class order within the year.",
    )
    source_team: str | None = Field(
        default=None,
        description="Source team name; null only for the uncommitted bucket.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    status: RecruitingClassStatus
    rank: int | None = Field(
        default=None,
        ge=1,
        json_schema_extra={"semantic_type": "measure"},
    )
    points: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    recruits: list[Recruit] = Field(
        description="Validated recruits preserved in source order."
    )
    recruit_count: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "recruits"},
    )


@step(
    id="cfbd.recruiting_classes.compose",
    revision=2,
    output=RecruitingClass,
    deterministic=True,
)
def compose_recruiting_classes(rankings: Table, recruits: Table) -> Table:
    """Compose recruiting classes with native grouping and an outer join.

    :param rankings: Validated team-ranking table.
    :param recruits: Validated recruit table retaining source ordinals.
    :return: Native class table with globally checked identity and ordering.
    """
    keys = ("class_year", "class_key")
    ranked = (
        rankings.normalize_text("team", into="__team_key")
        .with_columns(
            nw.col("year").alias("class_year"),
            nw.concat_str(nw.lit("team:"), nw.col("__team_key")).alias("class_key"),
            nw.lit(True).alias("__ranked"),
        )
        .select(
            "class_year",
            "class_key",
            nw.col("team").alias("__ranked_team"),
            "rank",
            "points",
            "__ranked",
        )
    )
    ranked = ranked.require_unique(
        keys, message="Recruiting rankings contain duplicate team classes"
    )
    commitments = recruits.require_unique(
        ("id",), message="Recruiting players contain duplicate recruit IDs"
    )
    commitments = commitments.normalize_text(
        "committed_to", into="__team_key"
    ).with_columns(
        nw.col("year").alias("class_year"),
        nw.when(nw.col("committed_to").is_null())
        .then(nw.lit("uncommitted"))
        .otherwise(nw.concat_str(nw.lit("team:"), nw.col("__team_key")))
        .alias("class_key"),
    )
    records = commitments.pack(
        columns={
            **{name: name for name in Recruit.model_fields},
            SOURCE_ORDINAL: SOURCE_ORDINAL,
        },
        into="__recruit",
    )
    grouped = records.ordered_records(
        keys=keys, column="__recruit", into="recruits", ordinal_field=SOURCE_ORDINAL
    )
    counts = commitments.aggregate(
        keys=keys,
        expressions=(
            nw.len().alias("recruit_count"),
            nw.col(SOURCE_ORDINAL).min().alias("__first"),
        ),
    )
    first = commitments.select(
        *keys,
        nw.col(SOURCE_ORDINAL).alias("__first"),
        nw.col("committed_to").alias("__committed_team"),
    )
    grouped = (
        grouped.join(counts, on=keys, cardinality="one_to_one")
        .join(first, on=(*keys, "__first"), cardinality="many_to_one")
        .drop("__first")
    )
    classes = ranked.join(grouped, on=keys, how="full", cardinality="one_to_one")
    classes = classes.with_columns(
        nw.when(nw.col("__ranked").fill_null(False))
        .then(nw.col("__ranked_team"))
        .otherwise(nw.col("__committed_team"))
        .alias("source_team"),
        nw.when(nw.col("class_key") == "uncommitted")
        .then(nw.lit("uncommitted"))
        .when(nw.col("__ranked").fill_null(False))
        .then(nw.lit("ranked"))
        .otherwise(nw.lit("commitments_only"))
        .alias("status"),
        nw.col("recruit_count").fill_null(0).cast(nw.Int64).alias("recruit_count"),
        (nw.col("class_key") == "uncommitted").alias("__uncommitted"),
        nw.col("rank").is_null().alias("__rank_null"),
    ).fill_empty_lists("recruits")
    return (
        classes.sort("class_year", "__uncommitted", "__rank_null", "rank", "class_key")
        .with_group_index("class_ordinal", keys=("class_year",))
        .select(*RecruitingClass.model_fields)
    )


@dataset(
    id="cfbd.recruiting_classes",
    revision=2,
    row=RecruitingClass,
    grain="one team recruiting class or uncommitted year bucket",
    keys=("class_year", "class_key"),
    order_by=("class_year", "class_ordinal"),
    partition_by=("class_year",),
)
def recruiting_classes(
    *,
    class_year: int,
    team: str | None = None,
    position: str | None = None,
    state: str | None = None,
    classification: RecruitClassification | None = None,
) -> RecipeRef[Table]:
    """Build recruiting classes from rankings and individual recruits.

    :param class_year: Required recruiting class year.
    :param team: Optional ranked and committed-team selector.
    :param position: Optional recruit position selector.
    :param state: Optional recruit home-state selector.
    :param classification: Optional recruit-type selector.
    :return: A reference to the validated recruiting-classes dataset.
    """
    return compose_recruiting_classes(
        recruiting_teams(year=class_year, team=team),
        recruiting_players(
            year=class_year,
            team=team,
            position=position,
            state=state,
            classification=classification,
        ),
    )


__all__ = ["RecruitingClass", "RecruitingClassStatus", "recruiting_classes"]
