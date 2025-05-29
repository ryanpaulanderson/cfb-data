"""Tests for the games pandas API layer."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, patch

import pandas as pd
import pandera as pa
import pytest

sys.path.insert(0, "cfb_data")

if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    sys.modules["aiohttp"] = aiohttp_stub

from cfb_data.base.api.base_api import route
from cfb_data.game.models.pandera.responses import CalendarWeekSchema
from cfb_data.game.models.pydantic.responses import CalendarWeek
from cfb_data.game.pandas import CFBDGamesPandasAPI


class DummyGamesPandasAPI(CFBDGamesPandasAPI):
    """Expose pandas methods for testing."""

    def __init__(self) -> None:
        """Initialize the dummy games API with a fake key."""

        super().__init__(api_key="fake")

    @route(
        "/calendar", response_model=CalendarWeek, dataframe_schema=CalendarWeekSchema
    )
    async def _get_calendar(self, params: dict) -> list[dict]:
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
    """Return DataFrame for valid calendar data."""

    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[sample])
    with patch.object(CFBDGamesPandasAPI, "_make_request", mocked):
        api = DummyGamesPandasAPI()
        df = run(api.make_request("/calendar", {"year": 2024}))
        mocked.assert_awaited_once_with("/calendar", {"year": 2024})
        assert isinstance(df, pd.DataFrame)
        assert df.loc[0, "week"] == 1


def test_make_request_schema_error():
    """Raise schema error for invalid calendar data."""

    bad_sample = {
        "season": 2024,
        "week": -1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[bad_sample])
    with patch.object(CFBDGamesPandasAPI, "_make_request", mocked):
        api = DummyGamesPandasAPI()
        with pytest.raises(pa.errors.SchemaError):
            run(api.make_request("/calendar", {"year": 2024}))
