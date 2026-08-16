"""Coordinate validated response caching, coalescing, and refresh leases."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Self, TypeVar, cast

from pydantic import BaseModel

from cfb_data._catalog.models import CatalogProjection
from cfb_data._observability import (
    _EventDispatcher,
    _failure_category,
    _OperationContext,
)
from cfb_data._transport import _HTTPTransport
from cfb_data.base.types import QueryParameters
from cfb_data.cache._backend import CacheBackend
from cfb_data.cache._catalog import project_catalog
from cfb_data.cache._key import response_cache_key
from cfb_data.cache._models import MAX_RESPONSE_BODY_BYTES, ResponseRecord
from cfb_data.cache._null import NullCacheBackend
from cfb_data.cache.config import CacheMode, CachePolicyConfig, CacheProfile
from cfb_data.cache.policy import cache_profile, resolve_ttl
from cfb_data.errors import (
    CFBDCacheBackendError,
    CFBDCacheMissError,
    CFBDHTTPError,
    CFBDTransportError,
)
from cfb_data.observability import (
    CacheBackendFailed,
    CacheLookupCompleted,
    CacheLookupOutcome,
    CacheLookupPhase,
    CacheWriteCompleted,
    CacheWriteOutcome,
    RefreshCoordinated,
    RefreshOutcome,
    RetrievalSource,
    StaleFallbackUsed,
)

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity

_LOGGER = logging.getLogger(__name__)
_MAX_CATALOG_COMMIT_TIMEOUT_SECONDS = 30.0
_OBSERVATIONS_PER_COMMIT_SECOND = 10_000
_LEASE_DURATION = timedelta(seconds=60)
_LEASE_RENEW_INTERVAL_SECONDS = 20.0
_ValueT = TypeVar("_ValueT")


@dataclass(slots=True)
class _FlightState:
    """Track one internal refresh task and its current public waiters."""

    task: asyncio.Task[object]
    waiters: int
    refresh_id: str | None
    leader_context: _OperationContext | None


@dataclass(frozen=True, slots=True)
class _CacheRead:
    """Carry one cache read while preserving backend failure from absence."""

    record: ResponseRecord | None
    answered: bool


class CacheModeScope:
    """Temporarily select cache behavior for endpoint calls in one task context."""

    def __init__(self, mode_variable: ContextVar[CacheMode], mode: CacheMode) -> None:
        """Bind the context-local mode variable and desired value."""
        self._mode_variable = mode_variable
        self._mode = mode
        self._token: Token[CacheMode] | None = None

    def __enter__(self) -> Self:
        """Apply the requested mode to the current context."""
        if self._token is not None:
            raise RuntimeError("CacheModeScope cannot be entered more than once")
        self._token = self._mode_variable.set(self._mode)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        """Restore the prior context-local cache mode."""
        if self._token is None:
            raise RuntimeError("CacheModeScope is not active")
        self._mode_variable.reset(self._token)
        self._token = None


class CacheCoordinator:
    """Own cache policy, process-local single-flight, and backend coordination."""

    def __init__(
        self,
        *,
        transport: _HTTPTransport,
        backend: CacheBackend,
        enabled: bool,
        credential_scope: str,
        policy: CachePolicyConfig,
        io_timeout_seconds: float,
        event_dispatcher: _EventDispatcher,
        utc_now: Callable[[], datetime] | None = None,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        """Initialize coordination without opening backend resources.

        :param transport: Owned HTTP transport used for cache refreshes.
        :param backend: Configured durable response-cache backend.
        :param enabled: Whether durable response caching is configured.
        :param credential_scope: Opaque credential partition for cache keys.
        :param policy: Freshness, retention, and refresh behavior.
        :param io_timeout_seconds: Maximum duration of one backend operation.
        :param event_dispatcher: Optional-observer event dispatcher.
        :param utc_now: Injectable UTC clock used to assess record age.
        :param random_source: Injectable jitter source for lease polling.
        """
        self._transport = transport
        self._backend = backend
        self._transient = NullCacheBackend()
        self._enabled = enabled
        self._credential_scope = credential_scope
        self._policy = policy
        self._io_timeout_seconds = io_timeout_seconds
        self._event_dispatcher = event_dispatcher
        self._utc_now = utc_now or (lambda: datetime.now(UTC))
        self._random_source = random_source
        self._mode: ContextVar[CacheMode] = ContextVar(
            "cfb_data_cache_mode", default=CacheMode.default
        )
        self._flights: dict[str, _FlightState] = {}
        self._flights_lock = asyncio.Lock()
        self._backend_available = False
        self._transient_available = False

    async def open(self) -> None:
        """Open the configured backend while preserving fail-open API behavior."""
        await self._transient.open()
        self._transient_available = True
        if not self._enabled:
            return
        try:
            async with asyncio.timeout(self._io_timeout_seconds):
                await self._backend.open()
            self._backend_available = True
        except Exception as exc:
            _LOGGER.warning(
                "CFBD cache backend unavailable category=%s", type(exc).__name__
            )
            self._emit_backend_failure("open", exc, context=None)

    async def close(self) -> None:
        """Close the configured backend if it opened successfully."""
        if self._backend_available:
            self._backend_available = False
            try:
                async with asyncio.timeout(self._io_timeout_seconds):
                    await self._backend.close()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOGGER.warning(
                    "CFBD cache backend failure operation=close category=%s",
                    type(exc).__name__,
                )
                self._emit_backend_failure("close", exc, context=None)
        if self._transient_available:
            self._transient_available = False
            await self._transient.close()

    def mode_scope(self, mode: CacheMode) -> CacheModeScope:
        """Return a task-local explicit cache-behavior context manager."""
        return CacheModeScope(self._mode, mode)

    @property
    def current_mode(self) -> CacheMode:
        """Return the current task-local cache mode for operation observation."""
        return self._mode.get()

    @property
    def identity_store_available(self) -> bool:
        """Return whether durable catalog persistence opened successfully."""
        return self._backend_available

    def ensure_active(self) -> None:
        """Reject identity and maintenance work outside the client context."""
        self._transport.ensure_active()

    def allows_identity_stale(self, error: Exception) -> bool:
        """Return whether policy permits retained catalog facts for a failure."""
        return self._policy.stale_if_error and _allows_stale(error)

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        strict: bool = False,
    ) -> bool:
        """Return whether the catalog freshly proves one partition capability."""
        self.ensure_active()
        if strict:
            return await self._identity_backend_call(
                "coverage_read",
                self._backend.has_fresh_coverage(
                    endpoint=endpoint,
                    canonical_filters=canonical_filters,
                    capability=capability,
                    now=self._utc_now(),
                ),
                default=False,
                strict=True,
            )
        answered, persistent = await self._catalog_call(
            "coverage_read",
            self._backend.has_fresh_coverage(
                endpoint=endpoint,
                canonical_filters=canonical_filters,
                capability=capability,
                now=self._utc_now(),
            ),
        )
        if answered:
            return bool(persistent)
        return await self._transient.has_fresh_coverage(
            endpoint=endpoint,
            canonical_filters=canonical_filters,
            capability=capability,
            now=self._utc_now(),
        )

    async def record_hydration_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
    ) -> None:
        """Record resumable hydration failure metadata when persistence permits."""
        self.ensure_active()
        await self._identity_backend_call(
            "coverage_failure_write",
            self._backend.record_coverage_failure(
                endpoint=endpoint,
                canonical_filters=canonical_filters,
                failure_category=failure_category,
                failed_at=self._utc_now(),
            ),
            default=None,
            strict=False,
        )

    async def find_teams(
        self, query: str | int, *, strict: bool = False
    ) -> list[TeamIdentity]:
        """Return exact team matches from the configured catalog.

        :param query: Provider ID or exact normalized team name.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact team identities.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "team_identity_read",
                self._backend.find_teams(query),
                default=[],
                strict=True,
            )
        return await self._identity_catalog_rows(
            "team_identity_read",
            self._backend.find_teams(query),
            self._transient.find_teams(query),
            key=lambda identity: identity.id,
        )

    async def find_conferences(
        self, query: str | int, *, strict: bool = False
    ) -> list[ConferenceIdentity]:
        """Return exact conference matches from the configured catalog.

        :param query: Provider ID or exact normalized conference name.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact conference identities.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "conference_identity_read",
                self._backend.find_conferences(query),
                default=[],
                strict=True,
            )
        return await self._identity_catalog_rows(
            "conference_identity_read",
            self._backend.find_conferences(query),
            self._transient.find_conferences(query),
            key=lambda identity: identity.id,
        )

    async def find_venues(
        self, query: str | int, *, strict: bool = False
    ) -> list[VenueIdentity]:
        """Return exact venue matches from the configured catalog.

        :param query: Provider ID or exact normalized venue name.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact venue identities.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "venue_identity_read",
                self._backend.find_venues(query),
                default=[],
                strict=True,
            )
        return await self._identity_catalog_rows(
            "venue_identity_read",
            self._backend.find_venues(query),
            self._transient.find_venues(query),
            key=lambda identity: identity.id,
        )

    async def find_game(
        self, game_id: int, *, strict: bool = False
    ) -> GameIdentity | None:
        """Return one game identity from the configured catalog.

        :param game_id: Exact provider game ID.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact game identity, or ``None`` when absent.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "game_identity_read",
                self._backend.find_game(game_id),
                default=None,
                strict=True,
            )
        answered, persistent = await self._catalog_call(
            "game_identity_read", self._backend.find_game(game_id)
        )
        transient = await self._transient.find_game(game_id)
        if transient is not None:
            return transient
        return persistent if answered else None

    async def find_games(
        self,
        *,
        season: int,
        week: int | None,
        team: str | None,
        strict: bool = False,
    ) -> list[GameIdentity]:
        """Return game identities from one explicit catalog partition.

        :param season: Four-digit season year.
        :param week: Optional season week.
        :param team: Optional exact normalized team name.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact game identities.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "game_identity_search",
                self._backend.find_games(season=season, week=week, team=team),
                default=[],
                strict=True,
            )
        return await self._identity_catalog_rows(
            "game_identity_search",
            self._backend.find_games(season=season, week=week, team=team),
            self._transient.find_games(season=season, week=week, team=team),
            key=lambda identity: identity.id,
        )

    async def find_athletes(
        self,
        *,
        name: str,
        team: str | None,
        season: int | None,
        strict: bool = False,
    ) -> list[AthleteIdentity]:
        """Return athlete identities from an exact scoped catalog query.

        :param name: Exact normalized athlete name.
        :param team: Optional exact normalized team name.
        :param season: Optional season year.
        :param strict: Raise when the durable catalog cannot answer instead of
            consulting the transient catalog.
        :return: Matching compact athlete identities.
        :raises CFBDCacheBackendError: If strict durable lookup fails.
        """
        self.ensure_active()
        if strict and self._enabled:
            return await self._identity_backend_call(
                "athlete_identity_read",
                self._backend.find_athletes(name=name, team=team, season=season),
                default=[],
                strict=True,
            )
        return await self._identity_catalog_rows(
            "athlete_identity_read",
            self._backend.find_athletes(name=name, team=team, season=season),
            self._transient.find_athletes(name=name, team=team, season=season),
            key=lambda identity: (identity.id, identity.team, identity.season),
        )

    async def _identity_catalog_rows[IdentityT, IdentityKeyT](
        self,
        operation: str,
        persistent_awaitable: Awaitable[list[IdentityT]],
        transient_awaitable: Awaitable[list[IdentityT]],
        *,
        key: Callable[[IdentityT], IdentityKeyT],
    ) -> list[IdentityT]:
        """Overlay current transient identities on durable catalog results."""
        answered, persistent = await self._catalog_call(operation, persistent_awaitable)
        transient = await transient_awaitable
        if not answered:
            return transient
        transient_by_key = {key(identity): identity for identity in transient}
        combined = [
            transient_by_key.pop(key(identity), identity)
            for identity in (persistent or [])
        ]
        combined.extend(transient_by_key.values())
        return combined

    async def cleanup_responses(self) -> int:
        """Remove expired response entries without deleting catalog facts."""
        self.ensure_active()
        return await self._identity_backend_call(
            "response_cleanup",
            self._backend.cleanup_responses(self._utc_now()),
            default=0,
            strict=True,
        )

    async def execute(
        self,
        *,
        endpoint: str,
        parameters: QueryParameters,
        response_contract: str,
        validate: Callable[[object], _ValueT],
        context: _OperationContext | None,
    ) -> _ValueT:
        """Return current validated output through cache policy and coordination."""
        self._transport.ensure_active()
        mode = self._mode.get()
        profile = cache_profile(endpoint)
        if mode is CacheMode.local_only and (
            not self._enabled or profile is CacheProfile.operational
        ):
            self._emit_lookup(
                context,
                profile=profile,
                phase=CacheLookupPhase.initial,
                outcome=(
                    CacheLookupOutcome.skipped_disabled
                    if not self._enabled
                    else CacheLookupOutcome.skipped_operational
                ),
            )
            raise CFBDCacheMissError(
                f"Endpoint {endpoint} is unavailable in local-only cache mode"
            )
        if not self._enabled or profile is CacheProfile.operational:
            event = "disabled" if not self._enabled else "operational_bypass"
            _LOGGER.debug("CFBD response cache %s endpoint=%s", event, endpoint)
            self._set_source(context, RetrievalSource.network)
            self._emit_lookup(
                context,
                profile=profile,
                phase=CacheLookupPhase.initial,
                outcome=(
                    CacheLookupOutcome.skipped_disabled
                    if not self._enabled
                    else CacheLookupOutcome.skipped_operational
                ),
            )
            return await self._network_only(
                endpoint,
                parameters,
                response_contract,
                profile,
                validate,
                project=not self._enabled,
                context=context,
            )
        if mode is CacheMode.bypass:
            _LOGGER.debug("CFBD response cache bypass endpoint=%s", endpoint)
            self._set_source(context, RetrievalSource.network)
            self._emit_lookup(
                context,
                profile=profile,
                phase=CacheLookupPhase.initial,
                outcome=CacheLookupOutcome.skipped_bypass,
            )
            return await self._network_only(
                endpoint,
                parameters,
                response_contract,
                profile,
                validate,
                project=False,
                context=context,
            )

        key = response_cache_key(
            base_url=self._transport.base_url,
            endpoint=endpoint,
            parameters=parameters,
            response_contract=response_contract,
            credential_scope=self._credential_scope,
        )
        now = self._utc_now()
        retained, cached = await self._lookup_record(
            key=key,
            now=now,
            response_contract=response_contract,
            validate=validate,
            context=context,
            profile=profile,
            phase=CacheLookupPhase.initial,
        )
        if (
            cached is not None
            and retained is not None
            and (
                mode is CacheMode.local_only
                or (mode is CacheMode.default and retained.fresh_until > now)
            )
        ):
            _LOGGER.debug("CFBD response cache hit endpoint=%s", endpoint)
            self._set_source(
                context,
                (
                    RetrievalSource.retained_cache
                    if mode is CacheMode.local_only and retained.fresh_until <= now
                    else RetrievalSource.fresh_cache
                ),
            )
            await self._reproject_record(
                endpoint=endpoint,
                parameters=parameters,
                record=retained,
                value=cached,
                context=context,
            )
            return cached
        if mode is CacheMode.local_only:
            raise CFBDCacheMissError(
                f"No retained validated cache record for endpoint {endpoint}"
            )
        event = "miss" if retained is None else "stale"
        _LOGGER.debug("CFBD response cache %s endpoint=%s", event, endpoint)
        return await self._single_flight(
            key=key,
            endpoint=endpoint,
            parameters=parameters,
            response_contract=response_contract,
            profile=profile,
            validate=validate,
            stale_record=retained,
            stale_value=cached,
            force_refresh=mode is CacheMode.refresh,
            context=context,
        )

    async def _single_flight(
        self,
        *,
        key: str,
        endpoint: str,
        parameters: QueryParameters,
        response_contract: str,
        profile: CacheProfile,
        validate: Callable[[object], _ValueT],
        stale_record: ResponseRecord | None,
        stale_value: _ValueT | None,
        force_refresh: bool,
        context: _OperationContext | None,
    ) -> _ValueT:
        """Share one shielded refresh task among process-local followers."""
        is_follower = False
        async with self._flights_lock:
            state = self._flights.get(key)
            if state is None:
                refresh_id = (
                    self._event_dispatcher.new_refresh_id()
                    if context is not None
                    else None
                )
                if context is not None:
                    context.refresh_id = refresh_id
                self._emit_refresh(
                    context, refresh_id, endpoint, RefreshOutcome.local_leader
                )
                task = asyncio.create_task(
                    self._distributed_refresh(
                        key=key,
                        endpoint=endpoint,
                        parameters=parameters,
                        response_contract=response_contract,
                        profile=profile,
                        validate=validate,
                        stale_record=stale_record,
                        stale_value=stale_value,
                        force_refresh=force_refresh,
                        context=context,
                        refresh_id=refresh_id,
                    )
                )
                stored_task = cast(asyncio.Task[object], task)
                stored_task.add_done_callback(_observe_flight_completion)
                state = _FlightState(
                    task=stored_task,
                    waiters=1,
                    refresh_id=refresh_id,
                    leader_context=context,
                )
                self._flights[key] = state
            else:
                is_follower = True
                state.waiters += 1
                task = cast(asyncio.Task[_ValueT], state.task)
                if context is not None:
                    context.refresh_id = state.refresh_id
                self._emit_refresh(
                    context,
                    state.refresh_id,
                    endpoint,
                    RefreshOutcome.local_follower,
                )
                _LOGGER.debug("CFBD cache local follower endpoint=%s", endpoint)
        try:
            value = await asyncio.shield(task)
            if is_follower and context is not None and state.leader_context is not None:
                context.source = state.leader_context.source
            return value
        finally:
            await self._release_flight_waiter(key, state)

    async def _release_flight_waiter(self, key: str, state: _FlightState) -> None:
        """Remove a waiter and cancel a refresh that no caller still needs."""
        async with self._flights_lock:
            if self._flights.get(key) is not state:
                return
            state.waiters -= 1
            if state.waiters < 0:
                raise AssertionError("Cache flight waiter count became negative")
            if state.waiters == 0:
                del self._flights[key]
                if not state.task.done():
                    state.task.cancel()

    async def _distributed_refresh(
        self,
        *,
        key: str,
        endpoint: str,
        parameters: QueryParameters,
        response_contract: str,
        profile: CacheProfile,
        validate: Callable[[object], _ValueT],
        stale_record: ResponseRecord | None,
        stale_value: _ValueT | None,
        force_refresh: bool,
        context: _OperationContext | None,
        refresh_id: str | None,
    ) -> _ValueT:
        """Acquire a renewable backend lease before quota-consuming refresh."""
        now = self._utc_now()
        rechecked, rechecked_value = await self._lookup_record(
            key=key,
            now=now,
            response_contract=response_contract,
            validate=validate,
            context=context,
            profile=profile,
            phase=CacheLookupPhase.leader_recheck,
        )
        refresh_baseline = rechecked
        if (
            not force_refresh
            and rechecked is not None
            and rechecked_value is not None
            and rechecked.fresh_until > now
        ):
            await self._reproject_record(
                endpoint=endpoint,
                parameters=parameters,
                record=rechecked,
                value=rechecked_value,
                context=context,
            )
            self._set_source(context, RetrievalSource.fresh_cache)
            return rechecked_value
        if rechecked is not None and rechecked_value is not None:
            stale_record, stale_value = rechecked, rechecked_value

        if not self._backend_available:
            self._emit_refresh(
                context, refresh_id, endpoint, RefreshOutcome.lease_unavailable
            )
            return await self._refresh(
                key=key,
                endpoint=endpoint,
                parameters=parameters,
                response_contract=response_contract,
                profile=profile,
                validate=validate,
                stale_record=stale_record,
                stale_value=stale_value,
                context=context,
                refresh_id=refresh_id,
            )

        owner_token = uuid.uuid4().hex
        deadline = (
            asyncio.get_running_loop().time() + self._transport.follower_wait_seconds
        )
        waiting_logged = False
        while True:
            now = self._utc_now()
            acquired: bool | None = await self._backend_call(
                "lease_acquire",
                self._backend.acquire_lease(
                    key, owner_token, now + _LEASE_DURATION, now
                ),
                default=None,
                context=context,
            )
            if acquired is None:
                self._emit_refresh(
                    context, refresh_id, endpoint, RefreshOutcome.lease_unavailable
                )
                return await self._refresh(
                    key=key,
                    endpoint=endpoint,
                    parameters=parameters,
                    response_contract=response_contract,
                    profile=profile,
                    validate=validate,
                    stale_record=stale_record,
                    stale_value=stale_value,
                    context=context,
                    refresh_id=refresh_id,
                )
            if acquired:
                self._emit_refresh(
                    context, refresh_id, endpoint, RefreshOutcome.lease_acquired
                )
                break
            if not waiting_logged:
                _LOGGER.debug("CFBD cache distributed lease wait endpoint=%s", endpoint)
                self._emit_refresh(
                    context,
                    refresh_id,
                    endpoint,
                    RefreshOutcome.lease_wait_started,
                )
                waiting_logged = True
            retained, value = await self._lookup_record(
                key=key,
                now=now,
                response_contract=response_contract,
                validate=validate,
                context=context,
                profile=profile,
                phase=CacheLookupPhase.lease_wait,
            )
            if (
                retained is not None
                and value is not None
                and retained.fresh_until > now
                and (not force_refresh or retained != refresh_baseline)
            ):
                await self._reproject_record(
                    endpoint=endpoint,
                    parameters=parameters,
                    record=retained,
                    value=value,
                    context=context,
                )
                self._set_source(context, RetrievalSource.fresh_cache)
                self._emit_refresh(
                    context,
                    refresh_id,
                    endpoint,
                    RefreshOutcome.lease_wait_satisfied,
                )
                return value
            if asyncio.get_running_loop().time() >= deadline:
                _LOGGER.warning(
                    "CFBD cache distributed lease timeout endpoint=%s", endpoint
                )
                self._emit_refresh(
                    context, refresh_id, endpoint, RefreshOutcome.lease_timeout
                )
                return await self._refresh(
                    key=key,
                    endpoint=endpoint,
                    parameters=parameters,
                    response_contract=response_contract,
                    profile=profile,
                    validate=validate,
                    stale_record=stale_record,
                    stale_value=stale_value,
                    context=context,
                    refresh_id=refresh_id,
                )
            delay = 0.05 + self._random_source() * 0.15
            await asyncio.sleep(delay)

        renewer = asyncio.create_task(
            self._renew_lease(
                key,
                owner_token,
                context=context,
            )
        )
        try:
            now = self._utc_now()
            retained, value = await self._lookup_record(
                key=key,
                now=now,
                response_contract=response_contract,
                validate=validate,
                context=context,
                profile=profile,
                phase=CacheLookupPhase.post_lease,
            )
            if (
                retained is not None
                and value is not None
                and retained.fresh_until > now
                and (not force_refresh or retained != refresh_baseline)
            ):
                await self._reproject_record(
                    endpoint=endpoint,
                    parameters=parameters,
                    record=retained,
                    value=value,
                    context=context,
                )
                self._set_source(context, RetrievalSource.fresh_cache)
                return value
            if retained is not None and value is not None:
                stale_record, stale_value = retained, value
            return await self._refresh(
                key=key,
                endpoint=endpoint,
                parameters=parameters,
                response_contract=response_contract,
                profile=profile,
                validate=validate,
                stale_record=stale_record,
                stale_value=stale_value,
                context=context,
                refresh_id=refresh_id,
            )
        finally:
            renewer.cancel()
            await asyncio.gather(renewer, return_exceptions=True)
            await asyncio.shield(
                self._backend_call(
                    "lease_release",
                    self._backend.release_lease(key, owner_token),
                    default=False,
                    context=context,
                )
            )
            self._emit_refresh(
                context, refresh_id, endpoint, RefreshOutcome.lease_released
            )

    async def _renew_lease(
        self,
        key: str,
        owner_token: str,
        *,
        context: _OperationContext | None,
    ) -> None:
        """Renew one owned distributed lease until refresh completion."""
        while True:
            await asyncio.sleep(_LEASE_RENEW_INTERVAL_SECONDS)
            renewed = await self._backend_call(
                "lease_renew",
                self._backend.renew_lease(
                    key, owner_token, self._utc_now() + _LEASE_DURATION
                ),
                default=False,
                context=context,
            )
            if not renewed:
                return

    async def _refresh(
        self,
        *,
        key: str,
        endpoint: str,
        parameters: QueryParameters,
        response_contract: str,
        profile: CacheProfile,
        validate: Callable[[object], _ValueT],
        stale_record: ResponseRecord | None,
        stale_value: _ValueT | None,
        context: _OperationContext | None,
        refresh_id: str | None,
    ) -> _ValueT:
        """Refresh one record conditionally and apply permitted stale fallback."""
        conditional_headers: dict[str, str] = {}
        if stale_record is not None and stale_value is not None:
            etag = _safe_validator(stale_record.etag)
            last_modified = _safe_validator(stale_record.last_modified)
            if etag is not None:
                conditional_headers["If-None-Match"] = etag
            elif last_modified is not None:
                conditional_headers["If-Modified-Since"] = last_modified
        if conditional_headers:
            _LOGGER.debug("CFBD response cache revalidation endpoint=%s", endpoint)
        else:
            _LOGGER.debug("CFBD response cache refresh endpoint=%s", endpoint)
        try:
            envelope = await self._transport.get_response(
                endpoint,
                parameters,
                conditional_headers=conditional_headers or None,
                context=context,
                refresh_id=refresh_id,
            )
            if envelope.status == 304:
                if stale_record is None or stale_value is None:
                    raise CFBDCacheBackendError(
                        "Conditional response has no retained cache record"
                    )
                value = stale_value
                body = stale_record.body
                etag = _safe_validator(envelope.etag) or _safe_validator(
                    stale_record.etag
                )
                last_modified = _safe_validator(
                    envelope.last_modified
                ) or _safe_validator(stale_record.last_modified)
            else:
                if envelope.body is None:
                    raise CFBDCacheBackendError("Successful response has no JSON body")
                value = validate(envelope.body)
                body = envelope.raw_body
                etag = _safe_validator(envelope.etag)
                last_modified = _safe_validator(envelope.last_modified)
        except Exception as exc:
            if (
                stale_value is not None
                and stale_record is not None
                and self._policy.stale_if_error
                and stale_record.retained_until > self._utc_now()
                and _allows_stale(exc)
            ):
                _LOGGER.warning(
                    "CFBD response cache stale-if-error endpoint=%s category=%s",
                    endpoint,
                    type(exc).__name__,
                )
                self._set_source(context, RetrievalSource.stale_fallback)
                if context is not None and refresh_id is not None:
                    self._event_dispatcher.emit(
                        StaleFallbackUsed(
                            client_id=context.client_id,
                            operation_id=context.operation_id,
                            refresh_id=refresh_id,
                            endpoint=endpoint,
                            failure_category=_failure_category(exc),
                            record_age_seconds=max(
                                0.0,
                                (
                                    self._utc_now() - stale_record.fetched_at
                                ).total_seconds(),
                            ),
                            record_bytes=len(stale_record.body),
                        )
                    )
                return stale_value
            raise

        self._set_source(
            context,
            (
                RetrievalSource.revalidated_cache
                if envelope.status == 304
                else RetrievalSource.network
            ),
        )
        now = self._utc_now()
        projectable = cast(BaseModel | list[object], value)
        ttl = resolve_ttl(
            profile=profile,
            endpoint=endpoint,
            parameters=parameters,
            value=projectable,
            policy=self._policy,
            now=now,
        )
        if ttl is None:
            self._emit_write(
                context,
                endpoint=endpoint,
                outcome=CacheWriteOutcome.skipped_policy,
                row_count=len(value) if isinstance(value, list) else 1,
                body_bytes=len(body),
            )
            return value
        if len(body) > MAX_RESPONSE_BODY_BYTES:
            self._emit_write(
                context,
                endpoint=endpoint,
                outcome=CacheWriteOutcome.skipped_size,
                row_count=len(value) if isinstance(value, list) else 1,
                body_bytes=len(body),
            )
            return value
        row_count = len(value) if isinstance(value, list) else 1
        record = ResponseRecord(
            key=key,
            endpoint=endpoint,
            response_contract=response_contract,
            body=body,
            fetched_at=now,
            fresh_until=now + ttl.fresh_for,
            retained_until=now + ttl.retain_for,
            etag=etag,
            last_modified=last_modified,
            row_count=row_count,
        )
        projection = project_catalog(
            endpoint=endpoint,
            parameters=parameters,
            value=projectable,
            response_key=key,
            fetched_at=now,
            fresh_until=record.fresh_until,
            retained_until=record.retained_until,
        )
        await self._commit_catalog_response(
            "revalidate" if envelope.status == 304 else "commit",
            record,
            projection,
            context=context,
        )
        return value

    async def _network_only(
        self,
        endpoint: str,
        parameters: QueryParameters,
        response_contract: str,
        profile: CacheProfile,
        validate: Callable[[object], _ValueT],
        *,
        project: bool,
        context: _OperationContext | None,
    ) -> _ValueT:
        """Fetch and validate, optionally populating the transient catalog."""
        refresh_id = (
            self._event_dispatcher.new_refresh_id() if context is not None else None
        )
        if context is not None:
            context.refresh_id = refresh_id
        envelope = await self._transport.get_response(
            endpoint,
            parameters,
            context=context,
            refresh_id=refresh_id,
        )
        if envelope.body is None:
            raise CFBDCacheBackendError("Successful response has no JSON body")
        value = validate(envelope.body)
        if not project or not self._transient_available:
            return value
        now = self._utc_now()
        projectable = cast(BaseModel | list[object], value)
        ttl = resolve_ttl(
            profile=profile,
            endpoint=endpoint,
            parameters=parameters,
            value=projectable,
            policy=self._policy,
            now=now,
        )
        if ttl is None:
            return value
        key = response_cache_key(
            base_url=self._transport.base_url,
            endpoint=endpoint,
            parameters=parameters,
            response_contract=response_contract,
            credential_scope=self._credential_scope,
        )
        record = ResponseRecord(
            key=key,
            endpoint=endpoint,
            response_contract=response_contract,
            body=b"",
            fetched_at=now,
            fresh_until=now + ttl.fresh_for,
            retained_until=now + ttl.retain_for,
            etag=None,
            last_modified=None,
            row_count=len(value) if isinstance(value, list) else 1,
        )
        projection = project_catalog(
            endpoint=endpoint,
            parameters=parameters,
            value=projectable,
            response_key=key,
            fetched_at=now,
            fresh_until=record.fresh_until,
            retained_until=record.retained_until,
        )
        await self._transient.commit_response(record, projection)
        return value

    async def _reproject_record(
        self,
        *,
        endpoint: str,
        parameters: QueryParameters,
        record: ResponseRecord,
        value: _ValueT,
        context: _OperationContext | None,
    ) -> None:
        """Reproject one retained validated response through the current contract."""
        projectable = cast(BaseModel | list[object], value)
        projection = project_catalog(
            endpoint=endpoint,
            parameters=parameters,
            value=projectable,
            response_key=record.key,
            fetched_at=record.fetched_at,
            fresh_until=record.fresh_until,
            retained_until=record.retained_until,
        )
        await self._commit_catalog_response(
            "reproject", record, projection, context=context
        )

    async def _commit_catalog_response(
        self,
        operation: str,
        record: ResponseRecord,
        projection: CatalogProjection,
        *,
        context: _OperationContext | None,
    ) -> None:
        """Commit durably and mirror the canonical merged state in memory."""
        answered, merged = await self._catalog_call(
            operation,
            self._backend.commit_response(record, projection),
            timeout_seconds=self._catalog_commit_timeout(projection),
            context=context,
        )
        write_answered = answered
        if not answered:
            answered, durable_merge = await self._catalog_call(
                f"{operation}_merge_read",
                self._backend.merge_catalog_projection(record, projection),
                context=context,
            )
            if answered:
                merged = durable_merge
        await self._transient.commit_response(record, merged or projection)
        outcome = {
            "commit": CacheWriteOutcome.stored,
            "revalidate": CacheWriteOutcome.revalidated,
            "reproject": CacheWriteOutcome.reprojected,
        }[operation]
        self._emit_write(
            context,
            endpoint=record.endpoint,
            outcome=(outcome if write_answered else CacheWriteOutcome.backend_error),
            row_count=record.row_count,
            body_bytes=len(record.body),
        )

    async def _lookup_record(
        self,
        *,
        key: str,
        now: datetime,
        response_contract: str,
        validate: Callable[[object], _ValueT],
        context: _OperationContext | None,
        profile: CacheProfile,
        phase: CacheLookupPhase,
    ) -> tuple[ResponseRecord | None, _ValueT | None]:
        """Read, validate, and observe one untrusted cache record."""
        read = await self._read_record(key, now, context=context)
        value, invalid_outcome = await self._validated_record(
            read.record,
            response_contract,
            validate,
            context=context,
        )
        if not read.answered:
            outcome = CacheLookupOutcome.backend_error
        elif invalid_outcome is not None:
            outcome = invalid_outcome
        elif read.record is None:
            outcome = CacheLookupOutcome.miss
        elif read.record.fresh_until > now:
            outcome = CacheLookupOutcome.fresh_hit
        else:
            outcome = CacheLookupOutcome.stale
        self._emit_lookup(
            context,
            profile=profile,
            phase=phase,
            outcome=outcome,
            record=read.record,
            now=now,
        )
        return read.record, value

    async def _read_record(
        self,
        key: str,
        now: datetime,
        *,
        context: _OperationContext | None,
    ) -> _CacheRead:
        """Read a retained record while preserving backend failure from absence."""
        if not self._backend_available:
            return _CacheRead(record=None, answered=False)
        answered, record = await self._backend_call_result(
            "read",
            self._backend.get_response(key, now),
            default=None,
            context=context,
        )
        return _CacheRead(record=record, answered=answered)

    async def _validated_record(
        self,
        record: ResponseRecord | None,
        response_contract: str,
        validate: Callable[[object], _ValueT],
        *,
        context: _OperationContext | None,
    ) -> tuple[_ValueT | None, CacheLookupOutcome | None]:
        """Decode and validate one untrusted record or evict it as corrupt."""
        if record is None:
            return None, None
        if (
            record.response_contract != response_contract
            or len(record.body) > MAX_RESPONSE_BODY_BYTES
        ):
            await self._delete_record(record.key, context=context)
            return None, CacheLookupOutcome.incompatible
        try:
            decoded: object = json.loads(record.body)
            return validate(decoded), None
        except Exception:
            await self._delete_record(record.key, context=context)
            _LOGGER.warning("CFBD response cache corrupt record evicted")
            return None, CacheLookupOutcome.corrupt

    async def _delete_record(
        self, key: str, *, context: _OperationContext | None
    ) -> None:
        """Delete a corrupt response record with fail-open behavior."""
        if self._backend_available:
            await self._backend_call(
                "delete",
                self._backend.delete_response(key),
                default=None,
                context=context,
            )

    async def _backend_call[ResultT](
        self,
        operation: str,
        awaitable: Awaitable[ResultT],
        *,
        default: ResultT,
        timeout_seconds: float | None = None,
        context: _OperationContext | None = None,
    ) -> ResultT:
        """Bound backend I/O and convert failures to observable fail-open results."""
        _, result = await self._backend_call_result(
            operation,
            awaitable,
            default=default,
            timeout_seconds=timeout_seconds,
            context=context,
        )
        return result

    async def _backend_call_result[ResultT](
        self,
        operation: str,
        awaitable: Awaitable[ResultT],
        *,
        default: ResultT,
        timeout_seconds: float | None = None,
        context: _OperationContext | None = None,
    ) -> tuple[bool, ResultT]:
        """Return whether bounded backend I/O answered and its safe result."""
        try:
            async with asyncio.timeout(timeout_seconds or self._io_timeout_seconds):
                return True, await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.warning(
                "CFBD cache backend failure operation=%s category=%s",
                operation,
                type(exc).__name__,
            )
            self._emit_backend_failure(operation, exc, context=context)
            return False, default

    def _catalog_commit_timeout(self, projection: CatalogProjection) -> float:
        """Return a bounded deadline scaled to atomic observation-batch size."""
        additional = len(projection.observations) / _OBSERVATIONS_PER_COMMIT_SECOND
        return min(
            _MAX_CATALOG_COMMIT_TIMEOUT_SECONDS,
            max(self._io_timeout_seconds, self._io_timeout_seconds + additional),
        )

    async def _identity_backend_call[ResultT](
        self,
        operation: str,
        awaitable: Awaitable[ResultT],
        *,
        default: ResultT,
        strict: bool,
    ) -> ResultT:
        """Bound catalog I/O, optionally failing explicitly for local-only intent."""
        if not self._backend_available:
            if isinstance(awaitable, Coroutine):
                awaitable.close()
            if strict:
                raise CFBDCacheBackendError(
                    "The configured identity catalog backend is unavailable"
                )
            return default
        try:
            async with asyncio.timeout(self._io_timeout_seconds):
                return await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.warning(
                "CFBD identity backend failure operation=%s category=%s",
                operation,
                type(exc).__name__,
            )
            if strict:
                raise CFBDCacheBackendError(
                    "The configured identity catalog backend could not answer"
                ) from exc
            return default

    async def _catalog_call[ResultT](
        self,
        operation: str,
        awaitable: Awaitable[ResultT],
        *,
        timeout_seconds: float | None = None,
        context: _OperationContext | None = None,
    ) -> tuple[bool, ResultT | None]:
        """Return whether the persistent catalog answered and its result."""
        if not self._backend_available:
            if isinstance(awaitable, Coroutine):
                awaitable.close()
            return False, None
        try:
            async with asyncio.timeout(timeout_seconds or self._io_timeout_seconds):
                return True, await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.warning(
                "CFBD identity backend failure operation=%s category=%s",
                operation,
                type(exc).__name__,
            )
            self._emit_backend_failure(operation, exc, context=context)
            return False, None

    def _set_source(
        self, context: _OperationContext | None, source: RetrievalSource
    ) -> None:
        """Set one observed operation's bounded retrieval source."""
        if context is not None:
            context.source = source

    def _emit_lookup(
        self,
        context: _OperationContext | None,
        *,
        profile: CacheProfile,
        phase: CacheLookupPhase,
        outcome: CacheLookupOutcome,
        record: ResponseRecord | None = None,
        now: datetime | None = None,
    ) -> None:
        """Emit one safe response-cache lookup event."""
        if context is None or not self._event_dispatcher.enabled:
            return
        age = None
        if record is not None and now is not None:
            age = max(0.0, (now - record.fetched_at).total_seconds())
        self._event_dispatcher.emit(
            CacheLookupCompleted(
                client_id=context.client_id,
                operation_id=context.operation_id,
                endpoint=context.endpoint,
                profile=profile,
                phase=phase,
                outcome=outcome,
                record_age_seconds=age,
                record_bytes=(len(record.body) if record is not None else None),
            )
        )

    def _emit_refresh(
        self,
        context: _OperationContext | None,
        refresh_id: str | None,
        endpoint: str,
        outcome: RefreshOutcome,
    ) -> None:
        """Emit one safe refresh-coordination event."""
        if context is None or refresh_id is None or not self._event_dispatcher.enabled:
            return
        self._event_dispatcher.emit(
            RefreshCoordinated(
                client_id=context.client_id,
                operation_id=context.operation_id,
                refresh_id=refresh_id,
                endpoint=endpoint,
                outcome=outcome,
            )
        )

    def _emit_write(
        self,
        context: _OperationContext | None,
        *,
        endpoint: str,
        outcome: CacheWriteOutcome,
        row_count: int,
        body_bytes: int,
    ) -> None:
        """Emit one safe response-cache write disposition."""
        if context is None or not self._event_dispatcher.enabled:
            return
        self._event_dispatcher.emit(
            CacheWriteCompleted(
                client_id=context.client_id,
                operation_id=context.operation_id,
                endpoint=endpoint,
                outcome=outcome,
                row_count=row_count,
                body_bytes=body_bytes,
            )
        )

    def _emit_backend_failure(
        self,
        operation: str,
        error: BaseException,
        *,
        context: _OperationContext | None,
    ) -> None:
        """Emit one safe cache failure without retaining its exception."""
        if not self._event_dispatcher.enabled:
            return
        self._event_dispatcher.emit(
            CacheBackendFailed(
                client_id=self._event_dispatcher.client_id,
                operation_id=(context.operation_id if context is not None else None),
                endpoint=(context.endpoint if context is not None else None),
                operation=operation[:64],
                failure_category=_failure_category(error),
            )
        )


def _observe_flight_completion(task: asyncio.Task[object]) -> None:
    """Retrieve an internal flight result even if every public waiter cancelled."""
    if task.cancelled():
        return
    task.exception()


def _allows_stale(error: Exception) -> bool:
    """Return whether an exhausted failure is safe to mask with retained data."""
    if isinstance(error, CFBDHTTPError):
        return error.status in {408, 429} or error.status >= 500
    if isinstance(error, CFBDTransportError):
        return error.category in {"timeout", "connection", "truncated_payload"}
    return False


def _safe_validator(value: str | None) -> str | None:
    """Return a bounded single-line HTTP validator safe for later reuse."""
    if value is None or len(value) > 1024 or "\r" in value or "\n" in value:
        return None
    return value
