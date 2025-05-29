"""Validation wrappers for game endpoints."""

from typing import Any, Dict, List

from cfb_data.base.validation.validation_api import CFBDValidationAPI
from cfb_data.game.api.game_api import CFBDGamesAPI
from cfb_data.game.models.pydantic.responses import (
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
    AdvancedBoxScore,
)


class CFBDGamesValidationAPI(CFBDGamesAPI, CFBDValidationAPI):
    """Games API with additional response validation."""

    async def get_games_validated(self, params: Dict[str, Any]) -> List[Game]:
        """Return validated games for the given parameters.

        :param params: Query parameters to pass to ``/games``
        :type params: Dict[str, Any]
        :return: List of validated :class:`Game` models
        :rtype: List[Game]

        """
        data: List[Dict[str, Any]] = await self._get_games(params)
        return [Game.model_validate(item) for item in data]

    async def get_team_records_validated(
        self, params: Dict[str, Any]
    ) -> List[TeamRecords]:
        """Return validated team records.

        :param params: Query parameters to pass to ``/records``
        :type params: Dict[str, Any]
        :return: List of validated :class:`TeamRecords` models
        :rtype: List[TeamRecords]
        """
        data: List[Dict[str, Any]] = await self._get_team_records(params)
        return [TeamRecords.model_validate(item) for item in data]

    async def get_calendar_validated(
        self, params: Dict[str, Any]
    ) -> List[CalendarWeek]:
        """Return validated calendar weeks.

        :param params: Query parameters for ``/calendar``
        :type params: Dict[str, Any]
        :return: List of validated :class:`CalendarWeek` models
        :rtype: List[CalendarWeek]
        """
        data: List[Dict[str, Any]] = await self._get_calendar(params)
        return [CalendarWeek.model_validate(item) for item in data]

    async def get_game_media_validated(self, params: Dict[str, Any]) -> List[GameMedia]:
        """Return validated game media information.

        :param params: Query parameters for ``/games/media``
        :type params: Dict[str, Any]
        :return: List of validated :class:`GameMedia` models
        :rtype: List[GameMedia]
        """
        data: List[Dict[str, Any]] = await self._get_game_media(params)
        return [GameMedia.model_validate(item) for item in data]

    async def get_game_weather_validated(
        self, params: Dict[str, Any]
    ) -> List[GameWeather]:
        """Return validated game weather information.

        :param params: Query parameters for ``/games/weather``
        :type params: Dict[str, Any]
        :return: List of validated :class:`GameWeather` models
        :rtype: List[GameWeather]
        """
        data: List[Dict[str, Any]] = await self._get_game_weather(params)
        return [GameWeather.model_validate(item) for item in data]

    async def get_player_game_stats_validated(
        self, params: Dict[str, Any]
    ) -> List[PlayerGameStats]:
        """Return validated player statistics for each game.

        :param params: Query parameters for ``/games/players``
        :type params: Dict[str, Any]
        :return: List of validated :class:`PlayerGameStats` models
        :rtype: List[PlayerGameStats]
        """
        data: List[Dict[str, Any]] = await self._get_player_game_stats(params)
        return [PlayerGameStats.model_validate(item) for item in data]

    async def get_team_game_stats_validated(
        self, params: Dict[str, Any]
    ) -> List[TeamGameStats]:
        """Return validated team statistics for each game.

        :param params: Query parameters for ``/games/teams``
        :type params: Dict[str, Any]
        :return: List of validated :class:`TeamGameStats` models
        :rtype: List[TeamGameStats]
        """
        data: List[Dict[str, Any]] = await self._get_team_game_stats(params)
        return [TeamGameStats.model_validate(item) for item in data]

    async def get_box_scores_validated(
        self, params: Dict[str, Any]
    ) -> AdvancedBoxScore:
        """Return validated advanced box score for a game.

        :param params: Query parameters for ``/games/box/advanced``
        :type params: Dict[str, Any]
        :return: Parsed :class:`AdvancedBoxScore` model
        :rtype: AdvancedBoxScore
        """
        data: Dict[str, Any] = await self._get_box_scores(params)
        return AdvancedBoxScore.model_validate(data)
