import asyncio
import sys
import types
from unittest.mock import AsyncMock

sys.path.insert(0, "cfb_data")

# Provide a minimal aiohttp stub for import resolution
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    sys.modules["aiohttp"] = aiohttp_stub

import pytest
from pydantic import ValidationError

from cfb_data.base.validation import CFBDValidationAPI
from cfb_data.game.models.pydantic.responses import CalendarWeek


class DummyValidationAPI(CFBDValidationAPI):
    """Subclass to expose validation helpers for testing."""

    def __init__(self) -> None:
        super().__init__(api_key="fake")


def run(coro):
    """Execute a coroutine for synchronous test code."""

    return asyncio.run(coro)


def test_make_request_validated_returns_models():
    api = DummyValidationAPI()
    sample = {
        "season": 2024,
        "week": 1,
        "season_type": "regular",
        "first_game_start": "2024-08-01T00:00:00Z",
        "last_game_start": "2024-08-02T00:00:00Z",
    }
    api._make_request = AsyncMock(return_value=[sample])
    result = run(api.make_request_validated("/calendar", CalendarWeek))
    api._make_request.assert_awaited_once_with("/calendar", None)
    assert isinstance(result, list)
    assert result[0].season == 2024


def test_make_request_validated_raises_on_invalid():
    api = DummyValidationAPI()
    api._make_request = AsyncMock(return_value=[{"season": 2024}])
    with pytest.raises(ValidationError):
        run(api.make_request_validated("/calendar", CalendarWeek))
