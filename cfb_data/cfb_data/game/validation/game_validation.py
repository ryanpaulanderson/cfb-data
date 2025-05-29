"""Validation wrappers for game endpoints."""

from typing import Any, Dict, List, cast

from cfb_data.base.validation.validation_api import CFBDValidationAPI
from cfb_data.game.api.game_api import CFBDGamesAPI
from cfb_data.game.models.pydantic.responses import (
    AdvancedBoxScore,
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
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
        result = await self.make_request_validated(
            self._get_games._api_path, Game, params
        )
        return cast(List[Game], result)

    async def get_team_records_validated(
        self, params: Dict[str, Any]
    ) -> List[TeamRecords]:
        """Return validated team records.

        :param params: Query parameters to pass to ``/records``
        :type params: Dict[str, Any]
        :return: List of validated :class:`TeamRecords` models
        :rtype: List[TeamRecords]
        """
        result = await self.make_request_validated(
            self._get_team_records._api_path,
            TeamRecords,
            params,
        )
        return cast(List[TeamRecords], result)

    async def get_calendar_validated(
        self, params: Dict[str, Any]
    ) -> List[CalendarWeek]:
        """Return validated calendar weeks.

        :param params: Query parameters for ``/calendar``
        :type params: Dict[str, Any]
        :return: List of validated :class:`CalendarWeek` models
        :rtype: List[CalendarWeek]
        """
        result = await self.make_request_validated(
            self._get_calendar._api_path,
            CalendarWeek,
            params,
        )
        return cast(List[CalendarWeek], result)

    async def get_game_media_validated(self, params: Dict[str, Any]) -> List[GameMedia]:
        """Return validated game media information.

        :param params: Query parameters for ``/games/media``
        :type params: Dict[str, Any]
        :return: List of validated :class:`GameMedia` models
        :rtype: List[GameMedia]
        """
        result = await self.make_request_validated(
            self._get_game_media._api_path,
            GameMedia,
            params,
        )
        return cast(List[GameMedia], result)

    async def get_game_weather_validated(
        self, params: Dict[str, Any]
    ) -> List[GameWeather]:
        """Return validated game weather information.

        :param params: Query parameters for ``/games/weather``
        :type params: Dict[str, Any]
        :return: List of validated :class:`GameWeather` models
        :rtype: List[GameWeather]
        """
        result = await self.make_request_validated(
            self._get_game_weather._api_path,
            GameWeather,
            params,
        )
        return cast(List[GameWeather], result)

    async def get_player_game_stats_validated(
        self, params: Dict[str, Any]
    ) -> List[PlayerGameStats]:
        """Return validated player statistics for each game.

        :param params: Query parameters for ``/games/players``
        :type params: Dict[str, Any]
        :return: List of validated :class:`PlayerGameStats` models
        :rtype: List[PlayerGameStats]
        """
        result = await self.make_request_validated(
            self._get_player_game_stats._api_path,
            PlayerGameStats,
            params,
        )
        return cast(List[PlayerGameStats], result)

    async def get_team_game_stats_validated(
        self, params: Dict[str, Any]
    ) -> List[TeamGameStats]:
        """Return validated team statistics for each game.

        :param params: Query parameters for ``/games/teams``
        :type params: Dict[str, Any]
        :return: List of validated :class:`TeamGameStats` models
        :rtype: List[TeamGameStats]
        """
        result = await self.make_request_validated(
            self._get_team_game_stats._api_path,
            TeamGameStats,
            params,
        )
        return cast(List[TeamGameStats], result)

    async def get_box_scores_validated(
        self, params: Dict[str, Any]
    ) -> AdvancedBoxScore:
        """Return validated advanced box score for a game.

        :param params: Query parameters for ``/games/box/advanced``
        :type params: Dict[str, Any]
        :return: Parsed :class:`AdvancedBoxScore` model
        :rtype: AdvancedBoxScore
        """
        result = await self.make_request_validated(
            self._get_box_scores._api_path,
            AdvancedBoxScore,
            params,
        )
        return cast(AdvancedBoxScore, result)
