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

from cfb_data.game.pandas import CFBDGamesPandasAPI


class DummyGamesPandasAPI(CFBDGamesPandasAPI):
    """Expose pandas methods for testing."""

    def __init__(self) -> None:
        """Initialize the dummy games API with a fake key."""

        super().__init__(api_key="fake")


def run(coro):
    """Execute a coroutine for synchronous test code.

    :param coro: Coroutine to execute
    :type coro: Coroutine
    :return: Result of the coroutine
    :rtype: Any
    """

    return asyncio.run(coro)


def test_get_calendar_df_returns_dataframe():
    """Return DataFrame for valid calendar data."""

    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[sample])
    mocked._api_path = CFBDGamesPandasAPI._get_calendar._api_path
    with patch.object(CFBDGamesPandasAPI, "_get_calendar", mocked):
        api = DummyGamesPandasAPI()
        df = run(api.get_calendar_df({"year": 2024}))
        mocked.assert_awaited_once_with({"year": 2024})
        assert isinstance(df, pd.DataFrame)
        assert df.loc[0, "week"] == 1


def test_get_calendar_df_schema_error():
    """Raise schema error for invalid calendar data."""

    bad_sample = {
        "season": 2024,
        "week": -1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[bad_sample])
    mocked._api_path = CFBDGamesPandasAPI._get_calendar._api_path
    with patch.object(CFBDGamesPandasAPI, "_get_calendar", mocked):
        api = DummyGamesPandasAPI()
        with pytest.raises(pa.errors.SchemaError):
            run(api.get_calendar_df({"year": 2024}))
