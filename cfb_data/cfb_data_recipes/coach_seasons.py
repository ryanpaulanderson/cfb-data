"""Provide the independently authored coach-seasons dataset recipe.

``coach_seasons`` uses detailed season records directly. Continuous tenure is
an explicit bounded enrichment matched by stable coach/team IDs and year. No
per-coach profile calls occur, and nullable record, poll, scoring, interim, and
effective-date evidence remains explicit.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.coaches.models.pydantic.responses import (
    CoachCfpContext,
    CoachDraftContext,
    CoachPollResume,
    CoachRatingContext,
    CoachRecord,
    CoachRecordSplits,
    CoachRecruitingContext,
    CoachScoring,
)
from cfb_data.coaches.sources import coach_seasons as coach_seasons_source
from cfb_data.coaches.sources import coach_tenures
from pydantic import BaseModel, ConfigDict, Field


class TenureCoverage(StrEnum):
    """Describe whether continuous-tenure context was requested."""

    not_requested = "not_requested"
    present = "present"


class CoachSeason(BaseModel):
    """Represent one directly attributed coach/team season."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    year: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    team_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    school: str = Field(json_schema_extra={"semantic_type": "dimension"})
    conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    coach_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    coach_first_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    coach_last_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    games: int = Field(ge=0, json_schema_extra={"semantic_type": "measure"})
    wins: int = Field(ge=0, json_schema_extra={"semantic_type": "measure"})
    losses: int = Field(ge=0, json_schema_extra={"semantic_type": "measure"})
    ties: int = Field(ge=0, json_schema_extra={"semantic_type": "measure"})
    win_percentage: float | None = Field(default=None, ge=0, le=1)
    preseason_rank: int | None = Field(default=None, ge=1)
    postseason_rank: int | None = Field(default=None, ge=1)
    srs: float | None = None
    sp_overall: float | None = None
    sp_offense: float | None = None
    sp_defense: float | None = None
    team_metrics: CoachRatingContext
    recruiting: CoachRecruitingContext
    poll_resume: CoachPollResume | None = None
    attribution_complete: bool
    record_splits: CoachRecordSplits | None = None
    scoring: CoachScoring | None = None
    cfp: CoachCfpContext
    draft_following_season: CoachDraftContext | None = None
    tenure_coverage: TenureCoverage
    tenure_id: int | None = Field(
        default=None,
        gt=0,
        json_schema_extra={"semantic_type": "identifier"},
    )
    hire_date: str | None = None
    tenure_start_year: int | None = Field(default=None, ge=1869)
    tenure_end_year: int | None = Field(default=None, ge=1869)
    effective_start: datetime | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "time"},
    )
    effective_end: datetime | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "time"},
    )
    is_interim: bool | None = None
    tenure_active: bool | None = None
    tenure_seasons: int | None = Field(default=None, ge=0)
    tenure_record: CoachRecord | None = None
    tenure_attribution_complete: bool | None = None


@step(
    id="cfbd.coach_seasons.normalize",
    revision=2,
    output=CoachSeason,
    deterministic=True,
)
def normalize_coach_seasons(rows: Table) -> Table:
    """Project attributed coach seasons through native expressions.

    :param rows: Validated detailed season table.
    :return: Ordered native coach seasons with omitted tenure evidence.
    """
    base = _coach_context(rows).with_columns(
        nw.lit("not_requested").alias("tenure_coverage")
    )
    for name in CoachSeason.model_fields:
        if name not in base.columns:
            base = base.with_columns(nw.lit(None).alias(name))
    return base.select(*CoachSeason.model_fields).sort("year", "team_id", "coach_id")


@step(
    id="cfbd.coach_seasons.attach_tenure",
    revision=2,
    output=CoachSeason,
    deterministic=True,
)
def attach_tenure_context(rows: Table, tenures: Table) -> Table:
    """Match tenure intervals with native keyed joins and global cardinality.

    :param rows: Validated attributed coach seasons.
    :param tenures: Validated continuous coaching tenures.
    :return: Native coach seasons with exactly one matching tenure each.
    """
    base = _coach_context(rows)
    evidence = tenures.nested("coach", fields={"id": "coach_id"}).nested(
        "team", fields={"id": "team_id"}
    )
    aliases = {
        "id": "tenure_id",
        "start_year": "tenure_start_year",
        "end_year": "tenure_end_year",
        "active": "tenure_active",
        "seasons": "tenure_seasons",
        "record": "tenure_record",
        "attribution_complete": "tenure_attribution_complete",
    }
    evidence = evidence.rename(aliases)
    fields = tuple(
        name
        for name in CoachSeason.model_fields
        if name in evidence.columns and name not in base.columns
    )
    matches = (
        base.select("year", "team_id", "coach_id")
        .join(
            evidence.select("team_id", "coach_id", *fields),
            on=("team_id", "coach_id"),
            cardinality="many_to_many",
            how="inner",
        )
        .filter(
            (nw.col("tenure_start_year") <= nw.col("year"))
            & (
                nw.col("tenure_end_year").is_null()
                | (nw.col("year") <= nw.col("tenure_end_year"))
            )
        )
    )
    keys = ("year", "team_id", "coach_id")
    matches = matches.require_unique(
        keys, message="Requested tenure context is missing or ambiguous"
    ).with_columns(nw.lit(True).alias("__tenure_match"))
    joined = base.join(matches, on=keys, cardinality="one_to_one").require(
        nw.col("__tenure_match").fill_null(False),
        message="Requested tenure context is missing or ambiguous",
    )
    return (
        joined.with_columns(nw.lit("present").alias("tenure_coverage"))
        .select(*CoachSeason.model_fields)
        .sort(*keys)
    )


@dataset(
    id="cfbd.coach_seasons",
    revision=2,
    row=CoachSeason,
    grain="one directly attributed coach/team season",
    keys=("year", "team_id", "coach_id"),
    order_by=("year", "team_id", "coach_id"),
    partition_by=("year",),
)
def coach_seasons(
    *,
    coach_id: int | None = None,
    team: str | None = None,
    year: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    include_tenure: bool = False,
    active_tenure: bool | None = None,
) -> RecipeRef[Table]:
    """Build detailed coach seasons with optional tenure context.

    :param coach_id: Optional exact coach identifier.
    :param team: Optional team selector.
    :param year: Optional exact season.
    :param min_year: Optional inclusive first season.
    :param max_year: Optional inclusive last season.
    :param include_tenure: Request continuous-tenure context.
    :param active_tenure: Optional active selector for requested tenures.
    :return: A reference to the validated coach-seasons dataset.
    """
    season_rows = coach_seasons_source(
        coach_id=coach_id,
        team=team,
        year=year,
        min_year=min_year,
        max_year=max_year,
    )
    if not include_tenure:
        return normalize_coach_seasons(season_rows)
    return attach_tenure_context(
        season_rows,
        coach_tenures(
            coach_id=coach_id,
            team=team,
            year=year,
            active=active_tenure,
        ),
    )


def _coach_context(rows: Table) -> Table:
    """Project stable coach and team identity from validated source structures."""
    return rows.nested(
        "coach",
        fields={
            "id": "coach_id",
            "first_name": "coach_first_name",
            "last_name": "coach_last_name",
        },
    ).nested(
        "team", fields={"id": "team_id", "school": "school", "conference": "conference"}
    )


__all__ = ["CoachSeason", "TenureCoverage", "coach_seasons"]
