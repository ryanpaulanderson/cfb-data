"""Test public cache configuration and canonical key isolation."""

from datetime import timedelta
from pathlib import Path

import pytest
from cfb_data.cache import (
    CachePolicyConfig,
    CacheProfile,
    CacheTTL,
    RedisCacheConfig,
    SQLiteCacheConfig,
)
from cfb_data.cache._key import credential_scope_digest, response_cache_key
from cfb_data.errors import CFBDConfigurationError


def test_cache_ttl_and_policy_are_validated_and_immutable() -> None:
    ttl = CacheTTL(timedelta(hours=1), timedelta(days=1))
    source = {CacheProfile.weather: ttl}
    policy = CachePolicyConfig(source)
    source.clear()

    assert policy.ttl_overrides == {CacheProfile.weather: ttl}
    with pytest.raises(TypeError):
        policy.ttl_overrides[CacheProfile.betting] = ttl  # type: ignore[index]

    with pytest.raises(CFBDConfigurationError):
        CacheTTL(timedelta(days=2), timedelta(days=1))
    with pytest.raises(CFBDConfigurationError):
        CacheTTL(timedelta(seconds=-1), timedelta())
    with pytest.raises(CFBDConfigurationError):
        CachePolicyConfig({CacheProfile.operational: ttl})


def test_backend_configuration_rejects_unsafe_or_unbounded_values() -> None:
    assert SQLiteCacheConfig(path=Path("cache.sqlite3")).path == Path("cache.sqlite3")
    assert RedisCacheConfig(url="rediss://cache.example.test/0").key_prefix == (
        "cfb-data"
    )

    with pytest.raises(CFBDConfigurationError):
        RedisCacheConfig(url="https://cache.example.test")
    with pytest.raises(CFBDConfigurationError):
        RedisCacheConfig(url="redis://cache.example.test", io_timeout_seconds=0)
    with pytest.raises(CFBDConfigurationError):
        SQLiteCacheConfig(io_timeout_seconds=float("inf"))


def test_redis_configuration_repr_redacts_credentials() -> None:
    """Keep hosted Redis passwords out of routine diagnostics."""
    password = "private-redis-password"
    config = RedisCacheConfig(url=f"rediss://cache-user:{password}@cache.test/0")

    assert password not in repr(config)
    assert config.url.endswith("@cache.test/0")


def test_cache_key_is_stable_typed_scoped_and_secret_free() -> None:
    token = "secret-bearer-value"
    scope = credential_scope_digest(token)
    common = {
        "base_url": "HTTPS://API.Example.Test:443/v1/",
        "endpoint": "/games",
        "response_contract": "Game:list:v1",
        "credential_scope": scope,
    }
    first = response_cache_key(parameters={"week": 0, "postseason": False}, **common)
    reordered = response_cache_key(
        parameters={"postseason": False, "week": 0}, **common
    )
    string_value = response_cache_key(
        parameters={"postseason": "false", "week": 0}, **common
    )

    assert first == reordered
    assert first != string_value
    assert token not in first
    assert len(first) == 64
