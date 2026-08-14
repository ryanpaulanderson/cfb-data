"""Define immutable public cache configuration."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from cfb_data.errors import CFBDConfigurationError


class CacheMode(StrEnum):
    """Control response-cache behavior for one explicit operation scope."""

    default = "default"
    refresh = "refresh"
    bypass = "bypass"
    local_only = "local_only"


class CacheProfile(StrEnum):
    """Identify one built-in college-football data freshness profile."""

    stable_reference = "stable_reference"
    reference_vocabulary = "reference_vocabulary"
    roster = "roster"
    schedule = "schedule"
    active_season = "active_season"
    recruiting = "recruiting"
    historical = "historical"
    betting = "betting"
    weather = "weather"
    live_scoreboard = "live_scoreboard"
    live_plays = "live_plays"
    operational = "operational"


def _validate_duration(name: str, value: timedelta) -> None:
    """Reject negative or non-finite cache durations."""
    if not isinstance(value, timedelta):
        raise CFBDConfigurationError(f"{name} must be a datetime.timedelta")
    seconds = value.total_seconds()
    if not math.isfinite(seconds) or seconds < 0:
        raise CFBDConfigurationError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class CacheTTL:
    """Configure freshness and maximum retained-stale lifetimes.

    :param fresh_for: Duration during which a validated record avoids HTTP.
    :param retain_for: Maximum duration that the original body may be retained.
    :raises CFBDConfigurationError: If durations are invalid or out of order.
    """

    fresh_for: timedelta
    retain_for: timedelta

    def __post_init__(self) -> None:
        _validate_duration("fresh_for", self.fresh_for)
        _validate_duration("retain_for", self.retain_for)
        if self.retain_for < self.fresh_for:
            raise CFBDConfigurationError(
                "retain_for must be greater than or equal to fresh_for"
            )


@dataclass(frozen=True, slots=True)
class CachePolicyConfig:
    """Override built-in TTLs by semantic cache profile.

    :param ttl_overrides: Immutable profile-to-TTL overrides.
    :param stale_if_error: Whether retryable exhausted requests may use retained data.
    """

    ttl_overrides: Mapping[CacheProfile, CacheTTL] = field(default_factory=dict)
    stale_if_error: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.stale_if_error, bool):
            raise CFBDConfigurationError("stale_if_error must be a boolean")
        copied: dict[CacheProfile, CacheTTL] = {}
        for profile, ttl in self.ttl_overrides.items():
            if not isinstance(profile, CacheProfile):
                raise CFBDConfigurationError(
                    "ttl_overrides keys must be CacheProfile members"
                )
            if not isinstance(ttl, CacheTTL):
                raise CFBDConfigurationError(
                    "ttl_overrides values must be CacheTTL instances"
                )
            if profile is CacheProfile.operational:
                raise CFBDConfigurationError(
                    "operational account responses cannot be made cacheable"
                )
            copied[profile] = ttl
        object.__setattr__(self, "ttl_overrides", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class SQLiteCacheConfig:
    """Select the local SQLite cache and identity-catalog backend.

    :param path: Explicit database path, or ``None`` for the user cache location.
    :param io_timeout_seconds: Finite timeout for an individual cache operation.
    :param busy_timeout: SQLite lock-wait limit.
    """

    path: Path | None = None
    io_timeout_seconds: float = 2.0
    busy_timeout: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if self.path is not None and not isinstance(self.path, Path):
            raise CFBDConfigurationError("SQLite cache path must be a pathlib.Path")
        _validate_positive_timeout("io_timeout_seconds", self.io_timeout_seconds)
        _validate_duration("busy_timeout", self.busy_timeout)
        if self.busy_timeout == timedelta(0):
            raise CFBDConfigurationError("busy_timeout must be positive")


@dataclass(frozen=True, slots=True)
class RedisCacheConfig:
    """Select a shared Redis cache and identity-catalog backend.

    :param url: Explicit ``redis://`` or ``rediss://`` connection location.
    :param io_timeout_seconds: Finite socket and cache-operation timeout.
    :param key_prefix: Non-secret deployment namespace for all owned keys.
    """

    url: str = field(repr=False)
    io_timeout_seconds: float = 2.0
    key_prefix: str = "cfb-data"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise CFBDConfigurationError(
                "Redis cache URL must use redis:// or rediss:// and name a host"
            )
        if parsed.fragment:
            raise CFBDConfigurationError("Redis cache URL must not contain a fragment")
        _validate_positive_timeout("io_timeout_seconds", self.io_timeout_seconds)
        if not self.key_prefix or any(char.isspace() for char in self.key_prefix):
            raise CFBDConfigurationError(
                "Redis key_prefix must be non-empty and contain no whitespace"
            )


type CacheConfig = SQLiteCacheConfig | RedisCacheConfig


def _validate_positive_timeout(name: str, value: float) -> None:
    """Reject non-positive or non-finite timeout values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CFBDConfigurationError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise CFBDConfigurationError(f"{name} must be finite and positive")


__all__ = [
    "CacheConfig",
    "CacheMode",
    "CachePolicyConfig",
    "CacheProfile",
    "CacheTTL",
    "RedisCacheConfig",
    "SQLiteCacheConfig",
]
