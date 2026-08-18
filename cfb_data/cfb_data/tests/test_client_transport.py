"""Test lifecycle, authentication, retries, and safe transport errors."""

import asyncio
import builtins
import json
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import aiohttp
import pytest
from aiohttp import web
from pydantic import ValidationError

from cfb_data import (
    CFBDAuthenticationError,
    CFBDAuthorizationError,
    CFBDClient,
    CFBDClientStateError,
    CFBDConfigurationError,
    CFBDHTTPError,
    CFBDNoContentError,
    CFBDOptionalDependencyError,
    CFBDRateLimitError,
    CFBDRequestValidationError,
    CFBDResponseDecodeError,
    CFBDResponseValidationError,
    CFBDServerError,
    CFBDTimeoutError,
    CFBDTLSError,
    CFBDTransportError,
    RetryPolicy,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _assert_detached_transport_exception_chain(
    error: BaseException,
    *,
    category: str,
    sensitive_values: tuple[str, ...],
) -> None:
    """Assert that an authenticated transport cause retains no request state."""
    cause = error.__cause__
    assert cause is not None
    assert str(cause) == category
    assert error.__context__ is None
    assert cause.__cause__ is None
    assert cause.__context__ is None

    rendered = f"{error!r}\n{vars(error)!r}\n{cause!r}\n{vars(cause)!r}"
    for sensitive_value in sensitive_values:
        assert sensitive_value not in rendered


def test_explicit_credentials_precede_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CFBD_API_KEY", "environment-key")
    client = CFBDClient("explicit-key")

    assert client is not None


def test_none_uses_environment_and_empty_explicit_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CFBD_API_KEY", "environment-key")
    assert CFBDClient() is not None

    with pytest.raises(CFBDConfigurationError, match="Explicit api_key"):
        CFBDClient("")


def test_missing_or_empty_environment_credential_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CFBD_API_KEY", raising=False)
    with pytest.raises(CFBDConfigurationError, match="CFBD_API_KEY"):
        CFBDClient()

    monkeypatch.setenv("CFBD_API_KEY", "   ")
    with pytest.raises(CFBDConfigurationError, match="CFBD_API_KEY"):
        CFBDClient()


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_timeout_must_be_finite_and_positive(timeout: float) -> None:
    with pytest.raises(CFBDConfigurationError, match="timeout_seconds"):
        CFBDClient("key", timeout_seconds=timeout)


@pytest.mark.parametrize(
    "base_url",
    [
        "api.collegefootballdata.com",
        "ftp://api.example.test",
        "https://user:password@example.test",
        "https://example.test?secret=value",
    ],
)
def test_base_url_rejects_unsafe_forms(base_url: str) -> None:
    with pytest.raises(CFBDConfigurationError, match="base_url"):
        CFBDClient("key", base_url=base_url)


@pytest.mark.asyncio
async def test_client_requires_one_active_one_shot_context(
    api_server: ServerFactory,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        client = CFBDClient("key", base_url=base_url)
        with pytest.raises(CFBDClientStateError):
            await client.games.calendar(year=2024)

        async with client:
            first = await client.games.calendar(year=2024)
            second = await client.games.calendar(year=2024)
            assert first.empty and second.empty
            with pytest.raises(CFBDClientStateError):
                async with client:
                    pass

        with pytest.raises(CFBDClientStateError):
            await client.games.calendar(year=2024)
        with pytest.raises(CFBDClientStateError):
            async with client:
                pass


@pytest.mark.asyncio
async def test_one_session_reuses_a_connection_and_closes_it(
    api_server: ServerFactory,
) -> None:
    transports: set[int] = set()

    async def handler(request: web.Request) -> web.Response:
        assert request.transport is not None
        transports.add(id(request.transport))
        return web.json_response([])

    async with api_server(handler) as base_url:
        client = CFBDClient("key", base_url=base_url)
        async with client:
            session = client._transport._session
            assert session is not None and not session.closed
            await client.games.calendar(year=2024)
            await client.games.calendar(year=2025)
        assert session.closed

    assert len(transports) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_retryable_http_statuses_use_total_attempt_limit(
    api_server: ServerFactory,
    status: int,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return web.Response(status=status)
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
        ) as client:
            result = await client.games.calendar(year=2024)

    assert result.empty
    assert attempts == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_non_retryable_statuses_fail_once_with_specific_errors(
    api_server: ServerFactory,
    status: int,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        return web.Response(status=status, text="sensitive upstream payload")

    expected = {
        400: CFBDHTTPError,
        401: CFBDAuthenticationError,
        403: CFBDAuthorizationError,
        404: CFBDHTTPError,
    }[status]
    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(expected) as exc_info:
                await client.games.calendar(year=2024)

    assert attempts == 1
    assert exc_info.value.status == status
    assert "sensitive upstream payload" not in str(exc_info.value)
    assert "year" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_disabled_retry_policy_attempts_once(
    api_server: ServerFactory,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        return web.Response(status=503)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
        ) as client:
            with pytest.raises(CFBDServerError) as exc_info:
                await client.games.calendar(year=2024)

    assert attempts == 1
    assert exc_info.value.attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after_kind", ["numeric", "date"])
async def test_retry_after_numeric_and_http_date_are_honored(
    api_server: ServerFactory,
    monkeypatch: pytest.MonkeyPatch,
    retry_after_kind: str,
) -> None:
    attempts = 0
    delays: list[float] = []
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            retry_after = "2"
            if retry_after_kind == "date":
                retry_after = format_datetime(now + timedelta(seconds=2))
            return web.Response(status=429, headers={"Retry-After": retry_after})
        return web.json_response([])

    async with api_server(handler) as base_url:
        client = CFBDClient("key", base_url=base_url)
        client._transport._sleep = fake_sleep
        client._transport._utc_now = lambda: now
        async with client:
            await client.games.calendar(year=2024)

    assert attempts == 2
    assert len(delays) == 1
    assert delays == [2.0]


@pytest.mark.asyncio
async def test_retry_after_at_default_cap_is_honored(
    api_server: ServerFactory,
) -> None:
    attempts = 0
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return web.Response(status=429, headers={"Retry-After": "90"})
        return web.json_response([])

    async with api_server(handler) as base_url:
        client = CFBDClient("key", base_url=base_url)
        client._transport._sleep = fake_sleep
        async with client:
            await client.games.calendar(year=2024)

    assert attempts == 2
    assert delays == [90.0]


@pytest.mark.asyncio
async def test_retry_after_above_cap_fails_without_waiting(
    api_server: ServerFactory,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        return web.Response(status=429, headers={"Retry-After": "91"})

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDRateLimitError) as exc_info:
                await client.games.calendar(year=2024)

    assert attempts == 1
    assert exc_info.value.retry_after_seconds == 91


@pytest.mark.asyncio
async def test_full_jitter_stays_inside_exponential_caps(
    api_server: ServerFactory,
) -> None:
    attempts = 0
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return web.Response(status=503)
        return web.json_response([])

    async with api_server(handler) as base_url:
        client = CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0.5,
                max_backoff_seconds=0.75,
            ),
        )
        client._transport._sleep = fake_sleep
        client._transport._random_source = lambda: 1.0
        async with client:
            await client.games.calendar(year=2024)

    assert delays == [0.5, 0.75]


@pytest.mark.asyncio
async def test_retry_debug_events_contain_only_safe_metadata(
    api_server: ServerFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return web.Response(status=503, text="private-response-body")
        return web.json_response([])

    caplog.set_level(logging.DEBUG, logger="cfb_data._transport")
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "private-api-key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
        ) as client:
            await client.games.calendar(year=2024)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "endpoint=/calendar" in messages
    assert "category=http_503" in messages
    assert "attempt=1" in messages
    assert "private-api-key" not in messages
    assert "private-response-body" not in messages
    assert "year=2024" not in messages


@pytest.mark.asyncio
async def test_timeout_retries_then_raises_safe_timeout(
    api_server: ServerFactory,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.05)
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            timeout_seconds=0.005,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
        ) as client:
            with pytest.raises(CFBDTimeoutError) as exc_info:
                await client.games.calendar(year=2024)

    assert attempts == 2
    assert exc_info.value.attempts == 2


