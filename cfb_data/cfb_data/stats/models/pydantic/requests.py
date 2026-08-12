"""Validate request parameters for implemented Stats endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.enums import Classification, SeasonType


class _StatsRequest(BaseModel):
    """Apply the closed-object contract shared by Stats requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _validate_week_range(start_week: int | None, end_week: int | None) -> None:
    """Reject a reversed inclusive week range."""
    if start_week is not None and end_week is not None and start_week > end_week:
        raise ValueError("start_week cannot be greater than end_week")


def _validate_year_or_team(year: int | None, team: str | None) -> None:
    """Require a season or team selector."""
    if year is None and team is None:
        raise ValueError("year is required when team is not specified")


class PlayerSeasonStatsRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/player/season``."""

    year: int = Field(ge=1869)
    conference: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    start_week: int | None = Field(default=None, alias="startWeek", ge=0)
    end_week: int | None = Field(default=None, alias="endWeek", ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    category: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_week_range(self) -> Self:
        """Reject a reversed week range."""
        _validate_week_range(self.start_week, self.end_week)
        return self


class PlayerSeasonSuccessRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/player/success``."""

    year: int | None = Field(default=None, ge=1869)
    conference: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    player_id: int | None = Field(default=None, alias="playerId", gt=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    start_week: int | None = Field(default=None, alias="startWeek", ge=0)
    end_week: int | None = Field(default=None, alias="endWeek", ge=0)
    threshold: int | None = Field(default=None, ge=0)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or player and reject a reversed week range."""
        if self.year is None and self.player_id is None:
            raise ValueError("year is required when player_id is not specified")
        _validate_week_range(self.start_week, self.end_week)
        return self


class PlayerGameSuccessRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/player/success/game``."""

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    conference: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    player_id: int | None = Field(default=None, alias="playerId", gt=0)
    threshold: int | None = Field(default=None, ge=0)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a week, team, or player selector."""
        if self.week is None and self.team is None and self.player_id is None:
            raise ValueError("At least one of week, team, or player_id is required")
        return self


class TeamSeasonStatsRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/season``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    start_week: int | None = Field(default=None, alias="startWeek", ge=0)
    end_week: int | None = Field(default=None, alias="endWeek", ge=0)
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team and reject a reversed week range."""
        _validate_year_or_team(self.year, self.team)
        _validate_week_range(self.start_week, self.end_week)
        return self


class AdvancedSeasonStatsRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/season/advanced``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")
    start_week: int | None = Field(default=None, alias="startWeek", ge=0)
    end_week: int | None = Field(default=None, alias="endWeek", ge=0)
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team and reject a reversed week range."""
        _validate_year_or_team(self.year, self.team)
        _validate_week_range(self.start_week, self.end_week)
        return self


class AdvancedGameStatsRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/game/advanced``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    week: int | None = Field(default=None, ge=0)
    opponent: str | None = Field(default=None, min_length=1)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")
    season_type: SeasonType | None = Field(default=None, alias="seasonType")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team selector."""
        _validate_year_or_team(self.year, self.team)
        return self


class GameHavocRequest(_StatsRequest):
    """Validate filters accepted by ``GET /stats/game/havoc``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    week: int | None = Field(default=None, ge=0)
    opponent: str | None = Field(default=None, min_length=1)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team selector."""
        _validate_year_or_team(self.year, self.team)
        return self


__all__ = [
    "AdvancedGameStatsRequest",
    "AdvancedSeasonStatsRequest",
    "GameHavocRequest",
    "PlayerGameSuccessRequest",
    "PlayerSeasonStatsRequest",
    "PlayerSeasonSuccessRequest",
    "TeamSeasonStatsRequest",
]
