"""Base asynchronous HTTP client for the College Football Data API."""

from __future__ import annotations

import ssl
from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiohttp
from aiohttp import TCPConnector
from pandera.pandas import DataFrameModel
from pydantic import BaseModel

from cfb_data.base.types import JSONResponse, QueryParameters, json_response

F = TypeVar("F", bound=Callable[..., object])
RouteHandler = Callable[[QueryParameters], Awaitable[object]]


def route(
    path: str,
    *,
    response_model: type[BaseModel] | None = None,
    dataframe_schema: type[DataFrameModel] | None = None,
) -> Callable[[F], F]:
    """Register ``func`` as the handler for ``path``.

    The optional ``response_model`` and ``dataframe_schema`` metadata are used
    by higher-level API classes to perform Pydantic and Pandera validation.

    :param path: API endpoint path.
    :type path: str
    :param response_model: Pydantic model for validating the response.
    :type response_model: Optional[Type[BaseModel]]
    :param dataframe_schema: Pandera schema for validating DataFrames.
    :type dataframe_schema: Optional[Type[DataFrameModel]]
    :return: Decorator that attaches metadata to the function.
    :rtype: Callable[[F], F]
    """

    def decorator(func: F) -> F:
        """Attach routing metadata to ``func``.

        :param func: Function to decorate.
        :type func: F
        :return: Decorated function with route metadata.
        :rtype: F
        """
        setattr(func, "_api_path", path)
        setattr(func, "response_model", response_model)
        setattr(func, "dataframe_schema", dataframe_schema)
        return func

    return decorator


class CFBDAPIBase:
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
        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        self._route_map: dict[str, RouteHandler] = self._discover_routes()

    def _discover_routes(self) -> dict[str, RouteHandler]:
        """
        Discover all methods decorated with @route in the class.

        :return: Dictionary mapping API paths to methods
        :rtype: Dict[str, Callable]
        """
        routes: dict[str, RouteHandler] = {}
        for name in dir(self):
            attr = getattr(self, name)
            path = getattr(attr, "_api_path", None)
            if callable(attr) and isinstance(path, str):
                routes[path] = attr
        return routes

    async def _make_request(
        self, endpoint: str, params: QueryParameters | None = None
    ) -> JSONResponse:
        """
        Make an async HTTP GET request to the API.

        :param endpoint: API endpoint path
        :type endpoint: str
        :param params: Optional query parameters
        :type params: Optional[Dict[str, Any]]
        :return: JSON response as dict or list
        :rtype: Union[Dict[str, Any], List[Dict[str, Any]]]
        """
        url: str = f"{self.base_url}{endpoint}"

        # TODO(#54): Remove this insecure SSL override while hardening the HTTP
        # transport. Certificate and hostname verification must be enabled by
        # default before the client is considered production-ready.
        sslctx = ssl.create_default_context()
        sslctx.check_hostname = False
        sslctx.verify_mode = ssl.CERT_NONE

        async with (
            aiohttp.ClientSession(connector=TCPConnector(ssl=sslctx)) as session,
            session.get(url, headers=self.headers, params=params) as resp,
        ):
            resp.raise_for_status()
            return json_response(await resp.json())

    async def make_request(
        self, path: str, params: QueryParameters | None = None
    ) -> object:
        """
        Make a request to the API using path routing.

        :param path: API path (e.g., "/games", "/games/teams")
        :type path: str
        :param params: Query parameters
        :type params: Optional[Dict[str, Any]]
        :return: API response
        :rtype: Union[Dict[str, Any], List[Dict[str, Any]]]
        """
        if path in self._route_map:
            return await self._route_map[path](params or {})
        return await self._make_request(path, params)
