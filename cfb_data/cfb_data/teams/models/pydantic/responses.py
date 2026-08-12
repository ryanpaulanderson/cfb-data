"""Validate responses from implemented CFBD Teams endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data.conferences.models.pydantic.responses import ConferenceClassification
from cfb_data.venues.models.pydantic.responses import Venue


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to response models."""

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


class Team(_ResponseModel):
    """Represent one team and its current or historical affiliation."""

    id: int = Field(gt=0)
    school: str
    mascot: str | None
    abbreviation: str | None
    alternate_names: list[str] | None = Field(alias="alternateNames")
    conference: str | None
    division: str | None
    classification: ConferenceClassification | None
    color: str | None
    alternate_color: str | None = Field(alias="alternateColor")
    logos: list[str] | None
    twitter: str | None
    location: Venue | None


class MatchupGame(_ResponseModel):
    """Represent one completed game in a historical matchup."""

    season: int = Field(ge=1869)
    week: int = Field(ge=0)
    season_type: str = Field(alias="seasonType")
    date: datetime
    neutral_site: bool = Field(alias="neutralSite")
    venue: str | None
    home_team: str = Field(alias="homeTeam")
    home_score: int | None = Field(alias="homeScore", ge=0)
    away_team: str = Field(alias="awayTeam")
    away_score: int | None = Field(alias="awayScore", ge=0)
    winner: str | None


class Matchup(_ResponseModel):
    """Represent a matchup summary and its nested completed games."""

    team1: str
    team2: str
    start_year: int | None = Field(default=None, alias="startYear", ge=1869)
    end_year: int | None = Field(default=None, alias="endYear", ge=1869)
    team1_wins: int = Field(alias="team1Wins", ge=0)
    team2_wins: int = Field(alias="team2Wins", ge=0)
    ties: int = Field(ge=0)
    games: list[MatchupGame]


class RosterPlayer(_ResponseModel):
    """Represent one player on a historical team roster."""

    id: str
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    team: str
    height: float | None
    weight: int | None = Field(ge=0)
    jersey: int | None = Field(ge=0)
    year: int = Field(ge=0)
    position: str | None
    home_city: str | None = Field(alias="homeCity")
    home_state: str | None = Field(alias="homeState")
    home_country: str | None = Field(alias="homeCountry")
    home_latitude: float | None = Field(alias="homeLatitude")
    home_longitude: float | None = Field(alias="homeLongitude")
    home_county_fips: str | None = Field(alias="homeCountyFIPS")
    recruit_ids: list[str] | None = Field(alias="recruitIds")


class TeamTalent(_ResponseModel):
    """Represent one team's 247Sports Team Talent Composite rating."""

    year: int = Field(ge=1869)
    team: str
    talent: float


class TeamATS(_ResponseModel):
    """Represent one team's against-the-spread season record."""

    year: int = Field(ge=1869)
    team_id: int = Field(alias="teamId", gt=0)
    team: str
    conference: str | None
    games: int = Field(ge=0)
    ats_wins: int = Field(alias="atsWins", ge=0)
    ats_losses: int = Field(alias="atsLosses", ge=0)
    ats_pushes: int = Field(alias="atsPushes", ge=0)
    avg_cover_margin: float | None = Field(alias="avgCoverMargin")
