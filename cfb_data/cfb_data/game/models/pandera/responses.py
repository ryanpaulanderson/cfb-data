"""
College Football Data API - Pandera Schema Models for Games Section
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandera as pa
from pandera import DataFrameModel, Field
from pandera.typing import Series


# -------------------------------------------------------------------
# /games endpoint
# -------------------------------------------------------------------
class GameSchema(DataFrameModel):
    """
    Schema for /games endpoint.
    """

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_date: Series[datetime] = Field()
    start_time_tbd: Series[bool] = Field()
    completed: Series[bool] = Field()
    neutral_site: Series[bool] = Field()
    conference_game: Series[Optional[bool]] = Field(nullable=True)
    attendance: Series[Optional[int]] = Field(nullable=True, ge=0)
    venue_id: Series[Optional[int]] = Field(nullable=True, ge=0)
    venue: Series[Optional[str]] = Field(nullable=True)
    home_id: Series[Optional[int]] = Field(nullable=True, ge=0)
    home_team: Series[str] = Field()
    home_conference: Series[Optional[str]] = Field(nullable=True)
    home_division: Series[Optional[str]] = Field(nullable=True)
    home_points: Series[Optional[int]] = Field(nullable=True, ge=0)
    home_line_scores: Series[Optional[List[Optional[int]]]] = Field(nullable=True)
    home_post_win_prob: Series[Optional[float]] = Field(nullable=True, ge=0, le=1)
    home_pregame_elo: Series[Optional[int]] = Field(nullable=True)
    home_postgame_elo: Series[Optional[int]] = Field(nullable=True)
    away_id: Series[Optional[int]] = Field(nullable=True, ge=0)
    away_team: Series[str] = Field()
    away_conference: Series[Optional[str]] = Field(nullable=True)
    away_division: Series[Optional[str]] = Field(nullable=True)
    away_points: Series[Optional[int]] = Field(nullable=True, ge=0)
    away_line_scores: Series[Optional[List[Optional[int]]]] = Field(nullable=True)
    away_post_win_prob: Series[Optional[float]] = Field(nullable=True, ge=0, le=1)
    away_pregame_elo: Series[Optional[int]] = Field(nullable=True)
    away_postgame_elo: Series[Optional[int]] = Field(nullable=True)
    excitement_index: Series[Optional[float]] = Field(nullable=True)
    highlights: Series[Optional[str]] = Field(nullable=True)
    notes: Series[Optional[str]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /calendar endpoint
# -------------------------------------------------------------------
class CalendarWeekSchema(DataFrameModel):
    """
    Schema for /calendar endpoint.
    """

    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    first_game_start: Series[datetime] = Field()
    last_game_start: Series[datetime] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/media endpoint
# -------------------------------------------------------------------
class GameMediaSchema(DataFrameModel):
    """
    Schema for /games/media endpoint.
    """

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_time: Series[datetime] = Field()
    is_start_time_tbd: Series[bool] = Field()
    home_team: Series[str] = Field()
    home_conference: Series[Optional[str]] = Field(nullable=True)
    away_team: Series[str] = Field()
    away_conference: Series[Optional[str]] = Field(nullable=True)
    tv: Series[Optional[str]] = Field(nullable=True)
    radio: Series[Optional[str]] = Field(nullable=True)
    web: Series[Optional[str]] = Field(nullable=True)
    ppv: Series[Optional[str]] = Field(nullable=True)
    mobile: Series[Optional[str]] = Field(nullable=True)
    outlet: Series[Optional[str]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/weather endpoint
# -------------------------------------------------------------------
class GameWeatherSchema(DataFrameModel):
    """
    Schema for /games/weather endpoint.
    """

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_time: Series[datetime] = Field()
    game_indoors: Series[Optional[bool]] = Field(nullable=True)
    venue_id: Series[Optional[int]] = Field(nullable=True, ge=0)
    venue: Series[Optional[str]] = Field(nullable=True)
    temperature: Series[Optional[float]] = Field(nullable=True)
    dew_point: Series[Optional[float]] = Field(nullable=True)
    humidity: Series[Optional[float]] = Field(nullable=True, ge=0, le=100)
    precipitation: Series[Optional[float]] = Field(nullable=True, ge=0)
    snowfall: Series[Optional[float]] = Field(nullable=True, ge=0)
    wind_direction: Series[Optional[float]] = Field(nullable=True, ge=0, le=360)
    wind_speed: Series[Optional[float]] = Field(nullable=True, ge=0)
    pressure: Series[Optional[float]] = Field(nullable=True)
    weather_condition_code: Series[Optional[str]] = Field(nullable=True)
    weather_condition: Series[Optional[str]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /records endpoint
# -------------------------------------------------------------------
class TeamRecordsSchema(DataFrameModel):
    """
    Schema for /records endpoint.
    """

    year: Series[int] = Field(ge=0)
    team_id: Series[Optional[int]] = Field(nullable=True, ge=0)
    team: Series[str] = Field()
    conference: Series[Optional[str]] = Field(nullable=True)
    division: Series[Optional[str]] = Field(nullable=True)
    expected_wins: Series[Optional[float]] = Field(nullable=True)
    total: Series[Dict[str, int]] = Field()
    conference_games: Series[Optional[Dict[str, int]]] = Field(nullable=True)
    home_games: Series[Optional[Dict[str, int]]] = Field(nullable=True)
    away_games: Series[Optional[Dict[str, int]]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/players endpoint
# -------------------------------------------------------------------
class PlayerGameStatsSchema(DataFrameModel):
    """
    Schema for /games/players endpoint.
    """

    game_id: Series[int] = Field(ge=0)
    team: Series[str] = Field()
    conference: Series[Optional[str]] = Field(nullable=True)
    category: Series[str] = Field()
    passing: Series[Optional[List[Dict[str, Any]]]] = Field(nullable=True)
    rushing: Series[Optional[List[Dict[str, Any]]]] = Field(nullable=True)
    receiving: Series[Optional[List[Dict[str, Any]]]] = Field(nullable=True)
    defensive: Series[Optional[List[Dict[str, Any]]]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/teams endpoint
# -------------------------------------------------------------------
class TeamGameStatsSchema(DataFrameModel):
    """
    Schema for /games/teams endpoint.
    """

    game_id: Series[int] = Field(ge=0)
    school: Series[str] = Field()
    conference: Series[Optional[str]] = Field(nullable=True)
    home_away: Series[str] = Field(isin=["home", "away"])
    opponent: Series[str] = Field()
    points: Series[int] = Field(ge=0)
    total_yards: Series[Optional[float]] = Field(nullable=True)
    net_passing_yards: Series[Optional[float]] = Field(nullable=True)
    completion_attempts: Series[Optional[str]] = Field(nullable=True)
    passing_tds: Series[Optional[int]] = Field(nullable=True)
    rushing_yards: Series[Optional[float]] = Field(nullable=True)
    rushing_attempts: Series[Optional[int]] = Field(nullable=True)
    rushing_tds: Series[Optional[int]] = Field(nullable=True)
    first_downs: Series[Optional[int]] = Field(nullable=True)
    third_down_efficiency: Series[Optional[str]] = Field(nullable=True)
    fourth_down_efficiency: Series[Optional[str]] = Field(nullable=True)
    total_penalties: Series[Optional[int]] = Field(nullable=True)
    penalty_yards: Series[Optional[int]] = Field(nullable=True)
    turnovers: Series[Optional[int]] = Field(nullable=True)
    fumbles_lost: Series[Optional[int]] = Field(nullable=True)
    interceptions_thrown: Series[Optional[int]] = Field(nullable=True)
    possession_time: Series[Optional[str]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /scoreboard endpoint
# -------------------------------------------------------------------
class GameLineSchema(DataFrameModel):
    """
    Sub-schema for the 'line' field in /scoreboard.
    """

    home_team: Series[float] = Field()
    away_team: Series[float] = Field()
    over_under: Series[float] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


class ScoreboardSchema(DataFrameModel):
    """
    Schema for /scoreboard endpoint.
    """

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_date: Series[datetime] = Field()
    home_team: Series[str] = Field()
    away_team: Series[str] = Field()
    home_points: Series[Optional[int]] = Field(nullable=True, ge=0)
    away_points: Series[Optional[int]] = Field(nullable=True, ge=0)
    neutral_site: Series[bool] = Field()
    conference_game: Series[Optional[bool]] = Field(nullable=True)
    line: Series[Optional[Dict[str, float]]] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True
