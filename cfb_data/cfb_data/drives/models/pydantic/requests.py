"""Validate request parameters for the implemented Drives endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import Classification, SeasonType


class DrivesRequest(BaseModel):
    """Validate filters accepted by ``GET /drives``.

    :param year: Required season year.
    :param season_type: Optional season phase.
    :param week: Optional non-negative season week.
    :param team: Team appearing on offense or defense.
    :param offense: Offensive-team selector.
    :param defense: Defensive-team selector.
    :param conference: Conference appearing on offense or defense.
    :param offense_conference: Offensive-team conference selector.
    :param defense_conference: Defensive-team conference selector.
    :param classification: Division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    week: int | None = Field(default=None, ge=0)
    team: str | None = None
    offense: str | None = None
    defense: str | None = None
    conference: str | None = None
    offense_conference: str | None = Field(
        default=None,
        alias="offenseConference",
    )
    defense_conference: str | None = Field(
        default=None,
        alias="defenseConference",
    )
    classification: Classification | None = None
