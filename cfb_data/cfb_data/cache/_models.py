"""Model versioned cache records and backend coordination values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_RESPONSE_BODY_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    """Store one exact validated response body and its safe metadata."""

    key: str
    endpoint: str
    response_contract: str
    body: bytes
    fetched_at: datetime
    fresh_until: datetime
    retained_until: datetime
    etag: str | None
    last_modified: str | None
    row_count: int
