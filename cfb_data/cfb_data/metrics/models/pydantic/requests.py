"""Validate request parameters for implemented Metrics endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import Classification, SeasonType


class _MetricsRequest(BaseModel):
    """Apply the closed-object contract shared by Metrics requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _require_year_or_team(year: int | None, team: str | None) -> None:
    """Require a season or team selector."""
    if year is None and team is None:
        raise ValueError("year is required when team is not specified")


class PredictedPointsRequest(_MetricsRequest):
    """Validate filters accepted by ``GET /ppa/predicted``."""

    down: int = Field(ge=1, le=4)
    distance: int = Field(ge=1, le=99)


class TeamSeasonPPARequest(_MetricsRequest):
    """Validate filters accepted by ``GET /ppa/teams``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team selector."""
        _require_year_or_team(self.year, self.team)
        return self


class TeamGamePPARequest(_MetricsRequest):
    """Validate filters accepted by ``GET /ppa/games``."""

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")
    classification: Classification | None = None


class PlayerGamePPARequest(_MetricsRequest):
    """Validate filters accepted by ``GET /ppa/players/games``."""

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)
    player_id: int | None = Field(default=None, alias="playerId", gt=0)
    threshold: int | None = Field(default=None, ge=0)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a week or team selector."""
        if self.week is None and self.team is None:
            raise ValueError("week is required when team is not specified")
        return self


class PlayerSeasonPPARequest(_MetricsRequest):
    """Validate filters accepted by ``GET /ppa/players/season``."""

    year: int | None = Field(default=None, ge=1869)
    conference: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)
    player_id: int | None = Field(default=None, alias="playerId", gt=0)
    threshold: int | None = Field(default=None, ge=0)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or player selector."""
        if self.year is None and self.player_id is None:
            raise ValueError("year is required when player_id is not specified")
        return self


class WinProbabilityRequest(_MetricsRequest):
    """Validate filters accepted by ``GET /metrics/wp``."""

    game_id: int = Field(alias="gameId", gt=0)


class PregameWinProbabilityRequest(_MetricsRequest):
    """Validate filters accepted by ``GET /metrics/wp/pregame``."""

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = Field(default=None, min_length=1)


__all__ = [
    "PlayerGamePPARequest",
    "PlayerSeasonPPARequest",
    "PredictedPointsRequest",
    "PregameWinProbabilityRequest",
    "TeamGamePPARequest",
    "TeamSeasonPPARequest",
    "WinProbabilityRequest",
]
