"""Validate responses from the implemented CFBD games endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data.enums import Classification, MediaType, SeasonType


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to response models."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def require_utc_datetimes(cls, value: object) -> object:
        """Require aware response timestamps and normalize them to UTC.

        :param value: Validated response field value.
        :return: UTC-normalized datetime or the unchanged non-datetime value.
        :raises ValueError: If a datetime does not identify an instant.
        """
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Response timestamps must be timezone-aware")
        return value.astimezone(UTC)


class GameStatus(StrEnum):
    """Identify the current state of a scoreboard game."""

    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"


class GamePlayoff(_ResponseModel):
    """Describe the playoff context attached to a game."""

    model_config = ConfigDict(populate_by_name=True)

    competition: str
    format: str
    round: str
    round_name: str = Field(alias="roundName")
    bracket_slot: str = Field(alias="bracketSlot")
    home_seed: int | None = Field(alias="homeSeed", ge=0)
    away_seed: int | None = Field(alias="awaySeed", ge=0)
    bowl_name: str | None = Field(alias="bowlName")


class Game(_ResponseModel):
    """Represent a game returned by ``GET /games``."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(ge=0)
    season: int = Field(ge=0)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    start_date: datetime = Field(alias="startDate")
    start_time_tbd: bool = Field(alias="startTimeTBD")
    completed: bool
    neutral_site: bool = Field(alias="neutralSite")
    conference_game: bool = Field(alias="conferenceGame")
    attendance: int | None = Field(ge=0)
    venue_id: int | None = Field(alias="venueId", ge=0)
    venue: str | None
    home_id: int = Field(alias="homeId", ge=0)
    home_team: str = Field(alias="homeTeam")
    home_conference: str | None = Field(alias="homeConference")
    home_classification: Classification | None = Field(alias="homeClassification")
    home_points: int | None = Field(alias="homePoints", ge=0)
    home_line_scores: list[float] | None = Field(alias="homeLineScores")
    home_postgame_win_probability: float | None = Field(
        alias="homePostgameWinProbability", ge=0, le=1
    )
    home_pregame_elo: int | None = Field(alias="homePregameElo")
    home_postgame_elo: int | None = Field(alias="homePostgameElo")
    away_id: int = Field(alias="awayId", ge=0)
    away_team: str = Field(alias="awayTeam")
    away_conference: str | None = Field(alias="awayConference")
    away_classification: Classification | None = Field(alias="awayClassification")
    away_points: int | None = Field(alias="awayPoints", ge=0)
    away_line_scores: list[float] | None = Field(alias="awayLineScores")
    away_postgame_win_probability: float | None = Field(
        alias="awayPostgameWinProbability", ge=0, le=1
    )
    away_pregame_elo: int | None = Field(alias="awayPregameElo")
    away_postgame_elo: int | None = Field(alias="awayPostgameElo")
    excitement_index: float | None = Field(alias="excitementIndex")
    highlights: str | None
    notes: str | None
    playoff: GamePlayoff | None


class CalendarWeek(_ResponseModel):
    """Represent a season week returned by ``GET /calendar``."""

    model_config = ConfigDict(populate_by_name=True)

    season: int = Field(ge=0)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")
    first_game_start: datetime = Field(alias="firstGameStart")
    last_game_start: datetime = Field(alias="lastGameStart")


class GameMedia(_ResponseModel):
    """Represent one broadcast returned by ``GET /games/media``."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(ge=0)
    season: int = Field(ge=0)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    start_time: datetime = Field(alias="startTime")
    is_start_time_tbd: bool = Field(alias="isStartTimeTBD")
    home_team: str = Field(alias="homeTeam")
    home_conference: str | None = Field(alias="homeConference")
    away_team: str = Field(alias="awayTeam")
    away_conference: str | None = Field(alias="awayConference")
    media_type: MediaType = Field(alias="mediaType")
    outlet: str


class GameWeather(_ResponseModel):
    """Represent weather returned by ``GET /games/weather``."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(ge=0)
    season: int = Field(ge=0)
    week: int = Field(ge=0)
    season_type: SeasonType = Field(alias="seasonType")
    start_time: datetime = Field(alias="startTime")
    game_indoors: bool = Field(alias="gameIndoors")
    home_team: str = Field(alias="homeTeam")
    home_conference: str | None = Field(alias="homeConference")
    away_team: str = Field(alias="awayTeam")
    away_conference: str | None = Field(alias="awayConference")
    venue_id: int = Field(alias="venueId", ge=0)
    venue: str
    temperature: float | None
    dew_point: float | None = Field(alias="dewPoint")
    humidity: float | None = Field(ge=0, le=100)
    precipitation: float | None = Field(ge=0)
    snowfall: float | None = Field(ge=0)
    wind_direction: float | None = Field(alias="windDirection", ge=0, le=360)
    wind_speed: float | None = Field(alias="windSpeed", ge=0)
    pressure: float | None
    weather_condition_code: float | None = Field(alias="weatherConditionCode")
    weather_condition: str | None = Field(alias="weatherCondition")


