"""Validate request parameters for implemented Plays endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import Classification, SeasonType


class PlaysRequest(BaseModel):
    """Validate filters accepted by ``GET /plays``.

    :param year: Required season year.
    :param week: Required non-negative season week.
    :param team: Team appearing on either side of the play.
    :param offense: Offensive-team selector.
    :param defense: Defensive-team selector.
    :param offense_conference: Offensive-team conference selector.
    :param defense_conference: Defensive-team conference selector.
    :param conference: Conference appearing on either side of the play.
    :param play_type: Play-type abbreviation.
    :param season_type: Optional season phase.
    :param classification: Division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)
    week: int = Field(ge=0)
    team: str | None = None
    offense: str | None = None
    defense: str | None = None
    offense_conference: str | None = Field(
        default=None,
        alias="offenseConference",
    )
    defense_conference: str | None = Field(
        default=None,
        alias="defenseConference",
    )
    conference: str | None = None
    play_type: str | None = Field(default=None, alias="playType")
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    classification: Classification | None = None


class PlayStatsRequest(BaseModel):
    """Validate filters accepted by ``GET /plays/stats``.

    The upstream endpoint permits an unfiltered request and limits every
    response to 2,000 rows.

    :param year: Optional season year.
    :param week: Optional non-negative season week.
    :param team: Team selector.
    :param game_id: Positive game identifier.
    :param athlete_id: Positive athlete identifier.
    :param stat_type_id: Positive play-stat type identifier.
    :param season_type: Optional season phase.
    :param conference: Conference name or abbreviation.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    team: str | None = None
    game_id: int | None = Field(default=None, gt=0, serialization_alias="gameId")
    athlete_id: int | None = Field(default=None, gt=0, serialization_alias="athleteId")
    stat_type_id: int | None = Field(
        default=None, gt=0, serialization_alias="statTypeId"
    )
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    conference: str | None = None


class LivePlaysRequest(BaseModel):
    """Validate filters accepted by ``GET /live/plays``.

    :param game_id: Positive game identifier.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_id: int = Field(gt=0, serialization_alias="gameId")
