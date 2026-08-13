"""Validate request parameters for implemented Recruiting endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import RecruitClassification


class _RecruitingRequest(BaseModel):
    """Apply the closed-object contract shared by Recruiting requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class RecruitingPlayersRequest(_RecruitingRequest):
    """Validate filters accepted by ``GET /recruiting/players``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)
    state: str | None = Field(default=None, min_length=1)
    classification: RecruitClassification | None = None

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a recruiting year or committed team."""
        if self.year is None and self.team is None:
            raise ValueError("year is required when team is not specified")
        return self


class RecruitingTeamsRequest(_RecruitingRequest):
    """Validate filters accepted by ``GET /recruiting/teams``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)


class RecruitingGroupsRequest(_RecruitingRequest):
    """Validate filters accepted by ``GET /recruiting/groups``."""

    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    recruit_type: RecruitClassification | None = Field(
        default=None, alias="recruitType"
    )
    start_year: int | None = Field(default=None, alias="startYear", ge=1869)
    end_year: int | None = Field(default=None, alias="endYear", ge=1869)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        """Require the recruiting year range to be ascending."""
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.start_year > self.end_year
        ):
            raise ValueError("start_year must be less than or equal to end_year")
        return self


__all__ = [
    "RecruitingGroupsRequest",
    "RecruitingPlayersRequest",
    "RecruitingTeamsRequest",
]
