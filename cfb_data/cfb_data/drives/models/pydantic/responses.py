"""Pydantic models for drives endpoint responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DriveTime(BaseModel):
    """Time remaining in a period."""

    seconds: Optional[int] = Field(default=None)
    minutes: Optional[int] = Field(default=None)

    model_config = ConfigDict(populate_by_name=True)


class Drive(BaseModel):
    """Drive data model for `/drives` endpoint."""

    offense: str = Field(alias="offense")
    offense_conference: Optional[str] = Field(default=None, alias="offenseConference")
    defense: str = Field(alias="defense")
    defense_conference: Optional[str] = Field(default=None, alias="defenseConference")
    game_id: int = Field(alias="gameId")
    id: str = Field(alias="id")
    drive_number: Optional[int] = Field(default=None, alias="driveNumber")
    scoring: bool = Field(alias="scoring")
    start_period: int = Field(alias="startPeriod")
    start_yardline: int = Field(alias="startYardline")
    start_yards_to_goal: int = Field(alias="startYardsToGoal")
    start_time: DriveTime = Field(alias="startTime")
    end_period: int = Field(alias="endPeriod")
    end_yardline: int = Field(alias="endYardline")
    end_yards_to_goal: int = Field(alias="endYardsToGoal")
    end_time: DriveTime = Field(alias="endTime")
    plays: int = Field(alias="plays")
    yards: int = Field(alias="yards")
    drive_result: str = Field(alias="driveResult")
    is_home_offense: bool = Field(alias="isHomeOffense")
    start_offense_score: int = Field(alias="startOffenseScore")
    start_defense_score: int = Field(alias="startDefenseScore")
    end_offense_score: int = Field(alias="endOffenseScore")
    end_defense_score: int = Field(alias="endDefenseScore")

    model_config = ConfigDict(populate_by_name=True)
