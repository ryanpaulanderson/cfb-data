"""College Football Data API - Pandera Schema Models for Games Section."""

from datetime import datetime

from pandera.pandas import DataFrameModel, Field
from pandera.typing import Series


# -------------------------------------------------------------------
# /games endpoint
# -------------------------------------------------------------------
class GameSchema(DataFrameModel):
    """Schema for /games endpoint."""

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(
        isin=[
            "regular",
            "postseason",
            "both",
            "allstar",
            "spring_regular",
            "spring_postseason",
        ]
    )
    start_date: Series[datetime] = Field()
    start_time_tbd: Series[bool] = Field()
    completed: Series[bool] = Field()
    neutral_site: Series[bool] = Field()
    conference_game: Series[bool] = Field()
    attendance: Series[float] = Field(nullable=True, ge=0)
    venue_id: Series[float] = Field(nullable=True, ge=0)
    venue: Series[str] = Field(nullable=True)
    home_id: Series[int] = Field(ge=0)
    home_team: Series[str] = Field()
    home_conference: Series[str] = Field(nullable=True)
    home_classification: Series[str] = Field(nullable=True)
    home_points: Series[float] = Field(nullable=True, ge=0)
    home_line_scores: Series[object] = Field(nullable=True)
    home_postgame_win_probability: Series[float] = Field(nullable=True, ge=0, le=1)
    home_pregame_elo: Series[float] = Field(nullable=True)
    home_postgame_elo: Series[float] = Field(nullable=True)
    away_id: Series[int] = Field(ge=0)
    away_team: Series[str] = Field()
    away_conference: Series[str] = Field(nullable=True)
    away_classification: Series[str] = Field(nullable=True)
    away_points: Series[float] = Field(nullable=True, ge=0)
    away_line_scores: Series[object] = Field(nullable=True)
    away_postgame_win_probability: Series[float] = Field(nullable=True, ge=0, le=1)
    away_pregame_elo: Series[float] = Field(nullable=True)
    away_postgame_elo: Series[float] = Field(nullable=True)
    excitement_index: Series[float] = Field(nullable=True)
    highlights: Series[str] = Field(nullable=True)
    notes: Series[str] = Field(nullable=True)
    playoff: Series[object] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /calendar endpoint
# -------------------------------------------------------------------
class CalendarWeekSchema(DataFrameModel):
    """Schema for /calendar endpoint."""

    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(
        isin=[
            "regular",
            "postseason",
            "both",
            "allstar",
            "spring_regular",
            "spring_postseason",
        ]
    )
    start_date: Series[datetime] = Field()
    end_date: Series[datetime] = Field()
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
    """Schema for /games/media endpoint."""

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(
        isin=[
            "regular",
            "postseason",
            "both",
            "allstar",
            "spring_regular",
            "spring_postseason",
        ]
    )
    start_time: Series[datetime] = Field()
    is_start_time_tbd: Series[bool] = Field()
    home_team: Series[str] = Field()
    home_conference: Series[str] = Field(nullable=True)
    away_team: Series[str] = Field()
    away_conference: Series[str] = Field(nullable=True)
    media_type: Series[str] = Field(isin=["tv", "radio", "web", "ppv", "mobile"])
    outlet: Series[str] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/weather endpoint
# -------------------------------------------------------------------
class GameWeatherSchema(DataFrameModel):
    """Schema for /games/weather endpoint."""

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_time: Series[datetime] = Field()
    game_indoors: Series[bool] = Field()
    home_team: Series[str] = Field()
    home_conference: Series[str] = Field(nullable=True)
    away_team: Series[str] = Field()
    away_conference: Series[str] = Field(nullable=True)
    venue_id: Series[int] = Field(ge=0)
    venue: Series[str] = Field()
    temperature: Series[float] = Field(nullable=True)
    dew_point: Series[float] = Field(nullable=True)
    humidity: Series[float] = Field(nullable=True, ge=0, le=100)
    precipitation: Series[float] = Field(nullable=True, ge=0)
    snowfall: Series[float] = Field(nullable=True, ge=0)
    wind_direction: Series[float] = Field(nullable=True, ge=0, le=360)
    wind_speed: Series[float] = Field(nullable=True, ge=0)
    pressure: Series[float] = Field(nullable=True)
    weather_condition_code: Series[float] = Field(nullable=True)
    weather_condition: Series[str] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /records endpoint
# -------------------------------------------------------------------
class TeamRecordsSchema(DataFrameModel):
    """Schema for /records endpoint."""

    year: Series[int] = Field(ge=0)
    team_id: Series[int] = Field(ge=0)
    team: Series[str] = Field()
    classification: Series[str] = Field(nullable=True)
    conference: Series[str] = Field()
    division: Series[str] = Field()
    expected_wins: Series[float] = Field(nullable=True)
    total: Series[object] = Field()
    conference_games: Series[object] = Field()
    home_games: Series[object] = Field()
    away_games: Series[object] = Field()
    neutral_site_games: Series[object] = Field()
    regular_season: Series[object] = Field()
    postseason: Series[object] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/players endpoint
# -------------------------------------------------------------------
class PlayerGameStatsSchema(DataFrameModel):
    """Schema for /games/players endpoint."""

    id: Series[int] = Field(ge=0)
    teams: Series[object] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/teams endpoint
# -------------------------------------------------------------------
class TeamGameStatsSchema(DataFrameModel):
    """Schema for /games/teams endpoint."""

    id: Series[int] = Field(ge=0)
    teams: Series[object] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
class ScoreboardSchema(DataFrameModel):
    """Schema for /scoreboard endpoint."""

    id: Series[int] = Field(ge=0)
    start_date: Series[datetime] = Field()
    start_time_tbd: Series[bool] = Field()
    tv: Series[str] = Field(nullable=True)
    neutral_site: Series[bool] = Field()
    conference_game: Series[bool] = Field()
    status: Series[str] = Field(isin=["scheduled", "in_progress", "completed"])
    period: Series[float] = Field(nullable=True, ge=0)
    clock: Series[str] = Field(nullable=True)
    situation: Series[str] = Field(nullable=True)
    possession: Series[str] = Field(nullable=True)
    last_play: Series[str] = Field(nullable=True)
    venue: Series[object] = Field()
    home_team: Series[object] = Field()
    away_team: Series[object] = Field()
    weather: Series[object] = Field()
    betting: Series[object] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True
