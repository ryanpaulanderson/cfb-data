"""Tests for games API validation layer."""

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
from cfb_data.games.models.pydantic.responses import ScoreboardGame
from cfb_data.games.validation import CFBDGamesValidationAPI
from pydantic import ValidationError


class DummyGamesValidationAPI(CFBDGamesValidationAPI):
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
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "startDate": "2024-08-01T00:00:00Z",
        "endDate": "2024-08-07T23:59:59Z",
        "firstGameStart": "2024-08-01T00:00:00Z",
        "lastGameStart": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[sample])
    with patch.object(CFBDGamesValidationAPI, "_make_request", mocked):
        api = DummyGamesValidationAPI()
        result = run(api.make_request("/calendar", {"year": 2024}))
        mocked.assert_awaited_once_with("/calendar", {"year": 2024})
        assert isinstance(result, list)
        assert result[0].week == 1


def test_make_request_raises_on_invalid():
    """Raise ``ValidationError`` when data are invalid."""
    mocked = AsyncMock(return_value=[{"season": 2024}])
    with patch.object(CFBDGamesValidationAPI, "_make_request", mocked):
        api = DummyGamesValidationAPI()
        with pytest.raises(ValidationError):
            run(api.make_request("/calendar", {"year": 2024}))
        mocked.assert_awaited_once_with("/calendar", {"year": 2024})


def test_scoreboard_returns_validated_models(
    scoreboard_response: dict[str, object],
) -> None:
    """Validate scoreboard data through the domain client."""
    mocked = AsyncMock(return_value=[scoreboard_response])
    with patch.object(CFBDGamesValidationAPI, "_make_request", mocked):
        api = DummyGamesValidationAPI()
        result = run(api.make_request("/scoreboard"))

    mocked.assert_awaited_once_with("/scoreboard", {})
    assert isinstance(result, list)
    assert isinstance(result[0], ScoreboardGame)
    assert result[0].home_team.name == "Alabama"
