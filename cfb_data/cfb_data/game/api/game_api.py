"""
College Football Data API Client - Base and Games Module
Async HTTP client for interacting with the CFBD API v2
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Union, Any, Callable, TypeVar, cast
from functools import wraps
from abc import ABC
import json

from cfb_data.base.api.base_api import route, CFBDAPIBase


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


class CFBDGamesAPI(CFBDAPIBase):
    """Games-specific endpoints for College Football Data API."""

    @route("/games")
    async def _get_games(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get game information.

        :param params: Query parameters including year (required), week, seasonType, team, home, away, conference, division, id
        :type params: Dict[str, Any]
        :return: List of game dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If required parameters are missing
        """
        if "year" not in params:
            raise ValueError("year parameter is required for /games endpoint")

        return await self._make_request("/games", params)

    @route("/records")
    async def _get_team_records(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get team records by year.

        :param params: Query parameters including year, team, conference
        :type params: Dict[str, Any]
        :return: List of team record dictionaries
        :rtype: List[Dict[str, Any]]
        """
        return await self._make_request("/records", params)

    @route("/calendar")
    async def _get_calendar(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get calendar/weeks for a given year.

        :param params: Query parameters including year (required)
        :type params: Dict[str, Any]
        :return: List of week dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If required parameters are missing
        """
        if "year" not in params:
            raise ValueError("year parameter is required for /calendar endpoint")

        return await self._make_request("/calendar", params)

    @route("/games/media")
    async def _get_game_media(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get game media information and types.

        :param params: Query parameters including year (required), week, seasonType, team, conference, mediaType, classification
        :type params: Dict[str, Any]
        :return: List of game media dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If required parameters are missing
        """
        if "year" not in params:
            raise ValueError("year parameter is required for /games/media endpoint")

        return await self._make_request("/games/media", params)

    @route("/games/weather")
    async def _get_game_weather(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get game weather information.

        :param params: Query parameters including gameId, year, week, seasonType, team, conference
        :type params: Dict[str, Any]
        :return: List of game weather dictionaries
        :rtype: List[Dict[str, Any]]
        """
        return await self._make_request("/games/weather", params)

    @route("/games/players")
    async def _get_player_game_stats(
        self, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get player statistics by game.

        :param params: Query parameters including year (required), week, seasonType, team, conference, category, gameId
        :type params: Dict[str, Any]
        :return: List of player game statistics dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If required parameters are missing
        """
        if "year" not in params:
            raise ValueError("year parameter is required for /games/players endpoint")

        return await self._make_request("/games/players", params)

    @route("/games/teams")
    async def _get_team_game_stats(
        self, params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get team statistics by game.

        :param params: Query parameters including year (required), week, seasonType, team, conference, gameId, classification
        :type params: Dict[str, Any]
        :return: List of team game statistics dictionaries
        :rtype: List[Dict[str, Any]]
        :raises ValueError: If required parameters are missing
        """
        if "year" not in params:
            raise ValueError("year parameter is required for /games/teams endpoint")

        return await self._make_request("/games/teams", params)

    @route("/games/box/advanced")
    async def _get_box_scores(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get box score data for a specific game.

        :param params: Query parameters including gameId (required)
        :type params: Dict[str, Any]
        :return: Box score data dictionary
        :rtype: Dict[str, Any]
        :raises ValueError: If required parameters are missing
        """
        if "gameId" not in params:
            raise ValueError(
                "gameId parameter is required for /games/box/advanced endpoint"
            )

        return await self._make_request("/games/box/advanced", params)

    # Convenience methods that maintain the original interface
    async def get_games(
        self,
        year: int,
        week: Optional[int] = None,
        season_type: Optional[str] = None,
        team: Optional[str] = None,
        home: Optional[str] = None,
        away: Optional[str] = None,
        conference: Optional[str] = None,
        division: Optional[str] = None,
        id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get game information using typed parameters.

        :param year: Year filter (required)
        :type year: int
        :param week: Week filter
        :type week: Optional[int]
        :param season_type: Season type filter (regular, postseason, both)
        :type season_type: Optional[str]
        :param team: Team filter
        :type team: Optional[str]
        :param home: Home team filter
        :type home: Optional[str]
        :param away: Away team filter
        :type away: Optional[str]
        :param conference: Conference filter
        :type conference: Optional[str]
        :param division: Division filter (fbs, fcs, ii, iii)
        :type division: Optional[str]
        :param id: Game ID filter
        :type id: Optional[int]
        :return: List of game dictionaries
        :rtype: List[Dict[str, Any]]
        """
        params: Dict[str, Any] = {"year": year}

        if week is not None:
            params["week"] = week
        if season_type:
            params["seasonType"] = season_type
        if team:
            params["team"] = team
        if home:
            params["home"] = home
        if away:
            params["away"] = away
        if conference:
            params["conference"] = conference
        if division:
            params["division"] = division
        if id is not None:
            params["id"] = id

        return await self.make_request("/games", params)
