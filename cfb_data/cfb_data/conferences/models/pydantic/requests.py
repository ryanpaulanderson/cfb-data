"""Validate request parameters for implemented Conferences endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .responses import ConferenceClassification


class ConferencesRequest(BaseModel):
    """Validate filters accepted by ``GET /conferences``.

    :param year: Season used to calculate membership.
    :param classification: Conference division classification.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    classification: ConferenceClassification | None = None


class ConferenceChangesRequest(BaseModel):
    """Validate filters accepted by ``GET /conferences/changes``.

    :param year: Season whose effective conference changes are returned.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)


class ConferenceAffiliationsRequest(BaseModel):
    """Validate filters accepted by ``GET /conferences/affiliations``.

    :param team: Team school name or abbreviation.
    :param conference: Conference name or abbreviation.
    :param year: Exact active-affiliation season.
    :param min_year: Earliest overlapping affiliation season.
    :param max_year: Latest overlapping affiliation season.
    :param classification: Conference division classification.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    team: str | None = None
    conference: str | None = None
    year: int | None = Field(default=None, ge=1869)
    min_year: int | None = Field(default=None, ge=1869, alias="minYear")
    max_year: int | None = Field(default=None, ge=1869, alias="maxYear")
    classification: ConferenceClassification | None = None

    @model_validator(mode="after")
    def validate_year_filters(self) -> Self:
        """Reject mutually exclusive and reversed season filters."""
        if self.year is not None and (
            self.min_year is not None or self.max_year is not None
        ):
            raise ValueError("year cannot be combined with min_year or max_year")
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year cannot be greater than max_year")
        return self
