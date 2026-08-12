"""Validate responses from implemented CFBD Metrics endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import SeasonType


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Metrics responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PredictedPointsValue(_ResponseModel):
    """Represent expected points at one field position."""

    yard_line: int = Field(alias="yardLine", ge=0, le=100)
    predicted_points: float = Field(alias="predictedPoints")


class TeamPPACumulative(_ResponseModel):
    """Represent cumulative team predicted-points-added values."""

    total: float
    passing: float
    rushing: float


class TeamSeasonPPAUnit(_ResponseModel):
    """Represent one side of a team's season PPA metrics."""

    overall: float
    passing: float
    rushing: float
    first_down: float = Field(alias="firstDown")
    second_down: float = Field(alias="secondDown")
    third_down: float = Field(alias="thirdDown")
    cumulative: TeamPPACumulative


class TeamSeasonPredictedPointsAdded(_ResponseModel):
    """Represent team predicted-points-added metrics for a season."""

    season: int = Field(ge=1869)
    conference: str
    team: str
    offense: TeamSeasonPPAUnit
    defense: TeamSeasonPPAUnit


class TeamGamePPAUnit(_ResponseModel):
    """Represent one side of a team's game PPA metrics."""

    overall: float
    passing: float
    rushing: float
    first_down: float = Field(alias="firstDown")
    second_down: float = Field(alias="secondDown")
    third_down: float = Field(alias="thirdDown")


class TeamGamePredictedPointsAdded(_ResponseModel):
    """Represent team predicted-points-added metrics for one game."""

    game_id: int = Field(alias="gameId", gt=0)
    season: int = Field(ge=1869)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    team: str
    conference: str
    opponent: str
    offense: TeamGamePPAUnit
    defense: TeamGamePPAUnit


class PlayerGamePPAAverage(_ResponseModel):
    """Represent a player's per-play PPA averages for one game."""

    all: float
    passing: float | None = Field(default=None, alias="pass")
    rush: float | None = None


class PlayerGamePredictedPointsAdded(_ResponseModel):
    """Represent player predicted-points-added metrics for one game."""

    season: int = Field(ge=1869)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    id: str
    name: str
    position: str
    team: str
    opponent: str
    average_ppa: PlayerGamePPAAverage = Field(alias="averagePPA")


class PlayerSeasonPPASplit(_ResponseModel):
    """Represent average or total player PPA split by play context."""

    all: float
    passing: float | None = Field(default=None, alias="pass")
    rush: float | None = None
    first_down: float | None = Field(default=None, alias="firstDown")
    second_down: float | None = Field(default=None, alias="secondDown")
    third_down: float | None = Field(default=None, alias="thirdDown")
    standard_downs: float | None = Field(default=None, alias="standardDowns")
    passing_downs: float | None = Field(default=None, alias="passingDowns")


class PlayerSeasonPredictedPointsAdded(_ResponseModel):
    """Represent player predicted-points-added metrics for a season."""

    season: int = Field(ge=1869)
    id: str
    name: str
    position: str
    team: str
    conference: str
    average_ppa: PlayerSeasonPPASplit = Field(alias="averagePPA")
    total_ppa: PlayerSeasonPPASplit = Field(alias="totalPPA")


class PlayWinProbability(_ResponseModel):
    """Represent the modeled home win probability after one play."""

    game_id: int = Field(alias="gameId", gt=0)
    play_id: str = Field(alias="playId")
    play_text: str = Field(alias="playText")
    home_id: int = Field(alias="homeId", gt=0)
    home: str
    away_id: int = Field(alias="awayId", gt=0)
    away: str
    spread: float
    home_ball: bool = Field(alias="homeBall")
    home_score: int = Field(alias="homeScore", ge=0)
    away_score: int = Field(alias="awayScore", ge=0)
    yard_line: int = Field(alias="yardLine", ge=0, le=100)
    down: int = Field(ge=0, le=4)
    distance: int = Field(ge=0)
    home_win_probability: float = Field(alias="homeWinProbability", ge=0, le=1)
    play_number: int = Field(alias="playNumber", ge=0)


class PregameWinProbability(_ResponseModel):
    """Represent one game's pregame home win probability."""

    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    game_id: int = Field(alias="gameId", gt=0)
    home_team: str = Field(alias="homeTeam")
    away_team: str = Field(alias="awayTeam")
    spread: float
    home_win_probability: float = Field(alias="homeWinProbability", ge=0, le=1)


class FieldGoalExpectedPoints(_ResponseModel):
    """Represent expected points for a field-goal distance."""

    yards_to_goal: int = Field(alias="yardsToGoal", ge=0, le=100)
    distance: int = Field(ge=0)
    expected_points: float = Field(alias="expectedPoints")


__all__ = [
    "FieldGoalExpectedPoints",
    "PlayerGamePPAAverage",
    "PlayerGamePredictedPointsAdded",
    "PlayerSeasonPPASplit",
    "PlayerSeasonPredictedPointsAdded",
    "PlayWinProbability",
    "PredictedPointsValue",
    "PregameWinProbability",
    "TeamGamePPAUnit",
    "TeamGamePredictedPointsAdded",
    "TeamPPACumulative",
    "TeamSeasonPPAUnit",
    "TeamSeasonPredictedPointsAdded",
]
