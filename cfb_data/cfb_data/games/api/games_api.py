"""Game-specific endpoint handlers for the CFBD API."""

from __future__ import annotations

from cfb_data.base.api.base_api import CFBDAPIBase, route
from cfb_data.base.types import (
    JSONObject,
    QueryParameters,
    json_object,
    json_object_list,
    query_parameters,
)
from cfb_data.games.models.pandera.responses import (
    CalendarWeekSchema,
    GameMediaSchema,
    GameSchema,
    GameWeatherSchema,
    PlayerGameStatsSchema,
    ScoreboardSchema,
    TeamGameStatsSchema,
    TeamRecordsSchema,
)
from cfb_data.games.models.pydantic.requests import (
    AdvancedBoxScoreRequest,
    CalendarRequest,
    GameMediaRequest,
    GamesRequest,
    GameWeatherRequest,
    PlayerGameStatsRequest,
    RecordsRequest,
    ScoreboardRequest,
    TeamGameStatsRequest,
)
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    ScoreboardGame,
    TeamGameStats,
    TeamRecords,
)


class CFBDGamesAPI(CFBDAPIBase):
    """Games-specific endpoints for the College Football Data API."""

    @route(
        "/games",
        response_model=Game,
        dataframe_schema=GameSchema,
    )
    async def _get_games(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get game information.

        :param params: Query parameters including year, week, seasonType, team,
            home, away, conference, classification, id, competition, and round.
        :type params: Dict[str, Any]
        :return: List of game dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Validate using request model instead of hard-coded check
        request: GamesRequest = GamesRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(await self._make_request("/games", validated_params))

    @route(
        "/records",
        response_model=TeamRecords,
        dataframe_schema=TeamRecordsSchema,
    )
    async def _get_team_records(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get team records by year.

        :param params: Query parameters including year, team, conference
        :type params: Dict[str, Any]
        :return: List of team record dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If parameters are invalid.
        """
        request: RecordsRequest = RecordsRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(await self._make_request("/records", validated_params))

    @route(
        "/calendar",
        response_model=CalendarWeek,
        dataframe_schema=CalendarWeekSchema,
    )
    async def _get_calendar(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get calendar/weeks for a given year.

        :param params: Query parameters including year (required)
        :type params: Dict[str, Any]
        :return: List of week dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Validate using request model instead of hard-coded check
        request: CalendarRequest = CalendarRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(await self._make_request("/calendar", validated_params))

    @route(
        "/scoreboard",
        response_model=ScoreboardGame,
        dataframe_schema=ScoreboardSchema,
    )
    async def _get_scoreboard(self, params: QueryParameters) -> list[JSONObject]:
        """Return current scoreboard data.

        :param params: Optional classification and conference filters.
        :return: Current scoreboard games in API order.
        :raises ValidationError: If a parameter is invalid or unsupported.
        """
        request = ScoreboardRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(
            await self._make_request("/scoreboard", validated_params)
        )

    @route(
        "/games/media",
        response_model=GameMedia,
        dataframe_schema=GameMediaSchema,
    )
    async def _get_game_media(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get game media information and types.

        :param params: Query parameters including year (required), week, seasonType, team, conference, mediaType, classification
        :type params: Dict[str, Any]
        :return: List of game media dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Validate using request model instead of hard-coded check
        request: GameMediaRequest = GameMediaRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(
            await self._make_request("/games/media", validated_params)
        )

    @route(
        "/games/weather",
        response_model=GameWeather,
        dataframe_schema=GameWeatherSchema,
    )
    async def _get_game_weather(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get game weather information.

        :param params: Query parameters including gameId, year, week, seasonType, team, conference
        :type params: Dict[str, Any]
        :return: List of game weather dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If parameters are invalid.
        """
        request: GameWeatherRequest = GameWeatherRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(
            await self._make_request("/games/weather", validated_params)
        )

    @route(
        "/games/players",
        response_model=PlayerGameStats,
        dataframe_schema=PlayerGameStatsSchema,
    )
    async def _get_player_game_stats(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get player statistics by game.

        :param params: Query parameters including year, week, seasonType, team, conference, category, gameId
        :type params: Dict[str, Any]
        :return: List of player game statistics dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If parameters are invalid.
        """
        # Use model validation instead of commented-out hard-coded check
        request: PlayerGameStatsRequest = PlayerGameStatsRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(
            await self._make_request("/games/players", validated_params)
        )

    @route(
        "/games/teams",
        response_model=TeamGameStats,
        dataframe_schema=TeamGameStatsSchema,
    )
    async def _get_team_game_stats(self, params: QueryParameters) -> list[JSONObject]:
        """
        Get team statistics by game.

        :param params: Query parameters including year (required), week, seasonType, team, conference, gameId, classification
        :type params: Dict[str, Any]
        :return: List of team game statistics dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Use model validation with complex conditional logic instead of commented-out hard-coded check
        request: TeamGameStatsRequest = TeamGameStatsRequest.model_validate(params)
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object_list(
            await self._make_request("/games/teams", validated_params)
        )

    @route(
        "/game/box/advanced",
        response_model=AdvancedBoxScore,
        dataframe_schema=None,
    )
    async def _get_box_scores(self, params: QueryParameters) -> JSONObject:
        """
        Get box score data for a specific game.

        :param params: Query parameters including id (required)
        :type params: Dict[str, Any]
        :return: Box score data dictionary
        :rtype: Dict[str, Any]
        :raises ValidationError: If required parameters are missing or invalid.
        """
        # Validate using request model instead of hard-coded check
        request: AdvancedBoxScoreRequest = AdvancedBoxScoreRequest.model_validate(
            params
        )
        validated_params = query_parameters(
            request.model_dump(exclude_none=True, by_alias=True)
        )
        return json_object(
            await self._make_request("/game/box/advanced", validated_params)
        )
