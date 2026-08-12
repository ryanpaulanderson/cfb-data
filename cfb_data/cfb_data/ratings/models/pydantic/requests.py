"""Validate request parameters for implemented Ratings endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import Classification, SeasonType


class _RatingsRequest(BaseModel):
    """Apply the closed-object contract shared by Ratings requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class _YearOrTeamRequest(_RatingsRequest):
    """Require a season or team selector for a Ratings route."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team selector."""
        if self.year is None and self.team is None:
            raise ValueError("year is required when team is not specified")
        return self


class CoreRatingsRequest(_YearOrTeamRequest):
    """Validate filters accepted by ``GET /ratings/core``."""

    conference: str | None = Field(default=None, min_length=1)


class SPRatingsRequest(_YearOrTeamRequest):
    """Validate filters accepted by ``GET /ratings/sp``."""


class ConferenceSPRatingsRequest(_RatingsRequest):
    """Validate filters accepted by ``GET /ratings/sp/conferences``."""

    year: int | None = Field(default=None, ge=1869)
    conference: str | None = Field(default=None, min_length=1)
    classification: Classification | None = None


class SRSRatingsRequest(_YearOrTeamRequest):
    """Validate filters accepted by ``GET /ratings/srs``."""

    conference: str | None = Field(default=None, min_length=1)


class ExpandedSRSRatingsRequest(_YearOrTeamRequest):
    """Validate filters accepted by ``GET /ratings/srs/expanded``."""

    conference: str | None = Field(default=None, min_length=1)
    classification: Classification | None = None


class EloRatingsRequest(_RatingsRequest):
    """Validate filters accepted by ``GET /ratings/elo``."""

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)


class FPIRatingsRequest(_YearOrTeamRequest):
    """Validate filters accepted by ``GET /ratings/fpi``."""

    conference: str | None = Field(default=None, min_length=1)


__all__ = [
    "ConferenceSPRatingsRequest",
    "CoreRatingsRequest",
    "EloRatingsRequest",
    "ExpandedSRSRatingsRequest",
    "FPIRatingsRequest",
    "SPRatingsRequest",
    "SRSRatingsRequest",
]