@pytest.mark.asyncio
async def test_connection_failure_is_retried_for_safe_get(
    api_server: ServerFactory,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.StreamResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            assert request.transport is not None
            request.transport.abort()
            return web.Response()
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
        ) as client:
            result = await client.games.calendar(year=2024)

    assert result.empty
    assert attempts == 2


@pytest.mark.asyncio
async def test_truncated_payload_is_retried_for_safe_get(
    api_server: ServerFactory,
) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.StreamResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            response = web.StreamResponse(
                headers={
                    "Content-Length": "100",
                    "Content-Type": "application/json",
                }
            )
            await response.prepare(request)
            await response.write(b"[]")
            assert request.transport is not None
            request.transport.abort()
            return response
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_backoff_seconds=0,
            ),
        ) as client:
            result = await client.games.calendar(year=2024)

    assert result.empty
    assert attempts == 2


@pytest.mark.asyncio
async def test_streamed_json_body_is_read_to_eof_before_decoding(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
) -> None:
    """Do not mistake the first available response chunk for a complete body."""
    payload = json.dumps([calendar_response]).encode()

    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        midpoint = len(payload) // 2
        await response.write(payload[:midpoint])
        await asyncio.sleep(0.05)
        await response.write(payload[midpoint:])
        await response.write_eof()
        return response

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            result = await client.games.calendar(year=2024)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_invalid_url_is_not_retried() -> None:
    async with CFBDClient("key", base_url="http://127.0.0.1:not-a-port") as client:
        with pytest.raises(CFBDTransportError) as exc_info:
            await client.games.calendar(year=2024)

    assert exc_info.value.attempts == 1
    assert exc_info.value.category == "invalid_url"


