"""Model versioned cache records and backend coordination values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

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


class ResponsePeekStatus(StrEnum):
    """Classify one non-mutating response-cache inspection."""

    missing = "missing"
    retained = "retained"
    expired = "expired"
    corrupt = "corrupt"


@dataclass(frozen=True, slots=True)
class ResponsePeek:
    """Report cache disposition without mutating the stored response."""

    status: ResponsePeekStatus
    record: ResponseRecord | None = None
