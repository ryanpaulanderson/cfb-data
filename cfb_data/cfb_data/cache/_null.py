"""Provide the explicit no-persistence backend implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from cfb_data.cache._catalog import CatalogProjection
from cfb_data.cache._models import ResponseRecord
from cfb_data.identities.models import (
    AthleteIdentity,
    ConferenceIdentity,
    GameIdentity,
    TeamIdentity,
    VenueIdentity,
)


class NullCacheBackend:
    """Implement every persistence operation without storing state."""

    async def open(self) -> Self:
        """Return this no-resource backend."""
        return self

    async def close(self) -> None:
        """Close no resources."""

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return no response record."""
        return None

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> None:
        """Discard a validated response and its projection."""

    async def delete_response(self, key: str) -> None:
        """Delete no response record."""

    async def cleanup_responses(self, now: datetime) -> int:
        """Report that no response records were removed."""
        return 0

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Report that no partition coverage is available."""
        return False

    async def record_coverage_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
        failed_at: datetime,
    ) -> None:
        """Discard hydration failure metadata."""

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Grant an in-memory no-op lease."""
        return True

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew an in-memory no-op lease."""
        return True

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release an in-memory no-op lease."""
        return True

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return no team identities."""
        return []

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return no conference identities."""
        return []

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return no venue identities."""
        return []

    async def find_game(self, game_id: int) -> GameIdentity | None:
        """Return no game identity."""
        return None

    async def find_games(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return no game identities."""
        return []

    async def find_athletes(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return no athlete identities."""
        return []
