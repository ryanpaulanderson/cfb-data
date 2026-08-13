"""Validate request parameters for implemented Rankings endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import RankingPoll, SeasonType


class RankingsRequest(BaseModel):
    """Validate filters accepted by ``GET /rankings``."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    week: int | None = Field(default=None, ge=0)
    poll: RankingPoll | None = None
    latest: bool | None = None
    final: bool | None = None

    @model_validator(mode="after")
    def validate_snapshot_selectors(self) -> Self:
        """Require coherent CFP snapshot selectors."""
        if self.latest is True and self.final is True:
            raise ValueError("latest and final cannot both be true")
        if (
            self.latest is True or self.final is True
        ) and self.poll is not RankingPoll.cfp:
            raise ValueError("poll='cfp' is required when latest or final is true")
        return self


__all__ = ["RankingsRequest"]
