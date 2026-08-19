"""Provide the independently authored coach-seasons dataset recipe.

``coach_seasons`` uses detailed season records directly. Continuous tenure is
an explicit bounded enrichment matched by stable coach/team IDs and year. No
per-coach profile calls occur, and nullable record, poll, scoring, interim, and
effective-date evidence remains explicit.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.coaches.models.pydantic.responses import (
    CoachCfpContext,
    CoachDraftContext,
    CoachPollResume,
    CoachRatingContext,
    CoachRecord,
    CoachRecordSplits,
    CoachRecruitingContext,
    CoachScoring,
    CoachTenure,
    DetailedCoachSeason,
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
    revision=1,
    output=CoachSeason,
    deterministic=True,
)
def normalize_coach_seasons(rows: list[DetailedCoachSeason]) -> list[CoachSeason]:
    """Normalize detailed source rows without tenure enrichment.

    :param rows: Validated detailed coach seasons.
    :return: Coach seasons in deterministic year/team/coach order.
    """
    return _sort_rows([_normalize_season(row) for row in rows])


@step(
    id="cfbd.coach_seasons.attach_tenure",
    revision=1,
    output=CoachSeason,
    deterministic=True,
)
def attach_tenure_context(
    rows: list[DetailedCoachSeason],
    tenures: list[CoachTenure],
) -> list[CoachSeason]:
    """Attach one ID- and year-matched tenure to every season row.

    :param rows: Validated detailed coach seasons.
    :param tenures: Validated continuous coaching tenures.
    :return: Enriched coach seasons in deterministic order.
    :raises ValueError: If tenure coverage is missing or ambiguous.
    """
    result: list[CoachSeason] = []
    for row in rows:
        matches = [
            tenure
            for tenure in tenures
            if tenure.coach.id == row.coach.id
            and tenure.team.id == row.team.id
            and tenure.start_year <= row.year
            and (tenure.end_year is None or row.year <= tenure.end_year)
        ]
        if len(matches) != 1:
            raise ValueError("Requested tenure context is missing or ambiguous")
        result.append(_normalize_season(row, tenure=matches[0]))
    return _sort_rows(result)


@dataset(
    id="cfbd.coach_seasons",
    revision=1,
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
) -> RecipeRef[list[CoachSeason]]:
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


def _normalize_season(
    row: DetailedCoachSeason,
    *,
    tenure: CoachTenure | None = None,
) -> CoachSeason:
    return CoachSeason(
        year=row.year,
        team_id=row.team.id,
        school=row.team.school,
        conference=row.team.conference,
        coach_id=row.coach.id,
        coach_first_name=row.coach.first_name,
        coach_last_name=row.coach.last_name,
        games=row.games,
        wins=row.wins,
        losses=row.losses,
        ties=row.ties,
        win_percentage=row.win_percentage,
        preseason_rank=row.preseason_rank,
        postseason_rank=row.postseason_rank,
        srs=row.srs,
        sp_overall=row.sp_overall,
        sp_offense=row.sp_offense,
        sp_defense=row.sp_defense,
        team_metrics=row.team_metrics,
        recruiting=row.recruiting,
        poll_resume=row.poll_resume,
        attribution_complete=row.attribution_complete,
        record_splits=row.record_splits,
        scoring=row.scoring,
        cfp=row.cfp,
        draft_following_season=row.draft_following_season,
        tenure_coverage=(
            TenureCoverage.present
            if tenure is not None
            else TenureCoverage.not_requested
        ),
        tenure_id=tenure.id if tenure is not None else None,
        hire_date=tenure.hire_date if tenure is not None else None,
        tenure_start_year=tenure.start_year if tenure is not None else None,
        tenure_end_year=tenure.end_year if tenure is not None else None,
        effective_start=tenure.effective_start if tenure is not None else None,
        effective_end=tenure.effective_end if tenure is not None else None,
        is_interim=tenure.is_interim if tenure is not None else None,
        tenure_active=tenure.active if tenure is not None else None,
        tenure_seasons=tenure.seasons if tenure is not None else None,
        tenure_record=tenure.record if tenure is not None else None,
        tenure_attribution_complete=(
            tenure.attribution_complete if tenure is not None else None
        ),
    )


def _sort_rows(rows: list[CoachSeason]) -> list[CoachSeason]:
    return sorted(rows, key=lambda row: (row.year, row.team_id, row.coach_id))


__all__ = ["CoachSeason", "TenureCoverage", "coach_seasons"]
