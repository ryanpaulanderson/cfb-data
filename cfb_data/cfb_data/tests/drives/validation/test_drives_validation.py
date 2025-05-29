"""Tests for validation wrapper around drives API."""

import asyncio
import importlib
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Provide a minimal aiohttp stub for import resolution
importlib.import_module("sys").path.insert(0, str(Path(__file__).resolve().parents[4]))

if importlib.util.find_spec("aiohttp") is None:
    aiohttp_stub = types.ModuleType("aiohttp")
    importlib.import_module("sys").modules["aiohttp"] = aiohttp_stub

import pytest
from cfb_data.drives.validation import CFBDDrivesValidationAPI
from pydantic import ValidationError


class DummyDrivesValidationAPI(CFBDDrivesValidationAPI):
    """Expose protected validation methods for testing."""

    def __init__(self) -> None:
        """Initialize the dummy validation API with a fake key."""

        super().__init__(api_key="fake")


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_make_request_returns_models():
    """Return Pydantic models when data are valid."""
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
    with patch.object(CFBDDrivesValidationAPI, "_make_request", mocked):
        api = DummyDrivesValidationAPI()
        result = run(api.make_request("/drives", {"year": 2024}))
        mocked.assert_awaited_once_with("/drives", {"year": 2024})
        assert isinstance(result, list)
        assert result[0].game_id == 1


def test_make_request_raises_on_invalid():
    """Raise ``ValidationError`` when data are invalid."""
    bad_sample = {"game_id": 1}
    mocked = AsyncMock(return_value=[bad_sample])
    with patch.object(CFBDDrivesValidationAPI, "_make_request", mocked):
        api = DummyDrivesValidationAPI()
        with pytest.raises(ValidationError):
            run(api.make_request("/drives", {"year": 2024}))
        mocked.assert_awaited_once_with("/drives", {"year": 2024})
