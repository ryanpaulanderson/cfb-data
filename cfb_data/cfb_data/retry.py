"""Configure retry behavior for safe CFBD GET requests."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configure bounded retries and backoff.

    ``max_attempts`` counts the initial request. Set it to ``1`` to disable
    retries.

    :param max_attempts: Maximum total attempts for one endpoint call.
    :param base_delay_seconds: Initial exponential-backoff ceiling.
    :param max_backoff_seconds: Maximum client-selected backoff ceiling.
    :param max_retry_after_seconds: Largest server delay the client will honor.
    :raises ValueError: If an option is outside its valid range.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    max_retry_after_seconds: float = 90.0

    def __post_init__(self) -> None:
        """Validate retry-policy invariants."""
        if isinstance(self.max_attempts, bool) or not isinstance(
            self.max_attempts, int
        ):
            raise ValueError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not math.isfinite(self.base_delay_seconds) or self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be finite and non-negative")
        if not math.isfinite(self.max_backoff_seconds):
            raise ValueError("max_backoff_seconds must be finite")
        if self.max_backoff_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_backoff_seconds cannot be less than base_delay_seconds"
            )
        if (
            not math.isfinite(self.max_retry_after_seconds)
            or self.max_retry_after_seconds < 0
        ):
            raise ValueError("max_retry_after_seconds must be finite and non-negative")


__all__ = ["RetryPolicy"]
