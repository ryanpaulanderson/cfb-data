"""Pydantic models for drives endpoint responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DriveTime(BaseModel):
    """Time remaining in a period."""

    seconds: Optional[int] = None
    minutes: Optional[int] = None


class Drive(BaseModel):
    """Drive data model for `/drives` endpoint."""

    offense: str
    offense_conference: Optional[str] = None
    defense: str
    defense_conference: Optional[str] = None
    game_id: int
    id: str
    drive_number: Optional[int] = None
    scoring: bool
    start_period: int
    start_yardline: int
    start_yards_to_goal: int
    start_time: DriveTime
    end_period: int
    end_yardline: int
    end_yards_to_goal: int
    end_time: DriveTime
    plays: int
    yards: int
    drive_result: str
    is_home_offense: bool
    start_offense_score: int
    start_defense_score: int
    end_offense_score: int
    end_defense_score: int
