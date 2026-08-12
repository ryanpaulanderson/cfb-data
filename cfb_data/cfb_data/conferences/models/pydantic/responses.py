"""Validate responses from implemented CFBD Conferences endpoints."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConferenceClassification(StrEnum):
    """Identify an official conference division classification."""

    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    ii_or_iii = "ii/iii"
    iii = "iii"


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to response models."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Conference(_ResponseModel):
    """Represent a conference and its membership count."""

    id: int = Field(gt=0)
    name: str
    short_name: str | None = Field(alias="shortName")
    abbreviation: str | None
    classification: ConferenceClassification | None
    member_count: int = Field(alias="memberCount", ge=0)


class TeamConferenceAffiliation(_ResponseModel):
    """Represent one historical team-to-conference affiliation."""

    team_id: int = Field(alias="teamId", gt=0)
    team: str
    conference_id: int = Field(alias="conferenceId", gt=0)
    conference: str
    conference_abbreviation: str | None = Field(alias="conferenceAbbreviation")
    classification: ConferenceClassification | None
    conference_division: str | None = Field(alias="conferenceDivision")
    start_year: int = Field(alias="startYear", ge=1869)
    end_year: int | None = Field(alias="endYear", ge=1869)


class TeamConferenceChange(_ResponseModel):
    """Represent one team's conference change for a season."""

    team_id: int = Field(alias="teamId", gt=0)
    team: str
    from_conference_id: int = Field(alias="fromConferenceId", gt=0)
    from_conference: str = Field(alias="fromConference")
    from_conference_abbreviation: str | None = Field(alias="fromConferenceAbbreviation")
    from_classification: ConferenceClassification | None = Field(
        alias="fromClassification"
    )
    to_conference_id: int = Field(alias="toConferenceId", gt=0)
    to_conference: str = Field(alias="toConference")
    to_conference_abbreviation: str | None = Field(alias="toConferenceAbbreviation")
    to_classification: ConferenceClassification | None = Field(alias="toClassification")
    effective_year: int = Field(alias="effectiveYear", ge=1869)
