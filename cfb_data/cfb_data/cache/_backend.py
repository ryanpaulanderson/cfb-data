"""Define narrow async protocols for response and catalog persistence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, Self

from cfb_data._catalog.models import CatalogCounts, CatalogProjection
from cfb_data.cache._models import ResponseRecord

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity


class BackendLifecycle(Protocol):
    """Own one backend's explicit resource lifecycle."""

    async def open(self) -> Self:
        """Open owned resources and return the backend."""
        ...

    async def close(self) -> None:
        """Close owned resources."""
        ...


class ResponseStore(Protocol):
    """Persist retained validated response records."""

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return one retained response or ``None`` after removing expiry."""
        ...

    async def delete_response(self, key: str) -> None:
        """Delete one invalid or expired response record."""
        ...

    async def cleanup_responses(self, now: datetime) -> int:
        """Delete expired response records and return the affected count."""
        ...


class CatalogWriter(Protocol):
    """Atomically persist a response with its canonical projection."""

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> None:
        """Store a response, catalog observations, and coverage atomically."""
        ...


class CoverageStore(Protocol):
    """Read and record capability-aware catalog coverage."""

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Return whether a complete partition freshly proves a capability."""
        ...

    async def record_coverage_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
        failed_at: datetime,
    ) -> None:
        """Record an interrupted or failed hydration partition."""
        ...


class LeaseStore(Protocol):
    """Coordinate cross-process refresh ownership."""

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Acquire a missing or expired refresh lease."""
        ...

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a lease while its owner token matches."""
        ...

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a lease while its owner token matches."""
        ...


class IdentityReader(Protocol):
    """Read domain-owned compact identities from canonical grains."""

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return exact provider-ID or name matches."""
        ...

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact provider-ID or name matches."""
        ...

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact provider-ID or name matches."""
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
        """Return exact athlete matches within optional scope."""
        ...


class CatalogInspector(Protocol):
    """Inspect backend-neutral canonical grain coverage for verification."""

    async def catalog_counts(self) -> CatalogCounts:
        """Return stored row counts for every canonical grain."""
        ...


class CacheBackend(
    BackendLifecycle,
    ResponseStore,
    CatalogWriter,
    CoverageStore,
    LeaseStore,
    IdentityReader,
    CatalogInspector,
    Protocol,
):
    """Combine narrow protocols for configured all-in-one backends."""
