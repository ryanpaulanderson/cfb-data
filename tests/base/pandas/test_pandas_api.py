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
from cfb_data.base.pandas import CFBDPanderaAPI
from cfb_data.game.models.pandera.responses import CalendarWeekSchema
from cfb_data.game.models.pydantic.responses import CalendarWeek


class DummyPandasAPI(CFBDPanderaAPI):
    """Expose pandas helper for testing."""

    def __init__(self) -> None:
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")


def run(coro):
    """Execute a coroutine for synchronous test code.

    :param coro: Coroutine to execute
    :type coro: Coroutine
    :return: Result of the coroutine
    :rtype: Any
    """

    return asyncio.run(coro)


def test_make_request_pandas_returns_dataframe():
    """Ensure DataFrame is returned for valid input."""

    api = DummyPandasAPI()
    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    model = CalendarWeek.model_validate(sample)
    api.make_request_validated = AsyncMock(return_value=[model])
    df = run(api.make_request_pandas("/calendar", CalendarWeek, CalendarWeekSchema))
    api.make_request_validated.assert_awaited_once_with("/calendar", CalendarWeek, None)
    assert isinstance(df, pd.DataFrame)
    assert df.loc[0, "week"] == 1


def test_make_request_pandas_raises_on_schema_error():
    """Ensure a schema error is raised for invalid data."""

    api = DummyPandasAPI()
    bad_sample = {
        "season": 2024,
        "week": -1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    model = CalendarWeek.model_validate(bad_sample)
    api.make_request_validated = AsyncMock(return_value=[model])
    with pytest.raises(pa.errors.SchemaError):
        run(api.make_request_pandas("/calendar", CalendarWeek, CalendarWeekSchema))
