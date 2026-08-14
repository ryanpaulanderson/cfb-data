"""Validate responses from implemented CFBD Players endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data._catalog.projection import (
    CatalogSink,
    ObservationAuthority,
    ProjectionContext,
    observe_athlete,
)
from cfb_data.enums import TransferEligibility
from cfb_data.metrics.models.pydantic.responses import PlayerSeasonPPASplit


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Players responses."""

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


class PlayerSearchTeamStint(_ResponseModel):
    """Represent one continuous period with a team."""

    team: str
    start_year: int | None = Field(alias="startYear", ge=1869)
    end_year: int | None = Field(alias="endYear", ge=1869)


class PlayerSearchResult(_ResponseModel):
    """Represent one player matching a name search."""

    id: str
    team: str
    name: str
    first_name: str | None = Field(alias="firstName")
    last_name: str | None = Field(alias="lastName")
    weight: int | None = Field(ge=0)
    height: float | None = Field(ge=0)
    jersey: int | None = Field(ge=0)
    position: str
    hometown: str
    team_color: str = Field(alias="teamColor")
    team_color_secondary: str = Field(alias="teamColorSecondary")
    active_start_year: int | None = Field(alias="activeStartYear", ge=1869)
    active_end_year: int | None = Field(alias="activeEndYear", ge=1869)
    team_stints: list[PlayerSearchTeamStint] = Field(alias="teamStints")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project a player and every explicit team-season stint."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        year = context.parameters.get("year")
        request_season = (
            year if isinstance(year, int) and not isinstance(year, bool) else None
        )
        observe_athlete(
            sink,
            id=self.id,
            name=self.name,
            position=self.position,
            team=self.team,
            season=request_season,
            authority=ObservationAuthority.canonical,
            source=source,
        )
        for stint in self.team_stints:
            if stint.start_year is None:
                continue
            end_year = stint.end_year or self.active_end_year
            if end_year is None or end_year < stint.start_year:
                continue
            if end_year - stint.start_year > 100:
                continue
            for season in range(stint.start_year, end_year + 1):
                observe_athlete(
                    sink,
                    id=self.id,
                    name=self.name,
                    position=self.position,
                    team=stint.team,
                    season=season,
                    authority=ObservationAuthority.canonical,
                    source=source,
                )


class PlayerUsageSplit(_ResponseModel):
    """Represent a player's share of team plays by context."""

    overall: float | None = Field(ge=0)
    passing: float | None = Field(alias="pass", ge=0)
    rush: float | None = Field(ge=0)
    first_down: float | None = Field(alias="firstDown", ge=0)
    second_down: float | None = Field(alias="secondDown", ge=0)
    third_down: float | None = Field(alias="thirdDown", ge=0)
    standard_downs: float | None = Field(alias="standardDowns", ge=0)
    passing_downs: float | None = Field(alias="passingDowns", ge=0)


class PlayerUsage(_ResponseModel):
    """Represent one player's season usage metrics."""

    season: int = Field(ge=1869)
    id: str
    name: str
    position: str
    team: str
    conference: str
    usage: PlayerUsageSplit

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project a season-scoped athlete identity."""
        observe_athlete(
            sink,
            id=self.id,
            name=self.name,
            position=self.position,
            team=self.team,
            season=self.season,
            authority=ObservationAuthority.canonical,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class PlayerSeasonOverviewStat(_ResponseModel):
    """Represent one display statistic in a season overview."""

    name: str
    value: str


class PlayerSeasonOverviewCategory(_ResponseModel):
    """Group season-overview statistics by category."""

    name: str
    stats: list[PlayerSeasonOverviewStat]


class PlayerSeasonOverviewBoxScore(_ResponseModel):
    """Represent categorized box-score statistics in a season overview."""

    categories: list[PlayerSeasonOverviewCategory]


class PlayerSeasonOverviewPPA(_ResponseModel):
    """Represent average and total PPA in a player season overview."""

    average: PlayerSeasonPPASplit
    total: PlayerSeasonPPASplit


class PlayerSeasonOverview(_ResponseModel):
    """Represent one player's combined season overview."""

    season: int = Field(ge=1869)
    id: str
    name: str
    position: str
    team: str
    conference: str
    games: int = Field(ge=0)
    box_score_stats: PlayerSeasonOverviewBoxScore = Field(alias="boxScoreStats")
    usage: PlayerUsageSplit | None = None
    ppa: PlayerSeasonOverviewPPA | None = None

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project the overview's exact athlete membership."""
        observe_athlete(
            sink,
            id=self.id,
            name=self.name,
            position=self.position,
            team=self.team,
            season=self.season,
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class ReturningProduction(_ResponseModel):
    """Represent one team's returning production metrics."""

    season: int = Field(ge=1869)
    team: str
    conference: str
    total_ppa: float = Field(alias="totalPPA")
    total_passing_ppa: float = Field(alias="totalPassingPPA")
    total_receiving_ppa: float = Field(alias="totalReceivingPPA")
    total_rushing_ppa: float = Field(alias="totalRushingPPA")
    percent_ppa: float = Field(alias="percentPPA")
    percent_passing_ppa: float = Field(alias="percentPassingPPA")
    percent_receiving_ppa: float = Field(alias="percentReceivingPPA")
    percent_rushing_ppa: float = Field(alias="percentRushingPPA")
    usage: float
    passing_usage: float = Field(alias="passingUsage")
    receiving_usage: float = Field(alias="receivingUsage")
    rushing_usage: float = Field(alias="rushingUsage")


class PlayerTransfer(_ResponseModel):
    """Represent one transfer portal entry."""

    season: int = Field(ge=1869)
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    position: str
    origin: str
    destination: str | None
    transfer_date: datetime | None = Field(alias="transferDate")
    rating: float | None
    stars: int | None = Field(ge=0, le=5)
    eligibility: TransferEligibility | None


__all__ = [
    "PlayerSearchResult",
    "PlayerSearchTeamStint",
    "PlayerSeasonOverview",
    "PlayerSeasonOverviewBoxScore",
    "PlayerSeasonOverviewCategory",
    "PlayerSeasonOverviewPPA",
    "PlayerSeasonOverviewStat",
    "PlayerTransfer",
    "PlayerUsage",
    "PlayerUsageSplit",
    "ReturningProduction",
]
