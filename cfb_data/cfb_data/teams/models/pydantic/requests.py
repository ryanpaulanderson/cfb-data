"""Validate request parameters for implemented Teams endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import Classification


class TeamsRequest(BaseModel):
    """Validate filters accepted by ``GET /teams``.

    :param conference: Conference abbreviation.
    :param year: Season used for historical affiliation membership.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    conference: str | None = None
    year: int | None = Field(default=None, ge=1869)


class FBSTeamsRequest(BaseModel):
    """Validate filters accepted by ``GET /teams/fbs``.

    :param year: Season used for historical FBS membership.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    year: int | None = Field(default=None, ge=1869)


class TeamMatchupRequest(BaseModel):
    """Validate filters accepted by ``GET /teams/matchup``.

    :param team1: First team name.
    :param team2: Second team name.
    :param min_year: Earliest season to include.
    :param max_year: Latest season to include.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    team1: str = Field(min_length=1)
    team2: str = Field(min_length=1)
    min_year: int | None = Field(default=None, ge=1869, alias="minYear")
    max_year: int | None = Field(default=None, ge=1869, alias="maxYear")

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        """Reject a reversed matchup season range."""
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year cannot be greater than max_year")
        return self


class TeamATSRequest(BaseModel):
    """Validate filters accepted by ``GET /teams/ats``.

    :param year: Required season year.
    :param conference: Conference name or abbreviation.
    :param team: Team name.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    year: int = Field(ge=1869)
    conference: str | None = None
    team: str | None = None


class RosterRequest(BaseModel):
    """Validate filters accepted by ``GET /roster``.

    :param team: Team name.
    :param year: Roster season, or ``None`` to retain the upstream default.
    :param classification: Division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    team: str | None = None
    year: int | None = Field(default=None, ge=1869)
    classification: Classification | None = None


class TalentRequest(BaseModel):
    """Validate filters accepted by ``GET /talent``.

    :param year: Required talent-composite season.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    year: int = Field(ge=1869)
