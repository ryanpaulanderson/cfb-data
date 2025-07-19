"""
College Football Data API - Game Request Models
Pydantic models for validating API request parameters for CFBD game endpoints
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.base.validation import (
    Classification,
    SeasonType,
    validate_team_game_stats_logic,
    validate_year_or_id_required,
)


class GamesRequest(BaseModel):
    """
    Request parameters for /games endpoint.

    :param year: Required year filter (except when id is specified)
    :type year: Optional[int]
    :param week: Optional week filter
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter
    :type team: Optional[str]
    :param home: Optional home team filter
    :type home: Optional[str]
    :param away: Optional away team filter
    :type away: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    :param id: Game id filter to retrieve a single game
    :type id: Optional[int]
    """

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    home: Optional[str] = None
    away: Optional[str] = None
    conference: Optional[str] = None
    classification: Optional[Classification] = None
    id: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_year_or_id(self) -> "GamesRequest":
        """
        Validate that year is required when id is not specified.

        API Rule: "Required year filter (except when id is specified)"

        :return: Validated model instance
        :rtype: GamesRequest
        :raises ValueError: If neither year nor id is provided  # noqa: DAR402
        """
        validate_year_or_id_required(self.year, self.id, "id")
        return self


class CalendarRequest(BaseModel):
    """
    Request parameters for /calendar endpoint.

    :param year: Required year filter
    :type year: int
    """

    model_config = ConfigDict(populate_by_name=True)

    year: int = Field(ge=1869, le=2030)


class RecordsRequest(BaseModel):
    """
    Request parameters for /records endpoint.

    :param year: Optional year filter
    :type year: Optional[int]
    :param team: Optional team filter
    :type team: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    """

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    team: Optional[str] = None
    conference: Optional[str] = None


class GameMediaRequest(BaseModel):
    """
    Request parameters for /games/media endpoint.

    :param year: Required year filter
    :type year: int
    :param week: Optional week filter
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter
    :type team: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    :param media_type: Optional media type filter
    :type media_type: Optional[str]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True)

    year: int = Field(ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    media_type: Optional[str] = Field(default=None, alias="mediaType")
    classification: Optional[Classification] = None


class GameWeatherRequest(BaseModel):
    """
    Request parameters for /games/weather endpoint.

    :param game_id: Optional game ID filter
    :type game_id: Optional[int]
    :param year: Optional year filter
    :type year: Optional[int]
    :param week: Optional week filter
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter
    :type team: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    """

    model_config = ConfigDict(populate_by_name=True)

    game_id: Optional[int] = Field(default=None, ge=0, alias="gameId")
    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None


class PlayerGameStatsRequest(BaseModel):
    """
    Request parameters for /games/players endpoint.

    :param year: Optional year filter
    :type year: Optional[int]
    :param week: Optional week filter
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter
    :type team: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    :param category: Optional stats category filter
    :type category: Optional[str]
    :param game_id: Optional game ID filter
    :type game_id: Optional[int]
    """

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    category: Optional[str] = None
    game_id: Optional[int] = Field(default=None, ge=0, alias="gameId")


class TeamGameStatsRequest(BaseModel):
    """
    Request parameters for /games/teams endpoint.

    :param year: Optional year filter (required along with one of week, team, or conference, unless game_id is specified)
    :type year: Optional[int]
    :param week: Optional week filter (required if team and conference not specified)
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter (required if week and conference not specified)
    :type team: Optional[str]
    :param conference: Optional conference filter (required if week and team not specified)
    :type conference: Optional[str]
    :param game_id: Optional game ID filter
    :type game_id: Optional[int]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    game_id: Optional[int] = Field(default=None, ge=0, alias="gameId")
    classification: Optional[Classification] = None

    @model_validator(mode="after")
    def validate_team_stats_requirements(self) -> "TeamGameStatsRequest":
        """
        Validate complex conditional requirements for /games/teams endpoint.

        API Rules:
        - year is required (along with one of week, team, or conference), unless id is specified
        - At least one of week, team, or conference must be specified when year is provided

        :return: Validated model instance
        :rtype: TeamGameStatsRequest
        :raises ValueError: If validation rules are violated  # noqa: DAR402
        """
        validate_team_game_stats_logic(
            self.year, self.week, self.team, self.conference, self.game_id
        )
        return self


class AdvancedBoxScoreRequest(BaseModel):
    """
    Request parameters for /games/box/advanced endpoint.

    :param game_id: Required game ID
    :type game_id: int
    """

    model_config = ConfigDict(populate_by_name=True)

    game_id: int = Field(ge=0, alias="gameId")
