import asyncio
from unittest.mock import AsyncMock
import sys
import types

sys.path.insert(0, "cfb_data")

# Provide a minimal aiohttp stub for import resolution
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    sys.modules["aiohttp"] = aiohttp_stub

import pytest

from cfb_data.game.api.game_api import CFBDGamesAPI


class DummyAPI(CFBDGamesAPI):
    """Subclass to expose protected methods for testing without real HTTP."""

    def __init__(self):
        super().__init__(api_key="fake")


def run(coro):
    """Helper to run async coroutines in tests without pytest-asyncio."""
    return asyncio.run(coro)


def test_get_games_requires_year():
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_games({}))


def test_get_games_calls_make_request():
    api = DummyAPI()
    api._make_request = AsyncMock(return_value=[{"id": 1}])
    params = {"year": 2024, "week": 1}
    result = run(api._get_games(params))
    api._make_request.assert_awaited_once_with("/games", params)
    assert result == [{"id": 1}]


def test_get_calendar_requires_year():
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_calendar({}))


def test_get_box_scores_requires_game_id():
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_box_scores({"id": 1}))


def test_typed_get_games_builds_params_and_calls_make_request():
    api = DummyAPI()
    api.make_request = AsyncMock(return_value=[{"id": 2}])
    result = run(
        api.get_games(
            year=2024,
            week=2,
            season_type="regular",
            team="A",
            home="B",
            away="C",
            conference="conf",
            division="fbs",
            id=10,
        )
    )
    expected_params = {
        "year": 2024,
        "week": 2,
        "seasonType": "regular",
        "team": "A",
        "home": "B",
        "away": "C",
        "conference": "conf",
        "division": "fbs",
        "id": 10,
    }
    api.make_request.assert_awaited_once_with("/games", expected_params)
    assert result == [{"id": 2}]


def test_route_map_contains_registered_paths():
    api = DummyAPI()
    assert "/games" in api._route_map
    assert "/games/box/advanced" in api._route_map
