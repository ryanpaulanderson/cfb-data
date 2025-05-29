import asyncio
import sys
import types
from unittest.mock import AsyncMock, patch

sys.path.insert(0, "cfb_data")

# Provide a minimal aiohttp stub for import resolution
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    sys.modules["aiohttp"] = aiohttp_stub

import pytest
from cfb_data.game.validation import CFBDGamesValidationAPI
from pydantic import ValidationError


class DummyGamesValidationAPI(CFBDGamesValidationAPI):
    """Expose protected validation methods for testing."""

    def __init__(self) -> None:
        super().__init__(api_key="fake")


def run(coro):
    """Execute a coroutine for synchronous test code."""

    return asyncio.run(coro)


def test_get_calendar_validated_returns_models():
    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    mocked = AsyncMock(return_value=[sample])
    mocked._api_path = CFBDGamesValidationAPI._get_calendar._api_path
    with patch.object(CFBDGamesValidationAPI, "_get_calendar", mocked):
        api = DummyGamesValidationAPI()
        result = run(api.get_calendar_validated({"year": 2024}))
        mocked.assert_awaited_once_with({"year": 2024})
        assert isinstance(result, list)
        assert result[0].week == 1


def test_get_calendar_validated_raises_on_invalid():
    mocked = AsyncMock(return_value=[{"season": 2024}])
    mocked._api_path = CFBDGamesValidationAPI._get_calendar._api_path
    with patch.object(CFBDGamesValidationAPI, "_get_calendar", mocked):
        api = DummyGamesValidationAPI()
        with pytest.raises(ValidationError):
            run(api.get_calendar_validated({"year": 2024}))
