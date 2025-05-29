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


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


def route(path: str) -> Callable[[F], F]:
    """
    Decorator to register a method as a handler for an API path.

    :param path: API endpoint path
    :type path: str
    :return: Decorator function
    :rtype: Callable[[F], F]
    """

    def decorator(func: F) -> F:
        func._api_path = path  # type: ignore
        return func

    return decorator


class CFBDAPIBase(ABC):
    """Base class for College Football Data API clients."""

    def __init__(
        self, api_key: str, base_url: str = "https://apinext.collegefootballdata.com"
    ) -> None:
        """
        Initialize the CFBD API base client.

        :param api_key: Bearer token for API authentication
        :type api_key: str
        :param base_url: Base URL for the API
        :type base_url: str
        """
        self.api_key: str = api_key
        self.base_url: str = base_url
        self.headers: Dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        self._route_map: Dict[str, Callable] = self._discover_routes()

    def _discover_routes(self) -> Dict[str, Callable]:
        """
        Discover all methods decorated with @route in the class.

        :return: Dictionary mapping API paths to methods
        :rtype: Dict[str, Callable]
        """
        routes: Dict[str, Callable] = {}
        for name in dir(self):
            attr = getattr(self, name)
            if callable(attr) and hasattr(attr, "_api_path"):
                routes[attr._api_path] = attr
        return routes

    async def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Make an async HTTP GET request to the API.

        :param endpoint: API endpoint path
        :type endpoint: str
        :param params: Optional query parameters
        :type params: Optional[Dict[str, Any]]
        :return: JSON response as dict or list
        :rtype: Union[Dict[str, Any], List[Dict[str, Any]]]
        :raises aiohttp.ClientError: On network errors
        :raises ValueError: On invalid JSON response
        """
        url: str = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self.headers, params=params
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def make_request(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Make a request to the API using path routing.

        :param path: API path (e.g., "/games", "/games/teams")
        :type path: str
        :param params: Query parameters
        :type params: Optional[Dict[str, Any]]
        :return: API response
        :rtype: Union[Dict[str, Any], List[Dict[str, Any]]]
        :raises ValueError: If path is not recognized
        """
        if path in self._route_map:
            return await self._route_map[path](params or {})
        else:
            # If no specific handler, make direct request
            return await self._make_request(path, params)
