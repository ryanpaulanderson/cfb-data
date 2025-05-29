"""
College Football Data API - Game Response Models
Pydantic models for validating API responses from CFBD game endpoints
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, root_validator, validator


# Enums
class SeasonType(str, Enum):
    """
    Season type enumeration.

    :param regular: Regular season
    :type regular: str
    :param postseason: Postseason games
    :type postseason: str
    :param both: Both regular and postseason
    :type both: str
    """

    regular = "regular"
    postseason = "postseason"
    both = "both"


class Division(str, Enum):
    """
    Division classification enumeration.

    :param fbs: Football Bowl Subdivision
    :type fbs: str
    :param fcs: Football Championship Subdivision
    :type fcs: str
    :param ii: Division II
    :type ii: str
    :param iii: Division III
    :type iii: str
    """

    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    iii = "iii"


class MediaType(str, Enum):
    """
    Media type enumeration.

    :param tv: Television broadcast
    :type tv: str
    :param radio: Radio broadcast
    :type radio: str
    :param web: Web streaming
    :type web: str
    :param ppv: Pay-per-view
    :type ppv: str
    :param mobile: Mobile streaming
    :type mobile: str
    """

    tv = "tv"
    radio = "radio"
    web = "web"
    ppv = "ppv"
    mobile = "mobile"


# Base Models
class TeamInfo(BaseModel):
    """
    Basic team information model.

    :param id: Team ID
    :type id: Optional[int]
    :param school: School name
    :type school: str
    :param conference: Conference name
    :type conference: Optional[str]
    :param classification: Division classification
    :type classification: Optional[str]
    :param color: Primary team color
    :type color: Optional[str]
    :param alt_color: Alternate team color
    :type alt_color: Optional[str]
    :param logos: List of team logo URLs
    :type logos: Optional[List[str]]
    """

    id: Optional[int] = None
    school: str
    conference: Optional[str] = None
    classification: Optional[str] = None
    color: Optional[str] = None
    alt_color: Optional[str] = None
    logos: Optional[List[str]] = None


class Venue(BaseModel):
    """
    Venue information model.

    :param id: Venue ID
    :type id: Optional[int]
    :param name: Venue name
    :type name: Optional[str]
    :param city: Venue city
    :type city: Optional[str]
    :param state: Venue state
    :type state: Optional[str]
    :param zip: Venue zip code
    :type zip: Optional[str]
    :param country_code: Country code
    :type country_code: Optional[str]
    :param timezone: Venue timezone
    :type timezone: Optional[str]
    :param latitude: Venue latitude
    :type latitude: Optional[float]
    :param longitude: Venue longitude
    :type longitude: Optional[float]
    :param elevation: Venue elevation in feet
    :type elevation: Optional[float]
    :param capacity: Venue capacity
    :type capacity: Optional[int]
    :param year_constructed: Year venue was constructed
    :type year_constructed: Optional[int]
    :param grass: Whether venue has grass field
    :type grass: Optional[bool]
    :param dome: Whether venue is a dome
    :type dome: Optional[bool]
    """

    id: Optional[int] = None
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country_code: Optional[str] = None
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    capacity: Optional[int] = None
    year_constructed: Optional[int] = None
    grass: Optional[bool] = None
    dome: Optional[bool] = None


# Game Models
class Game(BaseModel):
    """
    Game information model for /games endpoint.

    :param id: Game ID
    :type id: int
    :param season: Season year
    :type season: int
    :param week: Week number
    :type week: int
    :param season_type: Type of season
    :type season_type: str
    :param start_date: Game start date and time
    :type start_date: datetime
    :param start_time_tbd: Whether start time is TBD
    :type start_time_tbd: bool
    :param completed: Whether game is completed
    :type completed: bool
    :param neutral_site: Whether game is at neutral site
    :type neutral_site: bool
    :param conference_game: Whether this is a conference game
    :type conference_game: Optional[bool]
    :param attendance: Game attendance
    :type attendance: Optional[int]
    :param venue_id: Venue ID
    :type venue_id: Optional[int]
    :param venue: Venue name
    :type venue: Optional[str]
    :param home_id: Home team ID
    :type home_id: Optional[int]
    :param home_team: Home team name
    :type home_team: str
    :param home_conference: Home team conference
    :type home_conference: Optional[str]
    :param home_division: Home team division
    :type home_division: Optional[str]
    :param home_points: Home team points
    :type home_points: Optional[int]
    :param home_line_scores: Home team line scores by quarter
    :type home_line_scores: Optional[List[Optional[int]]]
    :param home_post_win_prob: Home team post-game win probability
    :type home_post_win_prob: Optional[float]
    :param home_pregame_elo: Home team pregame Elo rating
    :type home_pregame_elo: Optional[int]
    :param home_postgame_elo: Home team postgame Elo rating
    :type home_postgame_elo: Optional[int]
    :param away_id: Away team ID
    :type away_id: Optional[int]
    :param away_team: Away team name
    :type away_team: str
    :param away_conference: Away team conference
    :type away_conference: Optional[str]
    :param away_division: Away team division
    :type away_division: Optional[str]
    :param away_points: Away team points
    :type away_points: Optional[int]
    :param away_line_scores: Away team line scores by quarter
    :type away_line_scores: Optional[List[Optional[int]]]
    :param away_post_win_prob: Away team post-game win probability
    :type away_post_win_prob: Optional[float]
    :param away_pregame_elo: Away team pregame Elo rating
    :type away_pregame_elo: Optional[int]
    :param away_postgame_elo: Away team postgame Elo rating
    :type away_postgame_elo: Optional[int]
    :param excitement_index: Game excitement index
    :type excitement_index: Optional[float]
    :param highlights: Link to game highlights
    :type highlights: Optional[str]
    :param notes: Game notes
    :type notes: Optional[str]
    """

    id: int
    season: int
    week: int
    season_type: str
    start_date: datetime
    start_time_tbd: bool = False
    completed: bool = False
    neutral_site: bool = False
    conference_game: Optional[bool] = None
    attendance: Optional[int] = None
    venue_id: Optional[int] = None
    venue: Optional[str] = None
    home_id: Optional[int] = None
    home_team: str
    home_conference: Optional[str] = None
    home_division: Optional[str] = None
    home_points: Optional[int] = None
    home_line_scores: Optional[List[Optional[int]]] = None
    home_post_win_prob: Optional[float] = Field(None, ge=0, le=1)
    home_pregame_elo: Optional[int] = None
    home_postgame_elo: Optional[int] = None
    away_id: Optional[int] = None
    away_team: str
    away_conference: Optional[str] = None
    away_division: Optional[str] = None
    away_points: Optional[int] = None
    away_line_scores: Optional[List[Optional[int]]] = None
    away_post_win_prob: Optional[float] = Field(None, ge=0, le=1)
    away_pregame_elo: Optional[int] = None
    away_postgame_elo: Optional[int] = None
    excitement_index: Optional[float] = None
    highlights: Optional[str] = None
    notes: Optional[str] = None

    @validator("home_points", "away_points")
    def points_must_be_non_negative(cls, v: Optional[int]) -> Optional[int]:
        """
        Validate that points are non-negative.

        :param v: Points value
        :type v: Optional[int]
        :return: Validated points value
        :rtype: Optional[int]
        :raises ValueError: If ``v`` is negative
        """
        if v is not None and v < 0:
            raise ValueError("Points cannot be negative")
        return v


class CalendarWeek(BaseModel):
    """
    Calendar week model for /calendar endpoint.

    :param season: Season year
    :type season: int
    :param week: Week number
    :type week: int
    :param season_type: Season type
    :type season_type: str
    :param first_game_start: First game start time
    :type first_game_start: datetime
    :param last_game_start: Last game start time
    :type last_game_start: datetime
    """

    season: int
    week: int
    season_type: str
    first_game_start: datetime
    last_game_start: datetime


class GameMedia(BaseModel):
    """
    Game media information model for /games/media endpoint.

    :param id: Game ID
    :type id: int
    :param season: Season year
    :type season: int
    :param week: Week number
    :type week: int
    :param season_type: Season type
    :type season_type: str
    :param start_time: Game start time
    :type start_time: datetime
    :param is_start_time_tbd: Whether start time is TBD
    :type is_start_time_tbd: bool
    :param home_team: Home team name
    :type home_team: str
    :param home_conference: Home team conference
    :type home_conference: Optional[str]
    :param away_team: Away team name
    :type away_team: str
    :param away_conference: Away team conference
    :type away_conference: Optional[str]
    :param tv: TV network
    :type tv: Optional[str]
    :param radio: Radio network
    :type radio: Optional[str]
    :param web: Web streaming service
    :type web: Optional[str]
    :param ppv: PPV information
    :type ppv: Optional[str]
    :param mobile: Mobile streaming information
    :type mobile: Optional[str]
    :param outlet: Media outlet
    :type outlet: Optional[str]
    """

    id: int
    season: int
    week: int
    season_type: str
    start_time: datetime
    is_start_time_tbd: bool = False
    home_team: str
    home_conference: Optional[str] = None
    away_team: str
    away_conference: Optional[str] = None
    tv: Optional[str] = None
    radio: Optional[str] = None
    web: Optional[str] = None
    ppv: Optional[str] = None
    mobile: Optional[str] = None
    outlet: Optional[str] = None


class GameWeather(BaseModel):
    """
    Game weather information model for /games/weather endpoint.

    :param id: Game ID
    :type id: int
    :param season: Season year
    :type season: int
    :param week: Week number
    :type week: int
    :param season_type: Season type
    :type season_type: str
    :param start_time: Game start time
    :type start_time: datetime
    :param game_indoors: Whether game is indoors
    :type game_indoors: Optional[bool]
    :param venue_id: Venue ID
    :type venue_id: Optional[int]
    :param venue: Venue name
    :type venue: Optional[str]
    :param temperature: Temperature in Fahrenheit
    :type temperature: Optional[float]
    :param dew_point: Dew point in Fahrenheit
    :type dew_point: Optional[float]
    :param humidity: Humidity percentage
    :type humidity: Optional[float]
    :param precipitation: Precipitation in inches
    :type precipitation: Optional[float]
    :param snowfall: Snowfall in inches
    :type snowfall: Optional[float]
    :param wind_direction: Wind direction in degrees
    :type wind_direction: Optional[float]
    :param wind_speed: Wind speed in mph
    :type wind_speed: Optional[float]
    :param pressure: Barometric pressure in inches
    :type pressure: Optional[float]
    :param weather_condition_code: Weather condition code
    :type weather_condition_code: Optional[str]
    :param weather_condition: Weather condition description
    :type weather_condition: Optional[str]
    """

    id: int
    season: int
    week: int
    season_type: str
    start_time: datetime
    game_indoors: Optional[bool] = None
    venue_id: Optional[int] = None
    venue: Optional[str] = None
    temperature: Optional[float] = None
    dew_point: Optional[float] = None
    humidity: Optional[float] = Field(None, ge=0, le=100)
    precipitation: Optional[float] = Field(None, ge=0)
    snowfall: Optional[float] = Field(None, ge=0)
    wind_direction: Optional[float] = Field(None, ge=0, le=360)
    wind_speed: Optional[float] = Field(None, ge=0)
    pressure: Optional[float] = None
    weather_condition_code: Optional[str] = None
    weather_condition: Optional[str] = None


# Team Records Models
class TeamRecord(BaseModel):
    """
    Win-loss record model.

    :param games: Total games played
    :type games: int
    :param wins: Number of wins
    :type wins: int
    :param losses: Number of losses
    :type losses: int
    :param ties: Number of ties
    :type ties: int
    """

    games: int
    wins: int
    losses: int
    ties: int = 0


class TeamRecords(BaseModel):
    """
    Team season records model for /records endpoint.

    :param year: Season year
    :type year: int
    :param team_id: Team ID
    :type team_id: Optional[int]
    :param team: Team name
    :type team: str
    :param conference: Conference name
    :type conference: Optional[str]
    :param division: Division classification
    :type division: Optional[str]
    :param expected_wins: Expected wins based on analytics
    :type expected_wins: Optional[float]
    :param total: Total record
    :type total: TeamRecord
    :param conference_games: Conference games record
    :type conference_games: Optional[TeamRecord]
    :param home_games: Home games record
    :type home_games: Optional[TeamRecord]
    :param away_games: Away games record
    :type away_games: Optional[TeamRecord]
    """

    year: int
    team_id: Optional[int] = None
    team: str
    conference: Optional[str] = None
    division: Optional[str] = None
    expected_wins: Optional[float] = None
    total: TeamRecord
    conference_games: Optional[TeamRecord] = None
    home_games: Optional[TeamRecord] = None
    away_games: Optional[TeamRecord] = None


# Player Game Stats Models
class PlayerGamePassing(BaseModel):
    """
    Player passing statistics for a game.

    :param player_id: Player ID
    :type player_id: int
    :param player: Player name
    :type player: str
    :param completions: Pass completions
    :type completions: Optional[int]
    :param attempts: Pass attempts
    :type attempts: Optional[int]
    :param passing_yards: Passing yards
    :type passing_yards: Optional[float]
    :param passing_tds: Passing touchdowns
    :type passing_tds: Optional[int]
    :param interceptions: Interceptions thrown
    :type interceptions: Optional[int]
    :param yards_per_attempt: Yards per pass attempt
    :type yards_per_attempt: Optional[float]
    :param completion_percentage: Completion percentage
    :type completion_percentage: Optional[float]
    """

    player_id: int
    player: str
    completions: Optional[int] = None
    attempts: Optional[int] = None
    passing_yards: Optional[float] = None
    passing_tds: Optional[int] = None
    interceptions: Optional[int] = None
    yards_per_attempt: Optional[float] = None
    completion_percentage: Optional[float] = Field(None, ge=0, le=100)


class PlayerGameRushing(BaseModel):
    """
    Player rushing statistics for a game.

    :param player_id: Player ID
    :type player_id: int
    :param player: Player name
    :type player: str
    :param carries: Number of carries
    :type carries: Optional[int]
    :param rushing_yards: Rushing yards
    :type rushing_yards: Optional[float]
    :param rushing_tds: Rushing touchdowns
    :type rushing_tds: Optional[int]
    :param yards_per_carry: Yards per carry
    :type yards_per_carry: Optional[float]
    :param long_rushing: Longest rush
    :type long_rushing: Optional[int]
    """

    player_id: int
    player: str
    carries: Optional[int] = None
    rushing_yards: Optional[float] = None
    rushing_tds: Optional[int] = None
    yards_per_carry: Optional[float] = None
    long_rushing: Optional[int] = None


class PlayerGameReceiving(BaseModel):
    """
    Player receiving statistics for a game.

    :param player_id: Player ID
    :type player_id: int
    :param player: Player name
    :type player: str
    :param receptions: Number of receptions
    :type receptions: Optional[int]
    :param receiving_yards: Receiving yards
    :type receiving_yards: Optional[float]
    :param receiving_tds: Receiving touchdowns
    :type receiving_tds: Optional[int]
    :param yards_per_reception: Yards per reception
    :type yards_per_reception: Optional[float]
    :param long_reception: Longest reception
    :type long_reception: Optional[int]
    """

    player_id: int
    player: str
    receptions: Optional[int] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[int] = None
    yards_per_reception: Optional[float] = None
    long_reception: Optional[int] = None


class PlayerGameDefensive(BaseModel):
    """
    Player defensive statistics for a game.

    :param player_id: Player ID
    :type player_id: int
    :param player: Player name
    :type player: str
    :param tackles: Total tackles
    :type tackles: Optional[float]
    :param tackles_for_loss: Tackles for loss
    :type tackles_for_loss: Optional[float]
    :param sacks: Sacks
    :type sacks: Optional[float]
    :param interceptions: Interceptions
    :type interceptions: Optional[int]
    :param passes_defended: Passes defended
    :type passes_defended: Optional[int]
    :param fumbles_forced: Fumbles forced
    :type fumbles_forced: Optional[int]
    :param fumbles_recovered: Fumbles recovered
    :type fumbles_recovered: Optional[int]
    :param defensive_tds: Defensive touchdowns
    :type defensive_tds: Optional[int]
    """

    player_id: int
    player: str
    tackles: Optional[float] = None
    tackles_for_loss: Optional[float] = None
    sacks: Optional[float] = None
    interceptions: Optional[int] = None
    passes_defended: Optional[int] = None
    fumbles_forced: Optional[int] = None
    fumbles_recovered: Optional[int] = None
    defensive_tds: Optional[int] = None


class PlayerGameStats(BaseModel):
    """
    Player game statistics model for /games/players endpoint.

    :param game_id: Game ID
    :type game_id: int
    :param team: Team name
    :type team: str
    :param conference: Conference name
    :type conference: Optional[str]
    :param category: Stats category
    :type category: str
    :param passing: Passing statistics
    :type passing: Optional[List[PlayerGamePassing]]
    :param rushing: Rushing statistics
    :type rushing: Optional[List[PlayerGameRushing]]
    :param receiving: Receiving statistics
    :type receiving: Optional[List[PlayerGameReceiving]]
    :param defensive: Defensive statistics
    :type defensive: Optional[List[PlayerGameDefensive]]
    """

    game_id: int
    team: str
    conference: Optional[str] = None
    category: str
    passing: Optional[List[PlayerGamePassing]] = None
    rushing: Optional[List[PlayerGameRushing]] = None
    receiving: Optional[List[PlayerGameReceiving]] = None
    defensive: Optional[List[PlayerGameDefensive]] = None


# Team Game Stats Models
class TeamGameStats(BaseModel):
    """
    Team game statistics model for /games/teams endpoint.

    :param game_id: Game ID
    :type game_id: int
    :param school: School name
    :type school: str
    :param conference: Conference name
    :type conference: Optional[str]
    :param home_away: Home or away
    :type home_away: str
    :param opponent: Opponent name
    :type opponent: str
    :param points: Points scored
    :type points: int
    :param total_yards: Total yards
    :type total_yards: Optional[float]
    :param net_passing_yards: Net passing yards
    :type net_passing_yards: Optional[float]
    :param completion_attempts: Completion attempts
    :type completion_attempts: Optional[str]
    :param passing_tds: Passing touchdowns
    :type passing_tds: Optional[int]
    :param rushing_yards: Rushing yards
    :type rushing_yards: Optional[float]
    :param rushing_attempts: Rushing attempts
    :type rushing_attempts: Optional[int]
    :param rushing_tds: Rushing touchdowns
    :type rushing_tds: Optional[int]
    :param first_downs: First downs
    :type first_downs: Optional[int]
    :param third_down_efficiency: Third down efficiency
    :type third_down_efficiency: Optional[str]
    :param fourth_down_efficiency: Fourth down efficiency
    :type fourth_down_efficiency: Optional[str]
    :param total_penalties: Total penalties
    :type total_penalties: Optional[int]
    :param penalty_yards: Penalty yards
    :type penalty_yards: Optional[int]
    :param turnovers: Turnovers
    :type turnovers: Optional[int]
    :param fumbles_lost: Fumbles lost
    :type fumbles_lost: Optional[int]
    :param interceptions_thrown: Interceptions thrown
    :type interceptions_thrown: Optional[int]
    :param possession_time: Possession time in seconds
    :type possession_time: Optional[str]
    """

    game_id: int
    school: str
    conference: Optional[str] = None
    home_away: str
    opponent: str
    points: int
    total_yards: Optional[float] = None
    net_passing_yards: Optional[float] = None
    completion_attempts: Optional[str] = None
    passing_tds: Optional[int] = None
    rushing_yards: Optional[float] = None
    rushing_attempts: Optional[int] = None
    rushing_tds: Optional[int] = None
    first_downs: Optional[int] = None
    third_down_efficiency: Optional[str] = None
    fourth_down_efficiency: Optional[str] = None
    total_penalties: Optional[int] = None
    penalty_yards: Optional[int] = None
    turnovers: Optional[int] = None
    fumbles_lost: Optional[int] = None
    interceptions_thrown: Optional[int] = None
    possession_time: Optional[str] = None


# Advanced Box Score Models
class BoxScoreTeamStats(BaseModel):
    """
    Advanced team statistics for box score.

    :param team: Team name
    :type team: str
    :param points: Points scored
    :type points: int
    :param drives: Number of drives
    :type drives: Optional[int]
    :param scoring_opportunities: Scoring opportunities
    :type scoring_opportunities: Optional[int]
    :param points_per_opportunity: Points per scoring opportunity
    :type points_per_opportunity: Optional[float]
    :param explosiveness: Explosiveness metric
    :type explosiveness: Optional[float]
    :param play_count: Total plays
    :type play_count: Optional[int]
    :param stuff_rate: Stuff rate
    :type stuff_rate: Optional[float]
    :param line_yards: Line yards metric
    :type line_yards: Optional[float]
    :param second_level_yards: Second level yards metric
    :type second_level_yards: Optional[float]
    :param open_field_yards: Open field yards metric
    :type open_field_yards: Optional[float]
    :param success_rate: Success rate
    :type success_rate: Optional[float]
    :param field_position: Average field position
    :type field_position: Optional[float]
    :param havoc: Havoc rate
    :type havoc: Optional[float]
    """

    team: str
    points: int
    drives: Optional[int] = None
    scoring_opportunities: Optional[int] = None
    points_per_opportunity: Optional[float] = None
    explosiveness: Optional[float] = None
    play_count: Optional[int] = None
    stuff_rate: Optional[float] = None
    line_yards: Optional[float] = None
    second_level_yards: Optional[float] = None
    open_field_yards: Optional[float] = None
    success_rate: Optional[float] = None
    field_position: Optional[float] = None
    havoc: Optional[float] = None


class BoxScorePlayerUsage(BaseModel):
    """
    Player usage statistics in box score.

    :param player: Player name
    :type player: str
    :param team: Team name
    :type team: str
    :param position: Player position
    :type position: str
    :param total: Total usage
    :type total: float
    :param quarter1: First quarter usage
    :type quarter1: Optional[float]
    :param quarter2: Second quarter usage
    :type quarter2: Optional[float]
    :param quarter3: Third quarter usage
    :type quarter3: Optional[float]
    :param quarter4: Fourth quarter usage
    :type quarter4: Optional[float]
    :param rushing: Rushing usage
    :type rushing: Optional[float]
    :param passing: Passing usage
    :type passing: Optional[float]
    """

    player: str
    team: str
    position: str
    total: float
    quarter1: Optional[float] = None
    quarter2: Optional[float] = None
    quarter3: Optional[float] = None
    quarter4: Optional[float] = None
    rushing: Optional[float] = None
    passing: Optional[float] = None


class BoxScorePlayerPPA(BaseModel):
    """
    Player PPA (Predicted Points Added) in box score.

    :param player: Player name
    :type player: str
    :param team: Team name
    :type team: str
    :param position: Player position
    :type position: str
    :param average_ppa: Average PPA per play
    :type average_ppa: float
    :param total_ppa: Total PPA
    :type total_ppa: float
    :param rushing: Rushing PPA
    :type rushing: Optional[float]
    :param passing: Passing PPA
    :type passing: Optional[float]
    """

    player: str
    team: str
    position: str
    average_ppa: float
    total_ppa: float
    rushing: Optional[float] = None
    passing: Optional[float] = None


class AdvancedBoxScore(BaseModel):
    """
    Advanced box score model for /games/box/advanced endpoint.

    :param game_id: Game ID
    :type game_id: int
    :param home_team: Home team stats
    :type home_team: BoxScoreTeamStats
    :param away_team: Away team stats
    :type away_team: BoxScoreTeamStats
    :param players: Player-level statistics
    :type players: Optional[Dict[str, Any]]
    """

    game_id: int
    home_team: BoxScoreTeamStats
    away_team: BoxScoreTeamStats
    players: Optional[Dict[str, Any]] = None


class GameLine(BaseModel):
    """
    Game line model for /scoreboard endpoint.

    :param home_team: Spread for home team
    :type home_team: float
    :param away_team: Spread for away team
    :type away_team: float
    :param over_under: Over/Under line
    :type over_under: float
    """

    home_team: float
    away_team: float
    over_under: float


class Scoreboard(BaseModel):
    """
    Scoreboard model for /scoreboard endpoint.

    :param id: Game ID
    :type id: int
    :param season: Season year
    :type season: int
    :param week: Week number
    :type week: int
    :param season_type: Type of season
    :type season_type: str
    :param start_date: Game start date and time
    :type start_date: datetime
    :param home_team: Home team name
    :type home_team: str
    :param away_team: Away team name
    :type away_team: str
    :param home_points: Home team points
    :type home_points: Optional[int]
    :param away_points: Away team points
    :type away_points: Optional[int]
    :param neutral_site: Whether game is at neutral site
    :type neutral_site: bool
    :param conference_game: Whether this is a conference game
    :type conference_game: Optional[bool]
    :param line: Game line/spread information
    :type line: Optional[GameLine]
    """

    id: int
    season: int
    week: int
    season_type: str
    start_date: datetime
    home_team: str
    away_team: str
    home_points: Optional[int] = None
    away_points: Optional[int] = None
    neutral_site: bool = False
    conference_game: Optional[bool] = None
    line: Optional[GameLine] = None

    @validator("home_points", "away_points")
    def points_must_be_non_negative(cls, v: Optional[int]) -> Optional[int]:
        """Ensure point totals are not negative.

        :param v: Points value
        :type v: Optional[int]
        :return: Validated points value
        :rtype: Optional[int]
        :raises ValueError: If ``v`` is negative
        """

        if v is not None and v < 0:
            raise ValueError("Points cannot be negative")
        return v
