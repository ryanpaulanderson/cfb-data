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
from cfb_data.base.api.base_api import CFBDAPIBase, route


class DummyAPI(CFBDAPIBase):
    """Subclass for testing the base API client."""

    def __init__(self) -> None:
        super().__init__(api_key="fake")

    @route("/dummy")
    async def _dummy(self, params: dict) -> dict:
        return await self._make_request("/dummy", params)


def run(coro):
    """Helper to run async coroutines in tests without pytest-asyncio."""
    return asyncio.run(coro)


class DummyResponse:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def json(self):
        return self.data

    def raise_for_status(self):
        self.called = True


class DummySession:
    def __init__(self, response: DummyResponse) -> None:
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def get(self, url, headers=None, params=None):
        self.calls.append((url, headers, params))
        return self.response


def test_route_decorator_sets_api_path_attribute():
    @route("/test")
    async def handler(params: dict) -> dict:
        return {}

    assert getattr(handler, "_api_path") == "/test"


def test_discover_routes_finds_decorated_methods():
    api = DummyAPI()
    assert "/dummy" in api._route_map
    assert api._route_map["/dummy"].__name__ == "_dummy"


def test_make_request_routes_to_registered_handler():
    api = DummyAPI()
    mocked = AsyncMock(return_value={"ok": True})
    api._route_map["/dummy"] = mocked
    result = run(api.make_request("/dummy", {"a": 1}))
    mocked.assert_awaited_once_with({"a": 1})
    assert result == {"ok": True}


def test_make_request_calls_make_request_when_no_handler():
    api = DummyAPI()
    api._make_request = AsyncMock(return_value={"done": True})
    result = run(api.make_request("/other", {"x": 2}))
    api._make_request.assert_awaited_once_with("/other", {"x": 2})
    assert result == {"done": True}


def test_make_request_executes_http_call():
    api = DummyAPI()
    dummy_resp = DummyResponse({"data": 123})
    dummy_session = DummySession(dummy_resp)

    # Patch aiohttp.ClientSession within the module
    base_mod = sys.modules["cfb_data.base.api.base_api"]
    base_mod.aiohttp.ClientSession = lambda: dummy_session

    result = run(api._make_request("/path", {"k": "v"}))
    assert result == {"data": 123}
    assert dummy_resp.called
    assert dummy_session.calls == [(f"{api.base_url}/path", api.headers, {"k": "v"})]
