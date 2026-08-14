"""Define small async protocols for cache and catalog persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Self

from cfb_data.cache._catalog import CatalogProjection
from cfb_data.cache._models import ResponseRecord
from cfb_data.identities.models import (
    AthleteIdentity,
    ConferenceIdentity,
    GameIdentity,
    TeamIdentity,
    VenueIdentity,
)


class CacheBackend(Protocol):
    """Define response, catalog, coverage, and lease operations."""

    async def open(self) -> Self:
        """Open owned backend resources and return the backend."""
        ...

    async def close(self) -> None:
        """Close owned backend resources."""
        ...

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return one retained response or ``None`` after removing expiry."""
        ...

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> None:
        """Atomically store a response, projected facts, and coverage."""
        ...

    async def delete_response(self, key: str) -> None:
        """Delete one invalid or expired response record."""
        ...

    async def cleanup_responses(self, now: datetime) -> int:
        """Delete expired response records and return the affected count."""
        ...

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Return whether a complete partition freshly proves one capability."""
        ...

    async def record_coverage_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
        failed_at: datetime,
    ) -> None:
        """Record an interrupted or failed canonical hydration partition."""
        ...

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Acquire a missing or expired refresh lease."""
        ...

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a lease only while its owner token still matches."""
        ...

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a lease only while its owner token still matches."""
        ...

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return exact normalized provider-ID or name matches."""
        ...

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact normalized provider-ID or name matches."""
        ...

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact normalized provider-ID or name matches."""
        ...

    async def find_game(self, game_id: int) -> GameIdentity | None:
        """Return one game identity by provider ID."""
        ...

    async def find_games(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return games matching an explicit identity partition."""
        ...

    async def find_athletes(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return exact normalized athlete matches within optional scope."""
        ...