class TeamRecord(_ResponseModel):
    """Represent a win-loss-tie record for one game grouping."""

    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)


class TeamRecords(_ResponseModel):
    """Represent a team season returned by ``GET /records``."""

    model_config = ConfigDict(populate_by_name=True)

    year: int = Field(ge=0)
    team_id: int = Field(alias="teamId", ge=0)
    team: str
    classification: Classification | None
    conference: str
    division: str
    expected_wins: float | None = Field(alias="expectedWins")
    total: TeamRecord
    conference_games: TeamRecord = Field(alias="conferenceGames")
    home_games: TeamRecord = Field(alias="homeGames")
    away_games: TeamRecord = Field(alias="awayGames")
    neutral_site_games: TeamRecord = Field(alias="neutralSiteGames")
    regular_season: TeamRecord = Field(alias="regularSeason")
    postseason: TeamRecord


class ScoreboardVenue(_ResponseModel):
    """Represent the venue attached to a scoreboard game."""

    name: str | None
    city: str | None
    state: str | None


class ScoreboardTeam(_ResponseModel):
    """Represent one team in a scoreboard game."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(ge=0)
    name: str
    conference: str | None
    classification: Classification | None
    points: int | None = Field(ge=0)
    line_scores: list[int] | None = Field(alias="lineScores")
    win_probability: float | None = Field(alias="winProbability", ge=0, le=1)


class ScoreboardWeather(_ResponseModel):
    """Represent the weather summary attached to a scoreboard game."""

    model_config = ConfigDict(populate_by_name=True)

    temperature: float | None
    description: str | None
    wind_speed: float | None = Field(alias="windSpeed", ge=0)
    wind_direction: float | None = Field(alias="windDirection", ge=0, le=360)


class ScoreboardBetting(_ResponseModel):
    """Represent the betting summary attached to a scoreboard game."""

    model_config = ConfigDict(populate_by_name=True)

    spread: float | None
    over_under: float | None = Field(alias="overUnder")
    home_moneyline: float | None = Field(alias="homeMoneyline")
    away_moneyline: float | None = Field(alias="awayMoneyline")


class ScoreboardGame(_ResponseModel):
    """Represent one game returned by ``GET /scoreboard``."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(ge=0)
    start_date: datetime = Field(alias="startDate")
    start_time_tbd: bool = Field(alias="startTimeTBD")
    tv: str | None
    neutral_site: bool = Field(alias="neutralSite")
    conference_game: bool = Field(alias="conferenceGame")
    status: GameStatus
    period: int | None = Field(ge=0)
    clock: str | None
    situation: str | None
    possession: str | None
    last_play: str | None = Field(alias="lastPlay")
    venue: ScoreboardVenue
    home_team: ScoreboardTeam = Field(alias="homeTeam")
    away_team: ScoreboardTeam = Field(alias="awayTeam")
    weather: ScoreboardWeather
    betting: ScoreboardBetting


class TeamGameStat(_ResponseModel):
    """Represent one named team statistic in a game box score."""

    category: str
    stat: str


class TeamGameStatsTeam(_ResponseModel):
    """Represent one team in a team-statistics game response."""

    model_config = ConfigDict(populate_by_name=True)

    team_id: int = Field(alias="teamId", ge=0)
    team: str
    conference: str | None
    home_away: str = Field(alias="homeAway", pattern="^(home|away)$")
    points: int | None = Field(ge=0)
    stats: list[TeamGameStat]


class TeamGameStats(_ResponseModel):
    """Represent a game returned by ``GET /games/teams``."""

    id: int = Field(ge=0)
    teams: list[TeamGameStatsTeam]


class PlayerGameStatPlayer(_ResponseModel):
    """Represent one athlete value in a player-statistics response."""

    id: str
    name: str
    stat: str


class PlayerGameStatType(_ResponseModel):
    """Group player statistics by their display type."""

    name: str
    athletes: list[PlayerGameStatPlayer]


class PlayerGameStatCategory(_ResponseModel):
    """Group player statistics by category."""

    name: str
    types: list[PlayerGameStatType]