@pytest.mark.asyncio
async def test_invalid_json_is_not_retried(api_server: ServerFactory) -> None:
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        return web.Response(text="not json", content_type="application/json")

    async with api_server(handler) as base_url:
        async with CFBDClient("never-expose-api-key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseDecodeError) as exc_info:
                await client.games.calendar(year=2024)

    assert attempts == 1
    cause = exc_info.value.__cause__
    assert isinstance(cause, json.JSONDecodeError)
    assert cause.doc == "not json"
    assert "never-expose-api-key" not in repr(cause)


@pytest.mark.asyncio
async def test_undocumented_no_content_is_distinct_and_not_retried(
    api_server: ServerFactory,
) -> None:
    """Distinguish an empty 204 success from malformed response JSON."""
    attempts = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal attempts
        attempts += 1
        return web.Response(status=204)

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDNoContentError) as exc_info:
                await client.players.season_overview(year=2024, player_id=1)

    assert attempts == 1
    assert exc_info.value.attempts == 1
    assert exc_info.value.endpoint == "/player/season/overview"
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_content_type_error_chain_does_not_retain_api_key(
    api_server: ServerFactory,
) -> None:
    """Keep authenticated request metadata out of content-type failures."""

    async def handler(request: web.Request) -> web.Response:
        return web.Response(text="private-response-body", content_type="text/plain")

    async with api_server(handler) as base_url:
        async with CFBDClient("private-api-key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseDecodeError) as exc_info:
                await client.games.list(year=2024, team="private-team-filter")

    _assert_detached_transport_exception_chain(
        exc_info.value,
        category="ContentTypeError",
        sensitive_values=("private-api-key",),
    )


@pytest.mark.asyncio
async def test_validation_errors_preserve_diagnostics_without_api_key(
    api_server: ServerFactory,
) -> None:
    """Expose Pydantic field diagnostics without retaining authentication."""
    api_key = "never-expose-api-key"
    client = CFBDClient(api_key)
    with pytest.raises(CFBDRequestValidationError) as request_error:
        await client.games.calendar(year="diagnostic-year")

    request_cause = request_error.value.__cause__
    assert isinstance(request_cause, ValidationError)
    request_detail = request_cause.errors(include_url=False)[0]
    assert request_detail["loc"] == ("year",)
    assert request_detail["type"] == "int_parsing"
    assert request_detail["input"] == "diagnostic-year"
    assert "valid integer" in str(request_cause)
    assert "input_type=str" in str(request_cause)
    assert api_key not in repr(request_cause)

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([{"season": "diagnostic-season"}])

    async with api_server(handler) as base_url:
        async with CFBDClient(api_key, base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError) as response_error:
                await client.games.calendar(year=2024)

    response_cause = response_error.value.__cause__
    assert isinstance(response_cause, ValidationError)
    response_detail = response_cause.errors(include_url=False)[0]
    assert response_detail["loc"] == (0, "season")
    assert response_detail["type"] == "int_parsing"
    assert response_detail["input"] == "diagnostic-season"
    assert "valid integer" in str(response_cause)
    assert "input_type=str" in str(response_cause)
    assert api_key not in repr(response_cause)


@pytest.mark.asyncio
async def test_redirect_is_not_followed_or_retried(api_server: ServerFactory) -> None:
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        if request.path == "/calendar":
            raise web.HTTPFound("/credential-target")
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDHTTPError) as exc_info:
                await client.games.calendar(year=2024)

    assert exc_info.value.status == 302
    assert paths == ["/calendar"]


@pytest.mark.asyncio
async def test_tls_failure_and_cancellation_are_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CFBDClient("key")
    async with client:
        session = client._transport._session
        assert session is not None

        calls = 0

        def tls_get(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            raise aiohttp.ClientSSLError(None, OSError("certificate"))

        monkeypatch.setattr(session, "get", tls_get)
        with pytest.raises(CFBDTLSError):
            await client.games.calendar(year=2024)
        assert calls == 1

        def cancelled_get(*args: object, **kwargs: object) -> object:
            raise asyncio.CancelledError

        monkeypatch.setattr(session, "get", cancelled_get)
        with pytest.raises(asyncio.CancelledError):
            await client.games.calendar(year=2024)


def test_polars_dependency_error_contains_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
    calendar_response: dict[str, object],
) -> None:
    # Exercise the lazy boundary directly without unloading Polars from tests.
    from cfb_data import _dataframes

    real_builtin_import = builtins.__import__

    def fake_builtin_import(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[object, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "polars":
            raise ModuleNotFoundError("No module named 'polars'", name="polars")
        return real_builtin_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_builtin_import)
    from cfb_data.games.models.pydantic.responses import CalendarWeek

    row = CalendarWeek.model_validate(calendar_response)
    with pytest.raises(CFBDOptionalDependencyError, match=r"cfb-data\[polars\]"):
        _dataframes._PolarsAdapter().from_models(
            endpoint="/calendar", row_model=CalendarWeek, models=[row]
        )
