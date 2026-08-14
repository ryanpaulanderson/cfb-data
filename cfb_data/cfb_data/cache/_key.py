"""Build isolated versioned response-cache key digests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from cfb_data.base.types import QueryValue

_CACHE_KEY_VERSION = 1


def credential_scope_digest(api_key: str) -> str:
    """Return an irreversible account-scope discriminator for a bearer token."""
    material = b"cfb-data:credential-scope:v1\0" + api_key.encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def response_cache_key(
    *,
    base_url: str,
    endpoint: str,
    parameters: Mapping[str, QueryValue],
    response_contract: str,
    credential_scope: str,
) -> str:
    """Return a SHA-256 key without exposing request or credential values."""
    canonical = {
        "version": _CACHE_KEY_VERSION,
        "origin": _normalized_origin(base_url),
        "method": "GET",
        "endpoint": endpoint,
        "parameters": [
            [name, _typed_parameter(value)]
            for name, value in sorted(parameters.items())
        ],
        "representation": {"accept": "application/json"},
        "response_contract": response_contract,
        "credential_scope": credential_scope,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _typed_parameter(value: QueryValue) -> dict[str, str | int | float | bool]:
    """Preserve scalar JSON types when canonicalizing query parameters."""
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "str", "value": value}


def _normalized_origin(base_url: str) -> str:
    """Normalize scheme and host while preserving an API base path."""
    parsed = urlsplit(base_url)
    hostname = parsed.hostname or ""
    default_port = (parsed.scheme == "https" and parsed.port == 443) or (
        parsed.scheme == "http" and parsed.port == 80
    )
    host = hostname.lower()
    if parsed.port is not None and not default_port:
        host = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), host, path, "", ""))
