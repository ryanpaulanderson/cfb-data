"""Pandera schema models for drives endpoint."""

from typing import Dict, Optional

import pandera as pa
from pandera import DataFrameModel, Field
from pandera.typing import Series


class DriveSchema(DataFrameModel):
    """Schema for `/drives` endpoint."""

    offense: Series[str] = Field()
    offense_conference: Series[str] = Field(nullable=True)
    defense: Series[str] = Field()
    defense_conference: Series[str] = Field(nullable=True)
    game_id: Series[int] = Field(ge=0)
    id: Series[str] = Field()
    drive_number: Series[int] = Field(nullable=True, ge=0)
    scoring: Series[bool] = Field()
    start_period: Series[int] = Field(ge=0)
    start_yardline: Series[int] = Field(ge=0)
    start_yards_to_goal: Series[int] = Field(ge=0)
    start_time: Series[Dict[str, int]] = Field()
    end_period: Series[int] = Field(ge=0)
    end_yardline: Series[int] = Field(ge=0)
    end_yards_to_goal: Series[int] = Field(ge=0)
    end_time: Series[Dict[str, int]] = Field()
    plays: Series[int] = Field(ge=0)
    yards: Series[int] = Field()
    drive_result: Series[str] = Field()
    is_home_offense: Series[bool] = Field()
    start_offense_score: Series[int] = Field(ge=0)
    start_defense_score: Series[int] = Field(ge=0)
    end_offense_score: Series[int] = Field(ge=0)
    end_defense_score: Series[int] = Field(ge=0)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True
