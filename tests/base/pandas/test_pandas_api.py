"""Tests for the pandas validation layer."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock

import pandas as pd

sys.path.insert(0, "cfb_data")

if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    sys.modules["aiohttp"] = aiohttp_stub

import pandera as pa
import pytest
from cfb_data.base.api.base_api import route
from cfb_data.base.pandas import CFBDPandasAPI
from cfb_data.game.models.pandera.responses import CalendarWeekSchema
from cfb_data.game.models.pydantic.responses import CalendarWeek


class DummyPandasAPI(CFBDPandasAPI):
    """Expose pandas helper for testing."""

    def __init__(self) -> None:
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")

    @route(
        "/calendar",
        response_model=CalendarWeek,
        dataframe_schema=CalendarWeekSchema,
    )
    async def _calendar(self, params: dict) -> list[dict]:
        """Proxy to ``_make_request`` for testing.

        :param params: Query parameters passed to the endpoint.
        :type params: dict
        :return: Raw JSON list.
        :rtype: list[dict]
        """

        return await self._make_request("/calendar", params)


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_make_request_returns_dataframe():
    """Ensure DataFrame is returned for valid input."""

    api = DummyPandasAPI()
    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    api._make_request = AsyncMock(return_value=[sample])
    df = run(api.make_request("/calendar"))
    api._make_request.assert_awaited_once_with("/calendar", {})
    assert isinstance(df, pd.DataFrame)
    assert df.loc[0, "week"] == 1


def test_make_request_schema_error():
    """Ensure a schema error is raised for invalid data."""

    api = DummyPandasAPI()
    bad_sample = {
        "season": 2024,
        "week": -1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    api._make_request = AsyncMock(return_value=[bad_sample])
    with pytest.raises(pa.errors.SchemaError):
        run(api.make_request("/calendar"))
