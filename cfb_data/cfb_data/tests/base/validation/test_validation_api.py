"""Tests for Pydantic validation layer."""

import asyncio
import importlib
import types
from pathlib import Path
from unittest.mock import AsyncMock

# Provide a minimal aiohttp stub for import resolution
importlib.import_module("sys").path.insert(0, str(Path(__file__).resolve().parents[4]))

if importlib.util.find_spec("aiohttp") is None:
    aiohttp_stub = types.ModuleType("aiohttp")
    importlib.import_module("sys").modules["aiohttp"] = aiohttp_stub

import pytest
from cfb_data.base.api.base_api import route
from cfb_data.base.validation import CFBDValidationAPI
from cfb_data.game.models.pydantic.responses import CalendarWeek
from pydantic import ValidationError


class DummyValidationAPI(CFBDValidationAPI):
    """Subclass used to test validation behavior."""

    def __init__(self) -> None:
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")

    @route("/calendar", response_model=CalendarWeek)
    async def _calendar(self, params: dict) -> list[dict]:
        """Proxy ``_make_request`` for the calendar endpoint.

        :param params: Query parameters for the call.
        :type params: dict
        :return: Raw JSON list.
        :rtype: list[dict]
        """

        return await self._make_request("/calendar", params)


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to run.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_make_request_returns_models():
    """Validate that models are returned for valid input."""
    api = DummyValidationAPI()
    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "startDate": "2024-08-01T00:00:00Z",
        "endDate": "2024-08-07T23:59:59Z",
        "firstGameStart": "2024-08-01T00:00:00Z",
        "lastGameStart": "2024-08-02T00:00:00Z",
    }
    api._make_request = AsyncMock(return_value=[sample])
    result = run(api.make_request("/calendar"))
    api._make_request.assert_awaited_once_with("/calendar", {})
    assert isinstance(result, list)
    assert result[0].season == 2024


def test_make_request_raises_on_invalid():
    """Ensure a validation error is raised for bad data."""
    api = DummyValidationAPI()
    api._make_request = AsyncMock(return_value=[{"season": 2024}])
    with pytest.raises(ValidationError):
        run(api.make_request("/calendar"))
