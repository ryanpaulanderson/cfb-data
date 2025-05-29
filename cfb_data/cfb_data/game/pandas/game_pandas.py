"""Pandas-returning wrappers for game endpoints."""

from typing import Any, Dict

import pandas as pd
from cfb_data.base.pandas.pandas_api import CFBDPanderaAPI
from cfb_data.game.models.pandera.responses import (
    CalendarWeekSchema,
    GameMediaSchema,
    GameSchema,
    GameWeatherSchema,
    PlayerGameStatsSchema,
    TeamGameStatsSchema,
    TeamRecordsSchema,
)
from cfb_data.game.models.pydantic.responses import (
    CalendarWeek,
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)
from cfb_data.game.validation.game_validation import CFBDGamesValidationAPI


class CFBDGamesPandasAPI(CFBDGamesValidationAPI, CFBDPanderaAPI):
    """Games API that returns ``pandas.DataFrame`` objects."""

    async def get_games_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return games as a validated DataFrame.

        :param params: Query parameters passed to the ``/games`` endpoint
        :type params: Dict[str, Any]
        :return: Validated DataFrame of games
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_games._api_path, Game, GameSchema, params
        )

    async def get_team_records_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return team records as a validated DataFrame.

        :param params: Query parameters passed to ``/records``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of team records
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_team_records._api_path, TeamRecords, TeamRecordsSchema, params
        )

    async def get_calendar_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return calendar weeks as a validated DataFrame.

        :param params: Query parameters passed to ``/calendar``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of calendar weeks
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_calendar._api_path, CalendarWeek, CalendarWeekSchema, params
        )

    async def get_game_media_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return game media information as a validated DataFrame.

        :param params: Query parameters passed to ``/games/media``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of game media
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_game_media._api_path, GameMedia, GameMediaSchema, params
        )

    async def get_game_weather_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return game weather information as a validated DataFrame.

        :param params: Query parameters passed to ``/games/weather``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of game weather
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_game_weather._api_path, GameWeather, GameWeatherSchema, params
        )

    async def get_player_game_stats_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return player stats for each game as a validated DataFrame.

        :param params: Query parameters passed to ``/games/players``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of player statistics
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_player_game_stats._api_path,
            PlayerGameStats,
            PlayerGameStatsSchema,
            params,
        )

    async def get_team_game_stats_df(self, params: Dict[str, Any]) -> pd.DataFrame:
        """Return team stats for each game as a validated DataFrame.

        :param params: Query parameters passed to ``/games/teams``
        :type params: Dict[str, Any]
        :return: Validated DataFrame of team statistics
        :rtype: pandas.DataFrame
        """
        return await self.make_request_pandas(
            self._get_team_game_stats._api_path,
            TeamGameStats,
            TeamGameStatsSchema,
            params,
        )
