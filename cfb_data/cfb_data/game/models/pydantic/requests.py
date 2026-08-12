"""College Football Data API game request models.

Pydantic models for validating API request parameters for CFBD game endpoints.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.base.validation import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
    validate_at_least_one_of,
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

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    home: str | None = None
    away: str | None = None
    conference: str | None = None
    classification: Classification | None = None
    id: int | None = Field(default=None, gt=0)
    competition: PlayoffCompetition | None = None
    round: PlayoffRound | None = None

    @model_validator(mode="after")
    def validate_year_or_id(self) -> "GamesRequest":
        """
        Validate that year is required when id is not specified.

        API Rule: "Required year filter (except when id is specified)"

        :return: Validated model instance
        :rtype: GamesRequest
        :raises ValueError: If neither year nor id is provided.
        """
        validate_year_or_id_required(self.year, self.id, "id")
        if self.round is not None and self.competition is None:
            raise ValueError(
                "competition parameter is required when round is specified"
            )
        if (
            self.competition is PlayoffCompetition.cfp
            and self.season_type is not None
            and self.season_type not in {SeasonType.postseason, SeasonType.both}
        ):
            raise ValueError("CFP games are postseason games")
        return self


class CalendarRequest(BaseModel):
    """
    Request parameters for /calendar endpoint.

    :param year: Required year filter
    :type year: int
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)


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

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    team: str | None = None
    conference: str | None = None

    @model_validator(mode="after")
    def validate_year_or_team(self) -> "RecordsRequest":
        """Require one of the two upstream record selectors.

        :return: The validated request.
        :raises ValueError: If neither ``year`` nor ``team`` is provided.
        """
        validate_at_least_one_of(
            {"year": self.year, "team": self.team},
            ("year", "team"),
        )
        return self


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

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    media_type: MediaType | None = Field(default=None, alias="mediaType")
    classification: Classification | None = None


class GameWeatherRequest(BaseModel):
    """
    Request parameters for /games/weather endpoint.

    :param game_id: Optional game ID filter
    :type game_id: Optional[int]
    :param year: Optional year filter (required if game_id not provided)
    :type year: Optional[int]
    :param week: Optional week filter
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter
    :type team: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_id: int | None = Field(default=None, gt=0, alias="gameId")
    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_weather_requirements(self) -> "GameWeatherRequest":
        """
        Validate requirements for /games/weather endpoint.

        API Rules:
        - If game_id is provided, other filters are ignored (no validation needed)
        - If game_id is not provided, year is the minimum required field

        :return: Validated model instance
        :rtype: GameWeatherRequest
        :raises ValueError: If validation rules are violated.
        """
        if self.game_id is None and self.year is None:
            raise ValueError("year is required when game_id is not specified")
        return self


class PlayerGameStatsRequest(BaseModel):
    """
    Request parameters for /games/players endpoint.

    :param year: Optional year filter (required along with one of week, team, or conference, unless id is specified)
    :type year: Optional[int]
    :param week: Optional week filter (required if team and conference not specified)
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter (required if week and conference not specified)
    :type team: Optional[str]
    :param conference: Optional conference filter (required if week and team not specified)
    :type conference: Optional[str]
    :param category: Optional stats category filter
    :type category: Optional[str]
    :param id: Optional game ID filter
    :type id: Optional[int]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    category: str | None = None
    id: int | None = Field(default=None, gt=0)
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_player_stats_requirements(self) -> "PlayerGameStatsRequest":
        """
        Validate complex conditional requirements for /games/players endpoint.

        API Rules:
        - id bypasses all other requirements
        - If id is not provided, year is required
        - If year is provided, at least one of week, team, or conference must also be provided

        :return: Validated model instance
        :rtype: PlayerGameStatsRequest
        :raises ValueError: If validation rules are violated.
        """
        validate_team_game_stats_logic(
            self.year, self.week, self.team, self.conference, self.id
        )
        return self


class TeamGameStatsRequest(BaseModel):
    """
    Request parameters for /games/teams endpoint.

    :param year: Optional year filter (required along with one of week, team, or conference, unless id is specified)
    :type year: Optional[int]
    :param week: Optional week filter (required if team and conference not specified)
    :type week: Optional[int]
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param team: Optional team filter (required if week and conference not specified)
    :type team: Optional[str]
    :param conference: Optional conference filter (required if week and team not specified)
    :type conference: Optional[str]
    :param id: Optional game ID filter
    :type id: Optional[int]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    id: int | None = Field(default=None, gt=0)
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_team_stats_requirements(self) -> "TeamGameStatsRequest":
        """
        Validate complex conditional requirements for /games/teams endpoint.

        API Rules:
        - year is required (along with one of week, team, or conference), unless id is specified
        - At least one of week, team, or conference must be specified when year is provided

        :return: Validated model instance
        :rtype: TeamGameStatsRequest
        :raises ValueError: If validation rules are violated.
        """
        validate_team_game_stats_logic(
            self.year, self.week, self.team, self.conference, self.id
        )
        return self


class AdvancedBoxScoreRequest(BaseModel):
    """
    Request parameters for /game/box/advanced endpoint.

    :param id: Required game ID
    :type id: int
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: int = Field(gt=0)
