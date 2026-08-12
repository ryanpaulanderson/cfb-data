"""Pydantic models for drives endpoint responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DriveTime(BaseModel):
    """Time remaining in a period."""

    seconds: int | None = Field(ge=0)
    minutes: int | None = Field(ge=0)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Drive(BaseModel):
    """Drive data model for `/drives` endpoint."""

    offense: str = Field(alias="offense")
    offense_conference: str | None = Field(alias="offenseConference")
    defense: str = Field(alias="defense")
    defense_conference: str | None = Field(alias="defenseConference")
    game_id: int = Field(alias="gameId", ge=0)
    id: str = Field(alias="id")
    drive_number: int | None = Field(alias="driveNumber", ge=0)
    scoring: bool = Field(alias="scoring")
    start_period: int = Field(alias="startPeriod", ge=0)
    start_yardline: int = Field(alias="startYardline", ge=0)
    start_yards_to_goal: int = Field(alias="startYardsToGoal", ge=0)
    start_time: DriveTime = Field(alias="startTime")
    end_period: int = Field(alias="endPeriod", ge=0)
    end_yardline: int = Field(alias="endYardline", ge=0)
    end_yards_to_goal: int = Field(alias="endYardsToGoal", ge=0)
    end_time: DriveTime = Field(alias="endTime")
    elapsed: DriveTime
    plays: int = Field(alias="plays", ge=0)
    yards: int = Field(alias="yards")
    drive_result: str = Field(alias="driveResult")
    is_home_offense: bool = Field(alias="isHomeOffense")
    start_offense_score: int = Field(alias="startOffenseScore", ge=0)
    start_defense_score: int = Field(alias="startDefenseScore", ge=0)
    end_offense_score: int = Field(alias="endOffenseScore", ge=0)
    end_defense_score: int = Field(alias="endDefenseScore", ge=0)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
