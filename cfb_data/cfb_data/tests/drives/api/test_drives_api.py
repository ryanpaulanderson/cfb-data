"""Tests for the drives API layer."""

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
from cfb_data.drives.api.drives_api import CFBDDrivesAPI


class DummyAPI(CFBDDrivesAPI):
    """Subclass exposing protected methods for testing."""

    def __init__(self) -> None:
        """Initialize with a fake API key."""

        super().__init__(api_key="fake")


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


def test_get_drives_requires_year():
    """Ensure year parameter is enforced."""
    api = DummyAPI()
    with pytest.raises(ValueError):
        run(api._get_drives({}))


def test_get_drives_calls_make_request():
    """Verify ``_make_request`` invocation for drives."""
    api = DummyAPI()
    api._make_request = AsyncMock(return_value=[{"id": "1"}])
    params = {"year": 2024}
    result = run(api._get_drives(params))
    api._make_request.assert_awaited_once_with("/drives", params)
    assert result == [{"id": "1"}]


def test_route_map_contains_registered_path():
    """Path decorated with :func:`route` should be registered."""
    api = DummyAPI()
    assert "/drives" in api._route_map
