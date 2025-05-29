"""Tests for pandas-level drives API wrapper."""

import asyncio
import importlib
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pandera as pa
import pytest

importlib.import_module("sys").path.insert(0, str(Path(__file__).resolve().parents[4]))

if importlib.util.find_spec("aiohttp") is None:
    aiohttp_stub = types.ModuleType("aiohttp")
    importlib.import_module("sys").modules["aiohttp"] = aiohttp_stub

from cfb_data.base.api.base_api import route
from cfb_data.drives.models.pandera.responses import DriveSchema
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.drives.pandas import CFBDDrivesPandasAPI


class DummyDrivesPandasAPI(CFBDDrivesPandasAPI):
    """Expose pandas methods for testing."""

    def __init__(self) -> None:
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")

    @route("/drives", response_model=Drive, dataframe_schema=DriveSchema)
    async def _get_drives(self, params: dict) -> list[dict]:
        """Proxy to ``_make_request`` for testing.

        :param params: Query parameters passed to the endpoint.
        :type params: dict
        :return: Raw JSON list.
        :rtype: list[dict]
        """

        return await self._make_request("/drives", params)


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_make_request_returns_dataframe():
    """Return DataFrame for valid drive data."""
    sample = {
        "offense": "A",
        "offense_conference": None,
        "defense": "B",
        "defense_conference": None,
        "game_id": 1,
        "id": "d1",
        "drive_number": 1,
        "scoring": False,
        "start_period": 1,
        "start_yardline": 25,
        "start_yards_to_goal": 75,
        "start_time": {"seconds": 0, "minutes": 15},
        "end_period": 1,
        "end_yardline": 30,
        "end_yards_to_goal": 70,
        "end_time": {"seconds": 0, "minutes": 12},
        "plays": 3,
        "yards": 5,
        "drive_result": "Punt",
        "is_home_offense": True,
        "start_offense_score": 0,
        "start_defense_score": 0,
        "end_offense_score": 0,
        "end_defense_score": 0,
    }
    mocked = AsyncMock(return_value=[sample])
    with patch.object(CFBDDrivesPandasAPI, "_make_request", mocked):
        api = DummyDrivesPandasAPI()
        df = run(api.make_request("/drives", {"year": 2024}))
        mocked.assert_awaited_once_with("/drives", {"year": 2024})
        assert isinstance(df, pd.DataFrame)
        assert df.loc[0, "game_id"] == 1


def test_make_request_schema_error():
    """Raise schema error for invalid drive data."""
    bad_sample = {
        "offense": "A",
        "offense_conference": None,
        "defense": "B",
        "defense_conference": None,
        "game_id": 1,
        "id": "d1",
        "drive_number": 1,
        "scoring": False,
        "start_period": 1,
        "start_yardline": -1,
        "start_yards_to_goal": 101,
        "start_time": {"seconds": 0, "minutes": 15},
        "end_period": 1,
        "end_yardline": 30,
        "end_yards_to_goal": 70,
        "end_time": {"seconds": 0, "minutes": 12},
        "plays": 3,
        "yards": 5,
        "drive_result": "Punt",
        "is_home_offense": True,
        "start_offense_score": 0,
        "start_defense_score": 0,
        "end_offense_score": 0,
        "end_defense_score": 0,
    }
    mocked = AsyncMock(return_value=[bad_sample])
    with patch.object(CFBDDrivesPandasAPI, "_make_request", mocked):
        api = DummyDrivesPandasAPI()
        with pytest.raises(pa.errors.SchemaError):
            run(api.make_request("/drives", {"year": 2024}))
