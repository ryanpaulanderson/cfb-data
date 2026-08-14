"""Validate responses from implemented CFBD Coaches endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data._catalog.models import CoachFact, CoachTeamSeasonFact, TeamSeasonFact
from cfb_data._catalog.projection import (
    CatalogSink,
    ObservationAuthority,
    ProjectionContext,
    observe_team,
)


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Coaches responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def require_utc_datetimes(cls, value: object) -> object:
        """Require aware response timestamps and normalize them to UTC."""
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Response timestamps must be timezone-aware")
        return value.astimezone(UTC)


class CoachSeason(_ResponseModel):
    """Represent one season in the historical coach summary route."""

    team_id: int = Field(alias="teamId", gt=0)
    school: str
    conference: str | None
    year: int = Field(ge=1869)
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)
    win_percentage: float | None = Field(alias="winPercentage", ge=0, le=1)
    preseason_rank: int | None = Field(alias="preseasonRank", ge=1)
    postseason_rank: int | None = Field(alias="postseasonRank", ge=1)
    srs: float | None
    sp_overall: float | None = Field(alias="spOverall")
    sp_offense: float | None = Field(alias="spOffense")
    sp_defense: float | None = Field(alias="spDefense")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project the team and season carried by a coach summary."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        observe_team(sink, id=self.team_id, school=self.school, source=source)
        sink.add(
            TeamSeasonFact(self.team_id, self.year, self.conference), source=source
        )


class Coach(_ResponseModel):
    """Represent one historical head coach and selected seasons."""

    id: int = Field(gt=0)
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    hire_date: datetime | None = Field(alias="hireDate")
    seasons: list[CoachSeason]

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one coach and all selected coach-team seasons."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        name = " ".join(part for part in (self.first_name, self.last_name) if part)
        sink.add(
            CoachFact(self.id, name),
            authority=ObservationAuthority.canonical,
            source=source,
        )
        for season in self.seasons:
            sink.add(
                CoachTeamSeasonFact(self.id, season.team_id, season.year, season.year),
                source=source,
            )


class CoachRecord(_ResponseModel):
    """Represent an attributed coaching win-loss record."""

    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)
    win_percentage: float | None = Field(alias="winPercentage", ge=0, le=1)


class CoachReference(_ResponseModel):
    """Represent the canonical identity of a coach."""

    id: int = Field(gt=0)
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one canonical coach reference."""
        sink.add(
            CoachFact(self.id, f"{self.first_name} {self.last_name}".strip()),
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class CoachTeamReference(_ResponseModel):
    """Represent a team associated with a coach."""

    id: int = Field(gt=0)
    school: str

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one team referenced by coaching data."""
        observe_team(
            sink,
            id=self.id,
            school=self.school,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class CoachSeasonTeamReference(CoachTeamReference):
    """Represent a team and conference within one coaching season."""

    conference: str | None


class CoachCareer(CoachRecord):
    """Represent career totals in a coach profile."""

    seasons: int = Field(ge=0)
    teams: int = Field(ge=0)
    first_year: int = Field(alias="firstYear", ge=1869)
    last_year: int = Field(alias="lastYear", ge=1869)


class CoachAlmaMater(_ResponseModel):
    """Represent a coach's alma mater."""

    id: int = Field(gt=0)
    school: str

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project the provider team used as a coach's alma mater."""
        observe_team(
            sink,
            id=self.id,
            school=self.school,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class CoachProfile(_ResponseModel):
    """Represent canonical identity and career totals for one coach."""

    id: int = Field(gt=0)
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    display_name: str | None = Field(alias="displayName")
    current_team: CoachSeasonTeamReference | None = Field(alias="currentTeam")
    career: CoachCareer
    birth_date: str | None = Field(alias="birthDate")
    alma_mater: CoachAlmaMater | None = Field(alias="almaMater")
    graduation_year: int | None = Field(alias="graduationYear", ge=1869)
    wikidata_id: str | None = Field(alias="wikidataId")
    hall_of_fame_year: int | None = Field(alias="hallOfFameYear", ge=1869)

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project the authoritative coach profile identity."""
        name = self.display_name or f"{self.first_name} {self.last_name}".strip()
        sink.add(
            CoachFact(self.id, name, self.wikidata_id),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class CoachTenure(_ResponseModel):
    """Represent one continuous head-coaching tenure."""

    id: int = Field(gt=0)
    coach: CoachReference
    team: CoachTeamReference
    hire_date: str | None = Field(alias="hireDate")
    start_year: int = Field(alias="startYear", ge=1869)
    end_year: int | None = Field(alias="endYear", ge=1869)
    effective_start: datetime | None = Field(alias="effectiveStart")
    effective_end: datetime | None = Field(alias="effectiveEnd")
    is_interim: bool = Field(alias="isInterim")
    active: bool
    seasons: int = Field(ge=0)
    record: CoachRecord
    attribution_complete: bool = Field(alias="attributionComplete")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one continuous coach-team tenure."""
        sink.add(
            CoachTeamSeasonFact(
                self.coach.id,
                self.team.id,
                self.start_year,
                self.end_year,
                self.id,
            ),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class CoachYearOverYear(_ResponseModel):
    """Represent change from the preceding team season."""

    wins: int | None
    srs: float | None
    sp_overall: float | None = Field(alias="spOverall")


class CoachRatingContext(_ResponseModel):
    """Represent team rating context for a coaching season."""

    sp_special_teams: float | None = Field(alias="spSpecialTeams")
    strength_of_schedule: float | None = Field(alias="strengthOfSchedule")
    second_order_wins: float | None = Field(alias="secondOrderWins")
    fpi: float | None
    year_over_year: CoachYearOverYear = Field(alias="yearOverYear")


class CoachRecruitingContext(_ResponseModel):
    """Represent recruiting context for a coaching season."""

    rank: int | None = Field(ge=1)
    points: float | None
    talent: float | None


class CoachPollResume(_ResponseModel):
    """Represent poll résumé totals for a coaching season."""

    preseason_rank: int | None = Field(alias="preseasonRank", ge=1)
    postseason_rank: int | None = Field(alias="postseasonRank", ge=1)
    best_rank: int | None = Field(alias="bestRank", ge=1)
    weeks_ranked: int = Field(alias="weeksRanked", ge=0)
    weeks_top_ten: int = Field(alias="weeksTopTen", ge=0)


class CoachRecordSplits(_ResponseModel):
    """Represent coaching records split by game context."""

    conference: CoachRecord
    postseason: CoachRecord
    home: CoachRecord
    away: CoachRecord
    neutral: CoachRecord


class CoachScoring(_ResponseModel):
    """Represent aggregate scoring under a coach for one season."""

    points_for: int = Field(alias="pointsFor", ge=0)
    points_against: int = Field(alias="pointsAgainst", ge=0)
    average_point_differential: float | None = Field(alias="averagePointDifferential")


class CoachCfpOutcome(StrEnum):
    """Identify a coach's College Football Playoff season outcome."""

    active = "active"
    eliminated = "eliminated"
    champion = "champion"


class CoachCfpContext(_ResponseModel):
    """Represent College Football Playoff context for a coaching season."""

    appeared: bool
    seed: int | None = Field(ge=1)
    outcome: CoachCfpOutcome | None


class CoachDraftContext(_ResponseModel):
    """Represent draft outcomes following a coaching season."""

    year: int = Field(ge=1936)
    total_picks: int = Field(alias="totalPicks", ge=0)
    first_round_picks: int = Field(alias="firstRoundPicks", ge=0)


class DetailedCoachSeason(CoachRecord):
    """Represent one coach-season with results and team context."""

    coach: CoachReference
    team: CoachSeasonTeamReference
    year: int = Field(ge=1869)
    preseason_rank: int | None = Field(alias="preseasonRank", ge=1)
    postseason_rank: int | None = Field(alias="postseasonRank", ge=1)
    srs: float | None
    sp_overall: float | None = Field(alias="spOverall")
    sp_offense: float | None = Field(alias="spOffense")
    sp_defense: float | None = Field(alias="spDefense")
    team_metrics: CoachRatingContext = Field(alias="teamMetrics")
    recruiting: CoachRecruitingContext
    poll_resume: CoachPollResume | None = Field(alias="pollResume")
    attribution_complete: bool = Field(alias="attributionComplete")
    record_splits: CoachRecordSplits | None = Field(alias="recordSplits")
    scoring: CoachScoring | None
    cfp: CoachCfpContext
    draft_following_season: CoachDraftContext | None = Field(
        alias="draftFollowingSeason"
    )

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one explicit coach-team season relationship."""
        sink.add(
            CoachTeamSeasonFact(self.coach.id, self.team.id, self.year, self.year),
            authority=ObservationAuthority.canonical,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


__all__ = [
    "Coach",
    "CoachAlmaMater",
    "CoachCareer",
    "CoachCfpContext",
    "CoachCfpOutcome",
    "CoachDraftContext",
    "CoachPollResume",
    "CoachProfile",
    "CoachRatingContext",
    "CoachRecord",
    "CoachRecordSplits",
    "CoachRecruitingContext",
    "CoachReference",
    "CoachScoring",
    "CoachSeason",
    "CoachSeasonTeamReference",
    "CoachTeamReference",
    "CoachTenure",
    "CoachYearOverYear",
    "DetailedCoachSeason",
]
