"""Own HTTP resources and retry policy for the public client."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import Enum, auto
from urllib.parse import urlsplit

import aiohttp

from cfb_data.base.types import QueryParameters
from cfb_data.cache._models import MAX_RESPONSE_BODY_BYTES
from cfb_data.errors import (
    CFBDAuthenticationError,
    CFBDAuthorizationError,
    CFBDClientStateError,
    CFBDConfigurationError,
    CFBDHTTPError,
    CFBDNoContentError,
    CFBDRateLimitError,
    CFBDResponseDecodeError,
    CFBDServerError,
    CFBDTimeoutError,
    CFBDTLSError,
    CFBDTransportError,
    _sanitized_cause,
    _SanitizedCause,
)
from cfb_data.retry import RetryPolicy

_LOGGER = logging.getLogger(__name__)
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class _TransportState(Enum):
    """Track the one-shot session lifecycle."""

    new = auto()
    active = auto()
    closed = auto()


@dataclass(frozen=True, slots=True)
class _RetryDecision:
    """Carry a retry outside the response context so its connection is released."""

    error: CFBDHTTPError
    delay_seconds: float
    category: str


@dataclass(frozen=True, slots=True)
class _TransportFailure:
    """Carry a safely detached transport failure outside its exception handler."""

    error: CFBDTransportError
    cause: _SanitizedCause
    category: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class _ResponseEnvelope:
    """Carry a bounded decoded body and safe response metadata."""

    body: object | None
    raw_body: bytes
    status: int
    content_type: str | None
    etag: str | None
    last_modified: str | None
    quota_headers: Mapping[str, str]


class _HTTPTransport:
    """Own one reusable :class:`aiohttp.ClientSession` and its connection pool."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        retry_policy: RetryPolicy,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize transport configuration without opening resources.

        :param api_key: Non-empty CFBD bearer token.
        :param base_url: Validated API origin and optional base path.
        :param timeout_seconds: Finite timeout applied to each attempt.
        :param retry_policy: Bounded GET retry configuration.
        :param sleep: Awaitable delay function used by retries.
        :param random_source: Uniform random source in the inclusive range 0..1.
        :param utc_now: Clock used to interpret HTTP-date ``Retry-After`` values.
        """
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._retry_policy = retry_policy
        self._sleep = sleep
        self._random_source = random_source
        self._utc_now = utc_now or (lambda: datetime.now(UTC))
        self._state = _TransportState.new
        self._session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        """Create the one session owned by this transport.

        :raises CFBDClientStateError: If the one-shot transport is not new.
        """
        if self._state is not _TransportState.new:
            raise CFBDClientStateError(
                "CFBDClient can be entered exactly once and cannot be nested"
            )

        try:
            session = aiohttp.ClientSession(
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                timeout=self._timeout,
                trust_env=False,
            )
        except Exception:
            self._state = _TransportState.closed
            raise

        self._session = session
        self._state = _TransportState.active

    async def close(self) -> None:
        """Close the owned session and permanently retire this transport.

        :raises CFBDClientStateError: If no active context owns a session.
        """
        if self._state is not _TransportState.active or self._session is None:
            raise CFBDClientStateError("CFBDClient has no active session to close")

        session = self._session
        self._session = None
        self._state = _TransportState.closed
        await session.close()

    async def get_json(
        self,
        endpoint: str,
        params: QueryParameters,
    ) -> object:
        """Return one decoded JSON response using bounded safe-GET retries.

        :param endpoint: Fixed endpoint path without query parameters.
        :param params: Validated scalar query parameters.
        :return: Value produced by the response JSON decoder.
        :raises CFBDClientStateError: If used outside its active context.
        :raises CFBDHTTPError: If the API returns an unsuccessful status.
        :raises CFBDTransportError: If transport attempts are exhausted.
        :raises CFBDResponseDecodeError: If a response is not valid JSON.
        """
        envelope = await self.get_response(endpoint, params)
        if envelope.body is None:
            raise AssertionError("ordinary JSON request unexpectedly returned no body")
        return envelope.body

    async def get_response(
        self,
        endpoint: str,
        params: QueryParameters,
        *,
        conditional_headers: Mapping[str, str] | None = None,
    ) -> _ResponseEnvelope:
        """Return one bounded response envelope using safe-GET retries.

        :param endpoint: Fixed endpoint path without query parameters.
        :param params: Validated scalar query parameters.
        :param conditional_headers: Safe validators for retained records.
        :return: Decoded response and cache-relevant metadata.
        :raises CFBDClientStateError: If used outside its active context.
        :raises CFBDHTTPError: If the API returns an unsuccessful status.
        :raises CFBDTransportError: If transport attempts are exhausted.
        :raises CFBDResponseDecodeError: If a response is invalid or oversized.
        """
        session = self._active_session()
        url = f"{self._base_url}{endpoint}"

        for attempt in range(1, self._retry_policy.max_attempts + 1):
            failure: _TransportFailure | None = None
            try:
                result = await self._request_once(
                    session=session,
                    url=url,
                    endpoint=endpoint,
                    params=params,
                    attempt=attempt,
                    conditional_headers=conditional_headers,
                )
            except asyncio.CancelledError:
                raise
            except aiohttp.InvalidURL as exc:
                failure = _TransportFailure(
                    error=CFBDTransportError(
                        endpoint=endpoint,
                        attempts=attempt,
                        category="invalid_url",
                    ),
                    cause=_sanitized_cause(exc),
                    category="invalid_url",
                    retryable=False,
                )
            except aiohttp.ClientSSLError as exc:
                failure = _TransportFailure(
                    error=CFBDTLSError(endpoint=endpoint, attempts=attempt),
                    cause=_sanitized_cause(exc),
                    category="tls",
                    retryable=False,
                )
            except TimeoutError as exc:
                failure = _TransportFailure(
                    error=CFBDTimeoutError(endpoint=endpoint, attempts=attempt),
                    cause=_sanitized_cause(exc),
                    category="timeout",
                    retryable=True,
                )
            except aiohttp.ClientPayloadError as exc:
                failure = _TransportFailure(
                    error=CFBDTransportError(
                        endpoint=endpoint,
                        attempts=attempt,
                        category="truncated_payload",
                    ),
                    cause=_sanitized_cause(exc),
                    category="truncated_payload",
                    retryable=True,
                )
            except aiohttp.ClientConnectionError as exc:
                failure = _TransportFailure(
                    error=CFBDTransportError(
                        endpoint=endpoint,
                        attempts=attempt,
                        category="connection",
                    ),
                    cause=_sanitized_cause(exc),
                    category="connection",
                    retryable=True,
                )
            except aiohttp.ClientError as exc:
                failure = _TransportFailure(
                    error=CFBDTransportError(
                        endpoint=endpoint,
                        attempts=attempt,
                        category="client",
                    ),
                    cause=_sanitized_cause(exc),
                    category="client",
                    retryable=False,
                )

            if failure is not None:
                if failure.retryable and attempt < self._retry_policy.max_attempts:
                    await self._retry_after_failure(
                        endpoint=endpoint,
                        attempt=attempt,
                        category=failure.category,
                    )
                    continue
                raise failure.error from failure.cause

            if not isinstance(result, _RetryDecision):
                return result

            _LOGGER.debug(
                "Retrying CFBD GET endpoint=%s category=%s attempt=%d delay=%.3f",
                endpoint,
                result.category,
                attempt,
                result.delay_seconds,
            )
            await self._sleep(result.delay_seconds)

        raise AssertionError("retry loop exhausted without returning or raising")

    async def _request_once(
        self,
        *,
        session: aiohttp.ClientSession,
        url: str,
        endpoint: str,
        params: QueryParameters,
        attempt: int,
        conditional_headers: Mapping[str, str] | None,
    ) -> _ResponseEnvelope | _RetryDecision:
        """Perform one attempt and release its response before any retry delay."""
        async with session.get(
            url,
            params={
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in params.items()
            },
            headers=conditional_headers,
            allow_redirects=False,
        ) as response:
            if response.status == 304 and conditional_headers:
                return _response_envelope(response, body=None, raw_body=b"")
            if response.status >= 300:
                retry_after = self._parse_retry_after(
                    response.headers.get("Retry-After")
                )
                error = _http_error(
                    endpoint=endpoint,
                    status=response.status,
                    attempts=attempt,
                    retry_after_seconds=retry_after,
                )
                if (
                    response.status in _RETRYABLE_STATUSES
                    and retry_after is not None
                    and retry_after > self._retry_policy.max_retry_after_seconds
                ):
                    raise error
                if (
                    response.status in _RETRYABLE_STATUSES
                    and attempt < self._retry_policy.max_attempts
                ):
                    delay = retry_after
                    if delay is None:
                        delay = self._backoff_delay(attempt)
                    return _RetryDecision(
                        error=error,
                        delay_seconds=delay,
                        category=f"http_{response.status}",
                    )
                raise error

            if response.status == 204:
                raise CFBDNoContentError(endpoint=endpoint, attempts=attempt)

            if (
                response.content_length is not None
                and response.content_length > MAX_RESPONSE_BODY_BYTES
            ):
                raise CFBDResponseDecodeError(endpoint=endpoint, attempts=attempt)
            raw_body = await _read_bounded_body(response, endpoint, attempt)
            if (
                response.content_length is not None
                and response.headers.get("Content-Encoding") is None
                and len(raw_body) != response.content_length
            ):
                raise aiohttp.ClientPayloadError("response body was truncated")
            try:
                if not _is_json_content_type(response.headers.get("Content-Type")):
                    raise aiohttp.ContentTypeError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message="unexpected content type",
                        headers=response.headers,
                    )
                decoded: object = json.loads(raw_body)
            except (
                aiohttp.ContentTypeError,
                json.JSONDecodeError,
                UnicodeDecodeError,
            ) as exc:
                safe_cause = _sanitized_cause(exc)
            else:
                return _response_envelope(response, body=decoded, raw_body=raw_body)
            raise CFBDResponseDecodeError(
                endpoint=endpoint,
                attempts=attempt,
            ) from safe_cause

    async def _retry_after_failure(
        self,
        *,
        endpoint: str,
        attempt: int,
        category: str,
    ) -> None:
        """Log and apply one client-selected full-jitter delay."""
        delay = self._backoff_delay(attempt)
        _LOGGER.debug(
            "Retrying CFBD GET endpoint=%s category=%s attempt=%d delay=%.3f",
            endpoint,
            category,
            attempt,
            delay,
        )
        await self._sleep(delay)

    def _backoff_delay(self, attempt: int) -> float:
        """Return capped exponential full-jitter backoff after an attempt."""
        backoff_multiplier: float = 2.0 ** (attempt - 1)
        ceiling: float = min(
            self._retry_policy.max_backoff_seconds,
            self._retry_policy.base_delay_seconds * backoff_multiplier,
        )
        random_fraction: float = self._random_source()
        if not 0 <= random_fraction <= 1:
            raise ValueError("random_source must return a value from 0 through 1")
        return random_fraction * ceiling

    def _parse_retry_after(self, value: str | None) -> float | None:
        """Parse a numeric or HTTP-date ``Retry-After`` value."""
        if value is None:
            return None

        numeric = True
        try:
            seconds = float(value)
        except ValueError:
            numeric = False
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None or retry_at.utcoffset() is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            seconds = max(
                0.0,
                (retry_at.astimezone(UTC) - self._utc_now()).total_seconds(),
            )

        if not math.isfinite(seconds) or (numeric and seconds < 0):
            return None
        return seconds

    def _active_session(self) -> aiohttp.ClientSession:
        """Return the active session or reject calls outside the context."""
        if self._state is not _TransportState.active or self._session is None:
            raise CFBDClientStateError(
                "Endpoint calls require an active 'async with CFBDClient(...)' context"
            )
        return self._session

    def ensure_active(self) -> None:
        """Reject endpoint work before any cache or catalog lookup."""
        self._active_session()

    @property
    def base_url(self) -> str:
        """Return the validated API origin and optional base path."""
        return self._base_url

    @property
    def follower_wait_seconds(self) -> float:
        """Return a bounded distributed-follower wait derived from retry policy."""
        attempts = self._retry_policy.max_attempts
        return (
            self._timeout_seconds * attempts
            + self._retry_policy.max_retry_after_seconds * max(attempts - 1, 0)
        )


def _resolve_api_key(api_key: str | None) -> str:
    """Resolve and validate explicit or environment authentication.

    :param api_key: Explicit key, or ``None`` to consult ``CFBD_API_KEY``.
    :return: Non-empty bearer token.
    :raises CFBDConfigurationError: If the selected credential is empty or absent.
    """
    if api_key is not None:
        if not api_key.strip():
            raise CFBDConfigurationError("Explicit api_key cannot be empty")
        return api_key

    environment_key = os.getenv("CFBD_API_KEY")
    if environment_key is None or not environment_key.strip():
        raise CFBDConfigurationError(
            "Provide api_key or set a non-empty CFBD_API_KEY environment variable"
        )
    return environment_key


def _validate_base_url(base_url: str) -> str:
    """Return a normalized HTTP(S) base URL without unsafe components.

    :param base_url: API origin and optional base path.
    :return: Base URL without trailing slashes.
    :raises CFBDConfigurationError: If the URL cannot safely identify an origin.
    """
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CFBDConfigurationError("base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise CFBDConfigurationError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise CFBDConfigurationError("base_url must not contain a query or fragment")
    return base_url.rstrip("/")


def _validate_timeout(timeout_seconds: float) -> float:
    """Return a finite positive per-attempt timeout.

    :param timeout_seconds: Configured timeout in seconds.
    :return: Validated timeout.
    :raises CFBDConfigurationError: If the timeout is not finite and positive.
    """
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise CFBDConfigurationError("timeout_seconds must be finite and positive")
    return timeout_seconds


def _http_error(
    *,
    endpoint: str,
    status: int,
    attempts: int,
    retry_after_seconds: float | None,
) -> CFBDHTTPError:
    """Create the most specific safe HTTP exception for a response status."""
    error_type: type[CFBDHTTPError]
    if status == 401:
        error_type = CFBDAuthenticationError
    elif status == 403:
        error_type = CFBDAuthorizationError
    elif status == 429:
        error_type = CFBDRateLimitError
    elif status >= 500:
        error_type = CFBDServerError
    else:
        error_type = CFBDHTTPError
    return error_type(
        endpoint=endpoint,
        status=status,
        attempts=attempts,
        retry_after_seconds=retry_after_seconds,
    )


def _is_json_content_type(value: str | None) -> bool:
    """Return whether a Content-Type identifies JSON."""
    if value is None:
        return False
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _response_envelope(
    response: aiohttp.ClientResponse,
    *,
    body: object | None,
    raw_body: bytes,
) -> _ResponseEnvelope:
    """Detach bounded cache-safe metadata from an aiohttp response."""
    quota_headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower().startswith("x-ratelimit-")
        or name.lower().startswith("x-quota-")
    }
    return _ResponseEnvelope(
        body=body,
        raw_body=raw_body,
        status=response.status,
        content_type=response.headers.get("Content-Type"),
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        quota_headers=quota_headers,
    )


async def _read_bounded_body(
    response: aiohttp.ClientResponse, endpoint: str, attempt: int
) -> bytes:
    """Read a complete streamed body without exceeding the response limit."""
    body = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BODY_BYTES:
            raise CFBDResponseDecodeError(endpoint=endpoint, attempts=attempt)
    return bytes(body)
