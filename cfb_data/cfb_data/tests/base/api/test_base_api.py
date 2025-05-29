"""Tests for the base API layer."""

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
from cfb_data.base.api.base_api import CFBDAPIBase, route


class DummyAPI(CFBDAPIBase):
    """Subclass for testing the base API client."""

    def __init__(self) -> None:
        """Initialize the dummy API with a fake key."""

        super().__init__(api_key="fake")

    @route("/dummy")
    async def _dummy(self, params: dict) -> dict:
        """Proxy ``_make_request`` for the dummy path.

        :param params: Query parameters.
        :type params: dict
        :return: Raw JSON response.
        :rtype: dict
        """

        return await self._make_request("/dummy", params)


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """

    return asyncio.run(coro)


class DummyResponse:
    """Minimal async response object for testing."""

    def __init__(self, data: dict) -> None:
        """Create dummy response.

        :param data: Data to return from ``json``.
        :type data: dict
        """

        self.data = data
        self.called = False

    async def __aenter__(self):
        """Enter async context manager.

        :return: The response itself.
        :rtype: DummyResponse
        """

        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exit async context manager.

        :param exc_type: Exception type.
        :type exc_type: type | None
        :param exc: Exception instance.
        :type exc: BaseException | None
        :param tb: Traceback.
        :type tb: TracebackType | None
        """

        pass

    async def json(self):
        """Return stored JSON data.

        :return: JSON payload.
        :rtype: dict
        """

        return self.data

    def raise_for_status(self):
        """Record that status was checked."""

        self.called = True


class DummySession:
    """Minimal async session for testing HTTP calls."""

    def __init__(self, response: DummyResponse) -> None:
        """Create dummy session wrapper.

        :param response: Response object to return.
        :type response: DummyResponse
        """

        self.response = response
        self.calls = []

    async def __aenter__(self):
        """Enter async context manager.

        :return: The session itself.
        :rtype: DummySession
        """

        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exit async context manager.

        :param exc_type: Exception type.
        :type exc_type: type | None
        :param exc: Exception instance.
        :type exc: BaseException | None
        :param tb: Traceback.
        :type tb: TracebackType | None
        """

        pass

    def get(self, url, headers=None, params=None):
        """Record call arguments and return preset response.

        :param url: Request URL.
        :type url: str
        :param headers: Request headers.
        :type headers: dict | None
        :param params: Query parameters.
        :type params: dict | None
        :return: Dummy response context.
        :rtype: DummyResponse
        """

        self.calls.append((url, headers, params))
        return self.response


def test_route_decorator_sets_api_path_attribute():
    """Ensure the ``route`` decorator attaches the path."""

    @route("/test")
    async def handler(params: dict) -> dict:
        """Dummy handler for decorator testing.

        :param params: Query parameters.
        :type params: dict
        :return: Empty JSON object.
        :rtype: dict
        """

        return {}

    assert getattr(handler, "_api_path") == "/test"


def test_discover_routes_finds_decorated_methods():
    """Verify decorated methods are discovered in ``_route_map``."""
    api = DummyAPI()
    assert "/dummy" in api._route_map
    assert api._route_map["/dummy"].__name__ == "_dummy"


def test_make_request_routes_to_registered_handler():
    """Calls routed handler when path is registered."""
    api = DummyAPI()
    mocked = AsyncMock(return_value={"ok": True})
    api._route_map["/dummy"] = mocked
    result = run(api.make_request("/dummy", {"a": 1}))
    mocked.assert_awaited_once_with({"a": 1})
    assert result == {"ok": True}


def test_make_request_calls_make_request_when_no_handler():
    """Fall back to HTTP request when no handler is registered."""
    api = DummyAPI()
    api._make_request = AsyncMock(return_value={"done": True})
    result = run(api.make_request("/other", {"x": 2}))
    api._make_request.assert_awaited_once_with("/other", {"x": 2})
    assert result == {"done": True}


def test_make_request_executes_http_call():
    """Execute HTTP call and return JSON data."""
    api = DummyAPI()
    dummy_resp = DummyResponse({"data": 123})
    dummy_session = DummySession(dummy_resp)

    # Patch aiohttp.ClientSession within the module
    base_mod = importlib.import_module("cfb_data.base.api.base_api")
    base_mod.aiohttp.ClientSession = lambda: dummy_session

    result = run(api._make_request("/path", {"k": "v"}))
    assert result == {"data": 123}
    assert dummy_resp.called
    assert dummy_session.calls == [(f"{api.base_url}/path", api.headers, {"k": "v"})]
