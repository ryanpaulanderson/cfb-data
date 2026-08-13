"""Validate responses from implemented CFBD Draft endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Draft responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class DraftTeam(_ResponseModel):
    """Represent an NFL team present in the historical draft data."""

    location: str
    nickname: str | None
    display_name: str | None = Field(alias="displayName")
    logo: str | None


class DraftPosition(_ResponseModel):
    """Represent an NFL Draft position category."""

    name: str
    abbreviation: str


class DraftPickHometown(_ResponseModel):
    """Represent the recorded hometown of an NFL Draft pick."""

    city: str | None
    state: str | None
    country: str | None
    latitude: str | None
    longitude: str | None
    county_fips: str | None = Field(alias="countyFips")


class DraftPick(_ResponseModel):
    """Represent one historical NFL Draft selection."""

    college_athlete_id: int | None = Field(alias="collegeAthleteId", gt=0)
    nfl_athlete_id: int = Field(alias="nflAthleteId", gt=0)
    college_id: int = Field(alias="collegeId", gt=0)
    college_team: str = Field(alias="collegeTeam")
    college_conference: str | None = Field(alias="collegeConference")
    nfl_team_id: int = Field(alias="nflTeamId", gt=0)
    nfl_team: str = Field(alias="nflTeam")
    year: int = Field(ge=1936)
    overall: int = Field(gt=0)
    round: int = Field(gt=0)
    pick: int = Field(gt=0)
    name: str
    position: str
    height: float | None = Field(ge=0)
    weight: int | None = Field(ge=0)
    pre_draft_ranking: int | None = Field(alias="preDraftRanking", gt=0)
    pre_draft_position_ranking: int | None = Field(
        alias="preDraftPositionRanking", gt=0
    )
    pre_draft_grade: int | None = Field(alias="preDraftGrade", ge=0)
    hometown_info: DraftPickHometown = Field(alias="hometownInfo")


__all__ = ["DraftPick", "DraftPickHometown", "DraftPosition", "DraftTeam"]
