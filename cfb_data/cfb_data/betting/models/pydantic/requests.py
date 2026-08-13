"""Validate request parameters for implemented Betting endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data._request_rules import _validate_year_or_game_id
from cfb_data.enums import SeasonType


class BettingLinesRequest(BaseModel):
    """Validate filters accepted by ``GET /lines``."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_id: int | None = Field(default=None, alias="gameId", gt=0)
    year: int | None = Field(default=None, ge=1869)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    week: int | None = Field(default=None, ge=0)
    team: str | None = Field(default=None, min_length=1)
    home: str | None = Field(default=None, min_length=1)
    away: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    provider: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or game identifier."""
        _validate_year_or_game_id(self.year, self.game_id)
        return self


__all__ = ["BettingLinesRequest"]