class PlayerGameStatsTeam(_ResponseModel):
    """Represent one team in a player-statistics game response."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    conference: str | None
    home_away: str = Field(alias="homeAway", pattern="^(home|away)$")
    points: int | None = Field(ge=0)
    categories: list[PlayerGameStatCategory]


class PlayerGameStats(_ResponseModel):
    """Represent a game returned by ``GET /games/players``."""

    id: int = Field(ge=0)
    teams: list[PlayerGameStatsTeam]


class StatsByQuarter(_ResponseModel):
    """Represent a total metric and its first four quarter splits."""

    total: float
    quarter1: float | None
    quarter2: float | None
    quarter3: float | None
    quarter4: float | None


class TeamPPA(_ResponseModel):
    """Represent team predicted-points-added metrics."""

    team: str
    plays: int = Field(ge=0)
    overall: StatsByQuarter
    passing: StatsByQuarter
    rushing: StatsByQuarter


class TeamSuccessRates(_ResponseModel):
    """Represent team success-rate metrics."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    overall: StatsByQuarter
    standard_downs: StatsByQuarter = Field(alias="standardDowns")
    passing_downs: StatsByQuarter = Field(alias="passingDowns")


class TeamExplosiveness(_ResponseModel):
    """Represent team explosiveness by quarter."""

    team: str
    overall: StatsByQuarter


class TeamRushingStats(_ResponseModel):
    """Represent advanced team rushing metrics."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    power_success: float = Field(alias="powerSuccess")
    stuff_rate: float = Field(alias="stuffRate")
    line_yards: float = Field(alias="lineYards")
    line_yards_average: float = Field(alias="lineYardsAverage")
    second_level_yards: float = Field(alias="secondLevelYards")
    second_level_yards_average: float = Field(alias="secondLevelYardsAverage")
    open_field_yards: float = Field(alias="openFieldYards")
    open_field_yards_average: float = Field(alias="openFieldYardsAverage")


class TeamHavoc(_ResponseModel):
    """Represent team havoc metrics."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    total: float
    front_seven: float = Field(alias="frontSeven")
    defensive_back: float = Field(alias="db")


class TeamScoringOpportunities(_ResponseModel):
    """Represent team scoring-opportunity metrics."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    opportunities: int = Field(ge=0)
    points: int
    points_per_opportunity: float = Field(alias="pointsPerOpportunity")


class TeamFieldPosition(_ResponseModel):
    """Represent average team starting field position."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    average_start: float = Field(alias="averageStart")
    average_starting_predicted_points: float = Field(
        alias="averageStartingPredictedPoints"
    )


class PlayerStatsByQuarter(StatsByQuarter):
    """Represent a player's usage or PPA splits."""

    rushing: float
    passing: float


class PlayerGameUsage(PlayerStatsByQuarter):
    """Represent one player's game usage."""

    player: str
    team: str
    position: str


class PlayerPPA(_ResponseModel):
    """Represent one player's average and cumulative game PPA."""

    player: str
    team: str
    position: str
    average: PlayerStatsByQuarter
    cumulative: PlayerStatsByQuarter


class AdvancedGameInfo(_ResponseModel):
    """Represent the game summary within an advanced box score."""

    model_config = ConfigDict(populate_by_name=True)

    home_team: str = Field(alias="homeTeam")
    home_points: int = Field(alias="homePoints", ge=0)
    home_win_probability: float = Field(alias="homeWinProb", ge=0, le=1)
    away_team: str = Field(alias="awayTeam")
    away_points: int = Field(alias="awayPoints", ge=0)
    away_win_probability: float = Field(alias="awayWinProb", ge=0, le=1)
    home_winner: bool = Field(alias="homeWinner")
    excitement: float


class AdvancedTeamStats(_ResponseModel):
    """Group team metrics within an advanced box score."""

    model_config = ConfigDict(populate_by_name=True)

    ppa: list[TeamPPA]
    cumulative_ppa: list[TeamPPA] = Field(alias="cumulativePpa")
    success_rates: list[TeamSuccessRates] = Field(alias="successRates")
    explosiveness: list[TeamExplosiveness]
    rushing: list[TeamRushingStats]
    havoc: list[TeamHavoc]
    scoring_opportunities: list[TeamScoringOpportunities] = Field(
        alias="scoringOpportunities"
    )
    field_position: list[TeamFieldPosition] = Field(alias="fieldPosition")


class AdvancedPlayerStats(_ResponseModel):
    """Group player metrics within an advanced box score."""

    usage: list[PlayerGameUsage]
    ppa: list[PlayerPPA]


class AdvancedBoxScore(_ResponseModel):
    """Represent ``GET /game/box/advanced`` data."""

    model_config = ConfigDict(populate_by_name=True)

    game_info: AdvancedGameInfo = Field(alias="gameInfo")
    teams: AdvancedTeamStats
    players: AdvancedPlayerStats
