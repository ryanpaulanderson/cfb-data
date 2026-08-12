"""Define safe, actionable exceptions raised by :mod:`cfb_data`."""

from __future__ import annotations


class CFBDError(Exception):
    """Provide the root exception for all library-owned failures."""


class CFBDConfigurationError(CFBDError):
    """Report invalid or missing client configuration."""


class CFBDOptionalDependencyError(CFBDError, ImportError):
    """Report that a selected optional feature is not installed."""


class CFBDClientStateError(CFBDError, RuntimeError):
    """Report an operation that violates the one-shot client lifecycle."""


class _EndpointError(CFBDError):
    """Attach a safe endpoint identifier to an operation failure."""

    endpoint: str

    def __init__(self, message: str, *, endpoint: str) -> None:
        """Initialize an endpoint-scoped error.

        :param message: Safe human-readable failure description.
        :param endpoint: Fixed endpoint path without query parameters.
        """
        self.endpoint = endpoint
        super().__init__(f"{message} for endpoint {endpoint}")


class CFBDRequestValidationError(_EndpointError):
    """Report invalid endpoint request parameters."""

    def __init__(self, *, endpoint: str) -> None:
        """Initialize a request-validation error.

        :param endpoint: Fixed endpoint path without query parameters.
        """
        super().__init__("Request validation failed", endpoint=endpoint)


class CFBDTransportError(_EndpointError):
    """Report a non-timeout failure while communicating with the API."""

    attempts: int
    category: str

    def __init__(self, *, endpoint: str, attempts: int, category: str) -> None:
        """Initialize a transport error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param attempts: Total attempts made.
        :param category: Safe transport failure category.
        """
        self.attempts = attempts
        self.category = category
        super().__init__(
            f"Transport failed after {attempts} attempt(s) ({category})",
            endpoint=endpoint,
        )


class CFBDTimeoutError(CFBDTransportError, TimeoutError):
    """Report that every permitted request attempt timed out."""

    def __init__(self, *, endpoint: str, attempts: int) -> None:
        """Initialize a timeout error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param attempts: Total attempts made.
        """
        super().__init__(
            endpoint=endpoint,
            attempts=attempts,
            category="timeout",
        )


class CFBDTLSError(CFBDTransportError):
    """Report a non-retryable TLS or certificate failure."""

    def __init__(self, *, endpoint: str, attempts: int) -> None:
        """Initialize a TLS error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param attempts: Total attempts made.
        """
        super().__init__(endpoint=endpoint, attempts=attempts, category="tls")


class CFBDHTTPError(_EndpointError):
    """Report an unsuccessful HTTP response without exposing its body."""

    status: int
    attempts: int
    retry_after_seconds: float | None

    def __init__(
        self,
        *,
        endpoint: str,
        status: int,
        attempts: int,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Initialize an HTTP error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param status: HTTP response status.
        :param attempts: Total attempts made.
        :param retry_after_seconds: Parsed server-requested delay, if valid.
        """
        self.status = status
        self.attempts = attempts
        self.retry_after_seconds = retry_after_seconds
        retry_detail = ""
        if retry_after_seconds is not None:
            retry_detail = f", Retry-After={retry_after_seconds:g}s"
        super().__init__(
            f"HTTP {status} after {attempts} attempt(s){retry_detail}",
            endpoint=endpoint,
        )


class CFBDAuthenticationError(CFBDHTTPError):
    """Report rejected API authentication."""


class CFBDAuthorizationError(CFBDHTTPError):
    """Report insufficient authorization for an endpoint."""


class CFBDRateLimitError(CFBDHTTPError):
    """Report an API rate-limit response."""


class CFBDServerError(CFBDHTTPError):
    """Report an unsuccessful server response."""


class CFBDResponseDecodeError(_EndpointError):
    """Report a response body that cannot be decoded as JSON."""

    attempts: int

    def __init__(self, *, endpoint: str, attempts: int) -> None:
        """Initialize a response-decode error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param attempts: Total attempts made.
        """
        self.attempts = attempts
        super().__init__(
            f"Response JSON decoding failed after {attempts} attempt(s)",
            endpoint=endpoint,
        )


class CFBDResponseValidationError(_EndpointError):
    """Report a decoded response that violates its Pydantic contract."""

    def __init__(self, *, endpoint: str) -> None:
        """Initialize a response-validation error.

        :param endpoint: Fixed endpoint path without query parameters.
        """
        super().__init__("Response validation failed", endpoint=endpoint)


class CFBDDataFrameConversionError(_EndpointError):
    """Report failure to preserve validated rows in a selected DataFrame."""

    backend: str

    def __init__(self, *, endpoint: str, backend: str) -> None:
        """Initialize a DataFrame-conversion error.

        :param endpoint: Fixed endpoint path without query parameters.
        :param backend: Selected DataFrame backend name.
        """
        self.backend = backend
        super().__init__(
            f"{backend} DataFrame conversion failed",
            endpoint=endpoint,
        )


__all__ = [
    "CFBDAuthenticationError",
    "CFBDAuthorizationError",
    "CFBDClientStateError",
    "CFBDConfigurationError",
    "CFBDDataFrameConversionError",
    "CFBDError",
    "CFBDHTTPError",
    "CFBDOptionalDependencyError",
    "CFBDRateLimitError",
    "CFBDRequestValidationError",
    "CFBDResponseDecodeError",
    "CFBDResponseValidationError",
    "CFBDServerError",
    "CFBDTimeoutError",
    "CFBDTLSError",
    "CFBDTransportError",
]
