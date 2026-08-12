"""College Football Data API - Pandera Schema Models for Games Section."""

from datetime import datetime

from pandera.pandas import DataFrameModel, Field
from pandera.typing import Series

from cfb_data.base.types import JSONObject


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
    conference_game: Series[bool | None] = Field(nullable=True)
    attendance: Series[int | None] = Field(nullable=True, ge=0)
    venue_id: Series[int | None] = Field(nullable=True, ge=0)
    venue: Series[str | None] = Field(nullable=True)
    home_id: Series[int | None] = Field(nullable=True, ge=0)
    home_team: Series[str] = Field()
    home_conference: Series[str | None] = Field(nullable=True)
    home_classification: Series[str | None] = Field(nullable=True)
    home_points: Series[int | None] = Field(nullable=True, ge=0)
    home_line_scores: Series[list[int | None] | None] = Field(nullable=True)
    home_post_win_prob: Series[float | None] = Field(nullable=True, ge=0, le=1)
    home_pregame_elo: Series[int | None] = Field(nullable=True)
    home_postgame_elo: Series[int | None] = Field(nullable=True)
    away_id: Series[int | None] = Field(nullable=True, ge=0)
    away_team: Series[str] = Field()
    away_conference: Series[str | None] = Field(nullable=True)
    away_classification: Series[str | None] = Field(nullable=True)
    away_points: Series[int | None] = Field(nullable=True, ge=0)
    away_line_scores: Series[list[int | None] | None] = Field(nullable=True)
    away_post_win_prob: Series[float | None] = Field(nullable=True, ge=0, le=1)
    away_pregame_elo: Series[int | None] = Field(nullable=True)
    away_postgame_elo: Series[int | None] = Field(nullable=True)
    excitement_index: Series[float | None] = Field(nullable=True)
    highlights: Series[str | None] = Field(nullable=True)
    notes: Series[str | None] = Field(nullable=True)

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
    home_conference: Series[str | None] = Field(nullable=True)
    away_team: Series[str] = Field()
    away_conference: Series[str | None] = Field(nullable=True)
    media_type: Series[str | None] = Field(nullable=True)
    tv: Series[str | None] = Field(nullable=True)
    radio: Series[str | None] = Field(nullable=True)
    web: Series[str | None] = Field(nullable=True)
    ppv: Series[str | None] = Field(nullable=True)
    mobile: Series[str | None] = Field(nullable=True)
    outlet: Series[str | None] = Field(nullable=True)

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
    game_indoors: Series[bool | None] = Field(nullable=True)
    venue_id: Series[int | None] = Field(nullable=True, ge=0)
    venue: Series[str | None] = Field(nullable=True)
    temperature: Series[float | None] = Field(nullable=True)
    dew_point: Series[float | None] = Field(nullable=True)
    humidity: Series[float | None] = Field(nullable=True, ge=0, le=100)
    precipitation: Series[float | None] = Field(nullable=True, ge=0)
    snowfall: Series[float | None] = Field(nullable=True, ge=0)
    wind_direction: Series[float | None] = Field(nullable=True, ge=0, le=360)
    wind_speed: Series[float | None] = Field(nullable=True, ge=0)
    pressure: Series[float | None] = Field(nullable=True)
    weather_condition_code: Series[str | None] = Field(nullable=True)
    weather_condition: Series[str | None] = Field(nullable=True)

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
    team_id: Series[int | None] = Field(nullable=True, ge=0)
    team: Series[str] = Field()
    classification: Series[str | None] = Field(nullable=True)
    conference: Series[str | None] = Field(nullable=True)
    division: Series[str | None] = Field(nullable=True)
    expected_wins: Series[float | None] = Field(nullable=True)
    total: Series[dict[str, int]] = Field()
    conference_games: Series[dict[str, int] | None] = Field(nullable=True)
    home_games: Series[dict[str, int] | None] = Field(nullable=True)
    away_games: Series[dict[str, int] | None] = Field(nullable=True)
    neutral_site_games: Series[dict[str, int] | None] = Field(nullable=True)
    regular_season: Series[dict[str, int] | None] = Field(nullable=True)
    postseason: Series[dict[str, int] | None] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/players endpoint
# -------------------------------------------------------------------
class PlayerGameStatsSchema(DataFrameModel):
    """Schema for /games/players endpoint."""

    game_id: Series[int] = Field(ge=0)
    team: Series[str] = Field()
    conference: Series[str | None] = Field(nullable=True)
    category: Series[str] = Field()
    passing: Series[list[JSONObject] | None] = Field(nullable=True)
    rushing: Series[list[JSONObject] | None] = Field(nullable=True)
    receiving: Series[list[JSONObject] | None] = Field(nullable=True)
    defensive: Series[list[JSONObject] | None] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /games/teams endpoint
# -------------------------------------------------------------------
class TeamGameStatsSchema(DataFrameModel):
    """Schema for /games/teams endpoint."""

    game_id: Series[int] = Field(ge=0)
    school: Series[str] = Field()
    conference: Series[str | None] = Field(nullable=True)
    home_away: Series[str] = Field(isin=["home", "away"])
    opponent: Series[str] = Field()
    points: Series[int] = Field(ge=0)
    total_yards: Series[float | None] = Field(nullable=True)
    net_passing_yards: Series[float | None] = Field(nullable=True)
    completion_attempts: Series[str | None] = Field(nullable=True)
    passing_tds: Series[int | None] = Field(nullable=True)
    rushing_yards: Series[float | None] = Field(nullable=True)
    rushing_attempts: Series[int | None] = Field(nullable=True)
    rushing_tds: Series[int | None] = Field(nullable=True)
    first_downs: Series[int | None] = Field(nullable=True)
    third_down_efficiency: Series[str | None] = Field(nullable=True)
    fourth_down_efficiency: Series[str | None] = Field(nullable=True)
    total_penalties: Series[int | None] = Field(nullable=True)
    penalty_yards: Series[int | None] = Field(nullable=True)
    turnovers: Series[int | None] = Field(nullable=True)
    fumbles_lost: Series[int | None] = Field(nullable=True)
    interceptions_thrown: Series[int | None] = Field(nullable=True)
    possession_time: Series[str | None] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


# -------------------------------------------------------------------
# /scoreboard endpoint
# -------------------------------------------------------------------
class GameLineSchema(DataFrameModel):
    """Sub-schema for the 'line' field in /scoreboard."""

    home_team: Series[float] = Field()
    away_team: Series[float] = Field()
    over_under: Series[float] = Field()

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True


class ScoreboardSchema(DataFrameModel):
    """Schema for /scoreboard endpoint."""

    id: Series[int] = Field(ge=0)
    season: Series[int] = Field(ge=0)
    week: Series[int] = Field(ge=0)
    season_type: Series[str] = Field(isin=["regular", "postseason", "both"])
    start_date: Series[datetime] = Field()
    home_team: Series[str] = Field()
    away_team: Series[str] = Field()
    home_points: Series[int | None] = Field(nullable=True, ge=0)
    away_points: Series[int | None] = Field(nullable=True, ge=0)
    neutral_site: Series[bool] = Field()
    conference_game: Series[bool | None] = Field(nullable=True)
    line: Series[dict[str, float] | None] = Field(nullable=True)

    class Config:
        """Pandera configuration."""

        coerce = True
        strict = True
