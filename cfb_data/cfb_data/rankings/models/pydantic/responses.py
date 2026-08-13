"""Validate responses from implemented CFBD Rankings endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import SeasonType


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Rankings responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PollRank(_ResponseModel):
    """Represent one team's position within a poll snapshot."""

    rank: int | None = Field(ge=1)
    team_id: int = Field(alias="teamId", gt=0)
    school: str
    conference: str | None
    first_place_votes: int | None = Field(alias="firstPlaceVotes", ge=0)
    points: int | None = Field(ge=0)


class Poll(_ResponseModel):
    """Represent one named poll and its ranked teams."""

    poll: str
    is_final: bool | None = Field(alias="isFinal")
    ranks: list[PollRank]


class PollWeek(_ResponseModel):
    """Represent all returned polls for one season week."""

    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    polls: list[Poll]


__all__ = ["Poll", "PollRank", "PollWeek"]
