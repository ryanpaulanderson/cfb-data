"""Validate request parameters for implemented Playoffs endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import PlayoffRound


class _CfpSeasonRequest(BaseModel):
    """Apply the shared CFP season-selector contract."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=2014)


class CfpPlayoffRequest(_CfpSeasonRequest):
    """Validate filters accepted by ``GET /playoffs/cfp``."""


class CfpParticipantsRequest(_CfpSeasonRequest):
    """Validate filters accepted by ``GET /playoffs/cfp/participants``."""


class CfpGamesRequest(_CfpSeasonRequest):
    """Validate filters accepted by ``GET /playoffs/cfp/games``."""

    round: PlayoffRound | None = None


__all__ = ["CfpGamesRequest", "CfpParticipantsRequest", "CfpPlayoffRequest"]
