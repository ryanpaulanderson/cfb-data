"""Validate request parameters for implemented Coaches endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _require_ascending_years(min_year: int | None, max_year: int | None) -> None:
    """Require an optional year range to be ascending."""
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("min_year must be less than or equal to max_year")


class _CoachesRequest(BaseModel):
    """Apply the closed-object contract shared by Coaches requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CoachesRequest(_CoachesRequest):
    """Validate filters accepted by ``GET /coaches``."""

    first_name: str | None = Field(default=None, alias="firstName", min_length=1)
    last_name: str | None = Field(default=None, alias="lastName", min_length=1)
    team: str | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, ge=1869)
    min_year: int | None = Field(default=None, alias="minYear", ge=1869)
    max_year: int | None = Field(default=None, alias="maxYear", ge=1869)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        """Require the season range to be ascending."""
        _require_ascending_years(self.min_year, self.max_year)
        return self


class CoachProfileRequest(_CoachesRequest):
    """Validate filters accepted by ``GET /coaches/profile``."""

    coach_id: int = Field(alias="coachId", gt=0)


class CoachSeasonsRequest(_CoachesRequest):
    """Validate filters accepted by ``GET /coaches/seasons``."""

    coach_id: int | None = Field(default=None, alias="coachId", gt=0)
    team: str | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, ge=1869)
    min_year: int | None = Field(default=None, alias="minYear", ge=1869)
    max_year: int | None = Field(default=None, alias="maxYear", ge=1869)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        """Require the season range to be ascending."""
        _require_ascending_years(self.min_year, self.max_year)
        return self


class CoachTenuresRequest(_CoachesRequest):
    """Validate filters accepted by ``GET /coaches/tenures``."""

    coach_id: int | None = Field(default=None, alias="coachId", gt=0)
    team: str | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, ge=1869)
    active: bool | None = None


__all__ = [
    "CoachesRequest",
    "CoachProfileRequest",
    "CoachSeasonsRequest",
    "CoachTenuresRequest",
]
