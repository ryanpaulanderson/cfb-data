"""Tests for raw game API layer."""

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
from cfb_data.game.api.game_api import CFBDGamesAPI


class DummyAPI(CFBDGamesAPI):
    """Subclass to expose protected methods for testing without real HTTP."""

    def __init__(self):
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_get_games_requires_year():
    """Verify missing year parameter raises ``ValueError``."""
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_games({}))


def test_get_games_calls_make_request():
    """Ensure ``_make_request`` is invoked with params."""
    api = DummyAPI()
    api._make_request = AsyncMock(return_value=[{"id": 1}])
    params = {"year": 2024, "week": 1}
    result = run(api._get_games(params))
    api._make_request.assert_awaited_once_with("/games", params)
    assert result == [{"id": 1}]


def test_get_calendar_requires_year():
    """Validate year parameter enforcement on calendar."""
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_calendar({}))


def test_get_box_scores_requires_game_id():
    """Check that ``gameId`` is required for box score."""
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_box_scores({"game_id": 1}))


def test_route_map_contains_registered_paths():
    """Paths decorated with :func:`route` should be discoverable."""
    api = DummyAPI()
    assert "/games" in api._route_map
    assert "/game/box/advanced" in api._route_map
