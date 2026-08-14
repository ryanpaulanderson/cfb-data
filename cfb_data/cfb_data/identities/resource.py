"""Resolve compact identities and plan minimal resumable hydration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._catalog.sources import IdentitySourceSpec, identity_source
from cfb_data._executor import _EndpointExecutor, _serialize_request
from cfb_data.cache._catalog import canonical_filters
from cfb_data.cache._coordinator import CacheCoordinator
from cfb_data.cache.config import CacheMode
from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
from cfb_data.conferences.models.pydantic.requests import (
    ConferenceAffiliationsRequest,
    ConferencesRequest,
)
from cfb_data.conferences.models.pydantic.responses import (
    Conference,
    ConferenceClassification,
    TeamConferenceAffiliation,
)
from cfb_data.enums import Classification
from cfb_data.errors import (
    CFBDCacheBackendError,
    CFBDCacheMissError,
    CFBDIdentityAmbiguityError,
    CFBDIdentityNotFoundError,
)
from cfb_data.games.models.pydantic.identity import GameIdentity
from cfb_data.games.models.pydantic.requests import GamesRequest
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.identities.contracts import FreshnessMode, HydrationPlan
from cfb_data.players.models.pydantic.identity import AthleteIdentity
from cfb_data.players.models.pydantic.requests import PlayerSearchRequest
from cfb_data.players.models.pydantic.responses import PlayerSearchResult
from cfb_data.plays.models.pydantic.responses import PlayStatType, PlayType
from cfb_data.stats.models.pydantic.responses import _StatCategoryValue
from cfb_data.teams.models.pydantic.identity import TeamIdentity
from cfb_data.teams.models.pydantic.requests import (
    FBSTeamsRequest,
    RosterRequest,
    TeamsRequest,
)
from cfb_data.teams.models.pydantic.responses import RosterPlayer, Team
from cfb_data.venues.models.pydantic.identity import VenueIdentity
from cfb_data.venues.models.pydantic.responses import Venue

_TEAM_ROWS = TypeAdapter(list[Team])
_CONFERENCE_ROWS = TypeAdapter(list[Conference])
_AFFILIATION_ROWS = TypeAdapter(list[TeamConferenceAffiliation])
_VENUE_ROWS = TypeAdapter(list[Venue])
_GAME_ROWS = TypeAdapter(list[Game])
_ROSTER_ROWS = TypeAdapter(list[RosterPlayer])
_PLAYER_SEARCH_ROWS = TypeAdapter(list[PlayerSearchResult])
_PLAY_TYPE_ROWS = TypeAdapter(list[PlayType])
_PLAY_STAT_TYPE_ROWS = TypeAdapter(list[PlayStatType])
_CATEGORY_VALUES = TypeAdapter(list[_StatCategoryValue])
_LOGGER = logging.getLogger(__name__)


class _EmptyRequest(BaseModel):
    """Represent an identity hydration route with no filters."""

    model_config = ConfigDict(extra="forbid")


_EMPTY_REQUEST = _EmptyRequest()


@dataclass(frozen=True, slots=True)
class _HydrationCall:
    """Describe one capability-producing hydration request."""

    endpoint: str
    canonical_filters: str
    capability: str
    fetch: Callable[[], Awaitable[object]]


class TeamIdentities:
    """Resolve compact team identities without DataFrame materialization."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind shared execution and catalog coordination services."""
        self._executor = executor
        self._coordinator = coordinator

    async def resolve(
        self,
        query: str | int,
        *,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> TeamIdentity:
        """Resolve an exact team ID, school, abbreviation, or alternate name.

        :param query: Provider ID or exact normalized name.
        :param freshness: Whether missing or stale coverage may use the API.
        :return: One unambiguous compact team identity.
        :raises CFBDIdentityNotFoundError: If no exact team can be resolved.
        :raises CFBDIdentityAmbiguityError: If multiple teams match exactly.
        """
        matches, catalog_read_failed = await _initial_catalog_lookup(
            _team_matches(
                self._coordinator,
                query,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=[],
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Team", matches)
        coverage_fresh = False
        if not catalog_read_failed:
            coverage_fresh = await self._coordinator.has_fresh_coverage(
                endpoint="/teams",
                canonical_filters="",
                capability="team.core_identity",
            )
        if not coverage_fresh and matches:
            match_ids = {match.id for match in matches}
            coverage_fresh = await _has_matching_fresh_coverage(
                self._executor,
                self._coordinator,
                partitions=(("/teams/fbs", FBSTeamsRequest()),),
                response_adapter=_TEAM_ROWS,
                capability="team.core_identity",
                matches=lambda row: row.id in match_ids,
            )
        if coverage_fresh:
            return _one("Team", matches)
        try:
            await self._executor.fetch_many(
                endpoint="/teams", request=TeamsRequest(), response_adapter=_TEAM_ROWS
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=team")
                return _one("Team", matches)
            raise
        matches = await _team_matches(self._coordinator, query, strict=False)
        return _one("Team", matches)

    async def resolve_id(
        self,
        query: str | int,
        *,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> int:
        """Return one exact team's provider ID."""
        return (await self.resolve(query, freshness=freshness)).id

    async def resolve_name(
        self,
        query: str | int,
        *,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> str:
        """Return one exact team's canonical school name."""
        return (await self.resolve(query, freshness=freshness)).school


class ConferenceIdentities:
    """Resolve compact conference identities without DataFrames."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind shared execution and catalog coordination services."""
        self._executor = executor
        self._coordinator = coordinator

    async def resolve(
        self,
        query: str | int,
        *,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> ConferenceIdentity:
        """Resolve an exact conference ID, name, or abbreviation."""
        matches, catalog_read_failed = await _initial_catalog_lookup(
            _conference_matches(
                self._coordinator,
                query,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=[],
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Conference", matches)
        coverage_fresh = False
        if not catalog_read_failed:
            coverage_fresh = await self._coordinator.has_fresh_coverage(
                endpoint="/conferences",
                canonical_filters="",
                capability="conference.identity",
            )
        if not coverage_fresh and matches:
            match_ids = {match.id for match in matches}
            coverage_fresh = await _has_matching_fresh_coverage(
                self._executor,
                self._coordinator,
                partitions=_classified_conference_partitions(),
                response_adapter=_CONFERENCE_ROWS,
                capability="conference.identity",
                matches=lambda row: row.id in match_ids,
            )
        if coverage_fresh:
            return _one("Conference", matches)
        try:
            await self._executor.fetch_many(
                endpoint="/conferences",
                request=ConferencesRequest(),
                response_adapter=_CONFERENCE_ROWS,
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=conference")
                return _one("Conference", matches)
            raise
        matches = await _conference_matches(self._coordinator, query, strict=False)
        return _one("Conference", matches)


class VenueIdentities:
    """Resolve compact venue identities without DataFrames."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind shared execution and catalog coordination services."""
        self._executor = executor
        self._coordinator = coordinator

    async def resolve(
        self,
        query: str | int,
        *,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> VenueIdentity:
        """Resolve an exact venue ID or canonical name."""
        matches, catalog_read_failed = await _initial_catalog_lookup(
            _venue_matches(
                self._coordinator,
                query,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=[],
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Venue", matches)
        if not catalog_read_failed and await self._coordinator.has_fresh_coverage(
            endpoint="/venues",
            canonical_filters="",
            capability="venue.identity",
        ):
            return _one("Venue", matches)
        try:
            await self._executor.fetch_many(
                endpoint="/venues", request=_EMPTY_REQUEST, response_adapter=_VENUE_ROWS
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=venue")
                return _one("Venue", matches)
            raise
        matches = await _venue_matches(self._coordinator, query, strict=False)
        return _one("Venue", matches)


class GameIdentities:
    """Resolve and search compact game identities."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind shared execution and catalog coordination services."""
        self._executor = executor
        self._coordinator = coordinator

    async def resolve(
        self,
        *,
        game_id: int,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> GameIdentity:
        """Resolve one game by exact provider ID."""
        match, catalog_read_failed = await _initial_catalog_lookup(
            self._coordinator.find_game(
                game_id,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=None,
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Game", [match] if match is not None else [])
        filters = canonical_filters({"id": game_id})
        broad_fresh = False
        if not catalog_read_failed and match is not None and match.season is not None:
            broad_fresh = await self._coordinator.has_fresh_coverage(
                endpoint="/games",
                canonical_filters=canonical_filters({"year": match.season}),
                capability="game.identity",
            )
        exact_fresh = False
        if not catalog_read_failed:
            exact_fresh = await self._coordinator.has_fresh_coverage(
                endpoint="/games",
                canonical_filters=filters,
                capability="game.identity",
            )
        scoped_fresh = False
        if (
            not broad_fresh
            and not exact_fresh
            and match is not None
            and match.season is not None
        ):
            scoped_fresh = await _has_matching_fresh_coverage(
                self._executor,
                self._coordinator,
                partitions=_classified_game_partitions(match.season),
                response_adapter=_GAME_ROWS,
                capability="game.identity",
                matches=lambda row: row.id == game_id,
            )
        if broad_fresh or exact_fresh or scoped_fresh:
            return _one("Game", [match] if match is not None else [])
        try:
            await self._executor.fetch_many(
                endpoint="/games",
                request=GamesRequest(game_id=game_id),
                response_adapter=_GAME_ROWS,
            )
        except Exception as exc:
            if match is not None and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=game")
                return match
            raise
        match = await self._coordinator.find_game(game_id)
        return _one("Game", [match] if match is not None else [])

    async def find(
        self,
        *,
        season: int,
        week: int | None = None,
        team: str | None = None,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> list[GameIdentity]:
        """Return game identities matching an explicit season partition."""
        request = GamesRequest(year=season, week=week, team=team)
        filters = canonical_filters(_serialize_request("/games", request))
        matches, catalog_read_failed = await _initial_catalog_lookup(
            self._coordinator.find_games(
                season=season,
                week=week,
                team=team,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=[],
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return matches
        if not catalog_read_failed and await self._coordinator.has_fresh_coverage(
            endpoint="/games",
            canonical_filters=filters,
            capability="game.identity",
        ):
            return matches
        try:
            await self._executor.fetch_many(
                endpoint="/games", request=request, response_adapter=_GAME_ROWS
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=game")
                return matches
            raise
        matches = await self._coordinator.find_games(
            season=season, week=week, team=team
        )
        return matches


class AthleteIdentities:
    """Resolve exact athlete identities within optional team-season scope."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind shared execution and catalog coordination services."""
        self._executor = executor
        self._coordinator = coordinator

    async def resolve(
        self,
        *,
        name: str,
        team: str | None = None,
        season: int | None = None,
        freshness: FreshnessMode = FreshnessMode.ensure_fresh,
    ) -> AthleteIdentity:
        """Resolve one exact athlete, requiring scope when names are duplicated."""
        matches, catalog_read_failed = await _initial_catalog_lookup(
            self._coordinator.find_athletes(
                name=name,
                team=team,
                season=season,
                strict=freshness is not FreshnessMode.allow_stale,
            ),
            freshness=freshness,
            empty=[],
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one_athlete(matches)

        if season is not None:
            request: BaseModel = RosterRequest(year=season, team=team)
            endpoint = "/roster"
            capability = "athlete.identity"
        else:
            request = PlayerSearchRequest(search_term=name, team=team)
            endpoint = "/player/search"
            capability = "athlete.identity"
        filters = canonical_filters(_serialize_request(endpoint, request))
        coverage_fresh = False
        if not catalog_read_failed:
            coverage_fresh = await self._coordinator.has_fresh_coverage(
                endpoint=endpoint,
                canonical_filters=filters,
                capability=capability,
            )
        if (
            not coverage_fresh
            and matches
            and season is not None
            and isinstance(request, RosterRequest)
        ):
            match_ids = {match.id for match in matches}
            coverage_fresh = await _has_matching_fresh_coverage(
                self._executor,
                self._coordinator,
                partitions=_classified_roster_partitions(season),
                response_adapter=_ROSTER_ROWS,
                capability=capability,
                matches=lambda row: row.id in match_ids,
            )
        if coverage_fresh:
            return _one_athlete(matches)

        try:
            if isinstance(request, RosterRequest):
                await self._executor.fetch_many(
                    endpoint=endpoint, request=request, response_adapter=_ROSTER_ROWS
                )
            else:
                await self._executor.fetch_many(
                    endpoint=endpoint,
                    request=request,
                    response_adapter=_PLAYER_SEARCH_ROWS,
                )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=athlete")
                return _one_athlete(matches)
            raise
        matches = await self._coordinator.find_athletes(
            name=name, team=team, season=season
        )
        return _one_athlete(matches)


class IdentitiesResource:
    """Expose typed compact identity lookup and minimal hydration."""

    def __init__(
        self, executor: _EndpointExecutor, coordinator: CacheCoordinator
    ) -> None:
        """Bind all identity domains to shared execution and persistence."""
        self.teams = TeamIdentities(executor, coordinator)
        self.conferences = ConferenceIdentities(executor, coordinator)
        self.venues = VenueIdentities(executor, coordinator)
        self.games = GameIdentities(executor, coordinator)
        self.athletes = AthleteIdentities(executor, coordinator)
        self._executor = executor
        self._coordinator = coordinator

    async def hydrate(
        self,
        *,
        seasons: Sequence[int],
        classification: Classification | str | None = None,
        include_vocabularies: bool = False,
        dry_run: bool = False,
        max_concurrency: int = 4,
    ) -> HydrationPlan:
        """Hydrate missing canonical identity partitions with bounded concurrency.

        :param seasons: Explicit seasons whose games and rosters are required.
        :param classification: Optional division scope for supported partitions.
        :param include_vocabularies: Also hydrate play and statistic vocabularies.
        :param dry_run: Report missing API partitions without performing I/O.
        :param max_concurrency: Maximum simultaneous hydration operations.
        :return: Planned endpoints and completed-call count.
        :raises ValueError: If seasons, classification, or concurrency are invalid.
        :raises CFBDCacheBackendError: If durable catalog persistence is unavailable.
        """
        self._coordinator.ensure_active()
        if not self._coordinator.identity_store_available:
            raise CFBDCacheBackendError(
                "Identity hydration requires an available cache catalog backend"
            )
        if any(
            isinstance(season, bool) or not isinstance(season, int) or season < 1869
            for season in seasons
        ):
            raise ValueError("seasons must contain four-digit seasons from 1869 onward")
        normalized_seasons = tuple(sorted(set(seasons)))
        try:
            normalized_classification = (
                None if classification is None else Classification(classification)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "classification must be a supported Classification"
            ) from exc
        if (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or max_concurrency < 1
        ):
            raise ValueError("max_concurrency must be a positive integer")

        calls = self._hydration_calls(
            normalized_seasons,
            normalized_classification,
            include_vocabularies,
        )
        pending: list[_HydrationCall] = []
        for call in calls:
            if not await self._coordinator.has_fresh_coverage(
                endpoint=call.endpoint,
                canonical_filters=call.canonical_filters,
                capability=call.capability,
                strict=True,
            ):
                pending.append(call)
        endpoints = tuple(call.endpoint for call in pending)
        if dry_run:
            return HydrationPlan(
                seasons=normalized_seasons,
                classification=normalized_classification,
                endpoints=endpoints,
                planned_calls=len(pending),
                completed_calls=0,
                dry_run=True,
            )

        semaphore = asyncio.Semaphore(max_concurrency)
        stop_event = asyncio.Event()

        async def execute(call: _HydrationCall) -> None:
            try:
                async with semaphore:
                    if stop_event.is_set():
                        return
                    await call.fetch()
            except BaseException as error:
                stop_event.set()
                failure_write = asyncio.create_task(
                    self._coordinator.record_hydration_failure(
                        endpoint=call.endpoint,
                        canonical_filters=call.canonical_filters,
                        failure_category=type(error).__name__,
                    )
                )
                try:
                    await asyncio.shield(failure_write)
                except asyncio.CancelledError:
                    await failure_write
                raise

        tasks = [asyncio.create_task(execute(call)) for call in pending]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        for call in pending:
            persisted = await self._coordinator.has_fresh_coverage(
                endpoint=call.endpoint,
                canonical_filters=call.canonical_filters,
                capability=call.capability,
                strict=True,
            )
            if not persisted:
                await self._coordinator.record_hydration_failure(
                    endpoint=call.endpoint,
                    canonical_filters=call.canonical_filters,
                    failure_category="CFBDCacheBackendError",
                )
                raise CFBDCacheBackendError(
                    "Identity hydration did not durably commit "
                    f"endpoint={call.endpoint}"
                )
        return HydrationPlan(
            seasons=normalized_seasons,
            classification=normalized_classification,
            endpoints=endpoints,
            planned_calls=len(pending),
            completed_calls=len(pending),
            dry_run=False,
        )

    def _hydration_calls(
        self,
        seasons: tuple[int, ...],
        classification: Classification | None,
        include_vocabularies: bool,
    ) -> list[_HydrationCall]:
        """Return the canonical ``4 + 2S`` or ``7 + 2S`` hydration plan."""
        conference_classification = (
            None
            if classification is None
            else ConferenceClassification(classification.value)
        )
        team_call = (
            self._many_call(
                _hydration_source("/teams/fbs"),
                FBSTeamsRequest(),
                _TEAM_ROWS,
            )
            if classification is Classification.fbs
            else self._many_call(
                _hydration_source("/teams"), TeamsRequest(), _TEAM_ROWS
            )
        )
        calls = [
            team_call,
            self._many_call(_hydration_source("/venues"), _EMPTY_REQUEST, _VENUE_ROWS),
            self._many_call(
                _hydration_source("/conferences"),
                ConferencesRequest(classification=conference_classification),
                _CONFERENCE_ROWS,
            ),
            self._many_call(
                _hydration_source("/conferences/affiliations"),
                ConferenceAffiliationsRequest(classification=conference_classification),
                _AFFILIATION_ROWS,
            ),
        ]
        for season in seasons:
            calls.extend(
                [
                    self._many_call(
                        _hydration_source("/games"),
                        GamesRequest(
                            year=season,
                            classification=classification,
                        ),
                        _GAME_ROWS,
                    ),
                    self._many_call(
                        _hydration_source("/roster"),
                        RosterRequest(
                            year=season,
                            classification=classification,
                        ),
                        _ROSTER_ROWS,
                    ),
                ]
            )
        if include_vocabularies:
            calls.extend(
                [
                    self._many_call(
                        _hydration_source("/plays/types"),
                        _EMPTY_REQUEST,
                        _PLAY_TYPE_ROWS,
                    ),
                    self._many_call(
                        _hydration_source("/plays/stats/types"),
                        _EMPTY_REQUEST,
                        _PLAY_STAT_TYPE_ROWS,
                    ),
                    self._values_call(
                        _hydration_source("/stats/categories"),
                        _EMPTY_REQUEST,
                        _CATEGORY_VALUES,
                    ),
                ]
            )
        return calls

    def _many_call[RowT: BaseModel](
        self,
        source: IdentitySourceSpec,
        request: BaseModel,
        adapter: TypeAdapter[list[RowT]],
    ) -> _HydrationCall:
        """Build one typed model-list hydration operation."""
        endpoint = source.endpoint
        capability = _required_hydration_capability(source)

        async def fetch() -> object:
            return await self._executor.fetch_many(
                endpoint=endpoint, request=request, response_adapter=adapter
            )

        return _HydrationCall(
            endpoint=endpoint,
            canonical_filters=canonical_filters(_serialize_request(endpoint, request)),
            capability=capability,
            fetch=fetch,
        )

    def _values_call[ValueT](
        self,
        source: IdentitySourceSpec,
        request: BaseModel,
        adapter: TypeAdapter[list[ValueT]],
    ) -> _HydrationCall:
        """Build one typed scalar-list hydration operation."""
        endpoint = source.endpoint
        capability = _required_hydration_capability(source)

        async def fetch() -> object:
            return await self._executor.fetch_values(
                endpoint=endpoint, request=request, response_adapter=adapter
            )

        return _HydrationCall(
            endpoint=endpoint,
            canonical_filters=canonical_filters(_serialize_request(endpoint, request)),
            capability=capability,
            fetch=fetch,
        )


def _hydration_source(endpoint: str) -> IdentitySourceSpec:
    """Return one explicitly hydration-capable endpoint specification."""
    source = identity_source(endpoint)
    _required_hydration_capability(source)
    return source


def _required_hydration_capability(source: IdentitySourceSpec) -> str:
    """Return a source's hydration capability or reject an invalid plan."""
    if source.hydration_capability is None:
        raise RuntimeError(f"Endpoint {source.endpoint} is not a hydration source")
    return source.hydration_capability


async def _initial_catalog_lookup[ResultT](
    lookup: Awaitable[ResultT],
    *,
    freshness: FreshnessMode,
    empty: ResultT,
) -> tuple[ResultT, bool]:
    """Return an initial catalog result while preserving read failure state.

    :param lookup: Strict catalog lookup for the requested identity operation.
    :param freshness: Caller-selected identity freshness behavior.
    :param empty: Empty result used to continue an API-capable lookup.
    :return: Catalog result and whether the catalog failed to answer.
    :raises CFBDCacheBackendError: If a local-only lookup cannot be answered.
    """
    try:
        return await lookup, False
    except CFBDCacheBackendError:
        if freshness is FreshnessMode.local_only:
            raise
        return empty, True


async def _team_matches(
    coordinator: CacheCoordinator, query: str | int, *, strict: bool
) -> list[TeamIdentity]:
    """Apply provider-ID precedence before normalized team-name matching."""
    if isinstance(query, str) and query.strip().isdigit():
        by_id = await coordinator.find_teams(int(query.strip()), strict=strict)
        if by_id:
            return by_id
    return await coordinator.find_teams(query, strict=strict)


async def _has_matching_fresh_coverage[RowT: BaseModel](
    executor: _EndpointExecutor,
    coordinator: CacheCoordinator,
    *,
    partitions: Sequence[tuple[str, BaseModel]],
    response_adapter: TypeAdapter[list[RowT]],
    capability: str,
    matches: Callable[[RowT], bool],
) -> bool:
    """Return whether a fresh partition's validated response contains the match.

    :param executor: Shared endpoint execution boundary.
    :param coordinator: Cache and catalog coordinator.
    :param partitions: Candidate endpoint requests ordered by hydration preference.
    :param response_adapter: Validated response contract for every candidate request.
    :param capability: Catalog capability each partition must establish.
    :param matches: Predicate proving that a response row represents the identity.
    :return: Whether a fresh compatible partition contains the matched identity.
    """
    for endpoint, request in partitions:
        filters = canonical_filters(_serialize_request(endpoint, request))
        if not await coordinator.has_fresh_coverage(
            endpoint=endpoint,
            canonical_filters=filters,
            capability=capability,
        ):
            continue
        try:
            with coordinator.mode_scope(CacheMode.local_only):
                rows = await executor.fetch_many(
                    endpoint=endpoint,
                    request=request,
                    response_adapter=response_adapter,
                )
        except CFBDCacheMissError:
            continue
        if any(matches(row) for row in rows):
            return True
    return False


def _classified_conference_partitions() -> tuple[tuple[str, BaseModel], ...]:
    """Return requests produced by classified conference hydration."""
    return tuple(
        (
            "/conferences",
            ConferencesRequest(
                classification=ConferenceClassification(classification.value)
            ),
        )
        for classification in Classification
    )


def _classified_game_partitions(season: int) -> tuple[tuple[str, BaseModel], ...]:
    """Return requests produced by classified game hydration."""
    return tuple(
        (
            "/games",
            GamesRequest(year=season, classification=classification),
        )
        for classification in Classification
    )


def _classified_roster_partitions(season: int) -> tuple[tuple[str, BaseModel], ...]:
    """Return requests produced by classified roster hydration."""
    return tuple(
        (
            "/roster",
            RosterRequest(year=season, classification=classification),
        )
        for classification in Classification
    )


async def _conference_matches(
    coordinator: CacheCoordinator, query: str | int, *, strict: bool
) -> list[ConferenceIdentity]:
    """Apply provider-ID precedence before normalized conference matching."""
    if isinstance(query, str) and query.strip().isdigit():
        by_id = await coordinator.find_conferences(int(query.strip()), strict=strict)
        if by_id:
            return by_id
    return await coordinator.find_conferences(query, strict=strict)


async def _venue_matches(
    coordinator: CacheCoordinator, query: str | int, *, strict: bool
) -> list[VenueIdentity]:
    """Apply provider-ID precedence before normalized venue-name matching."""
    if isinstance(query, str) and query.strip().isdigit():
        by_id = await coordinator.find_venues(int(query.strip()), strict=strict)
        if by_id:
            return by_id
    return await coordinator.find_venues(query, strict=strict)


def _one[IdentityT](label: str, matches: Sequence[IdentityT]) -> IdentityT:
    """Return one match without guessing among zero or multiple candidates."""
    if not matches:
        raise CFBDIdentityNotFoundError(f"{label} identity was not found")
    if len(matches) > 1:
        summaries = ", ".join(_safe_summary(match) for match in matches[:10])
        raise CFBDIdentityAmbiguityError(
            f"{label} identity is ambiguous among: {summaries}"
        )
    return matches[0]


def _one_athlete(matches: Sequence[AthleteIdentity]) -> AthleteIdentity:
    """Return one provider athlete while collapsing membership projections."""
    if not matches:
        raise CFBDIdentityNotFoundError("Athlete identity was not found")
    by_id: dict[str, list[AthleteIdentity]] = {}
    for match in matches:
        by_id.setdefault(match.id, []).append(match)
    if len(by_id) > 1:
        return _one("Athlete", [memberships[0] for memberships in by_id.values()])

    memberships = next(iter(by_id.values()))
    first = memberships[0]
    teams = {membership.team for membership in memberships}
    seasons = {membership.season for membership in memberships}
    positions = {
        membership.position
        for membership in memberships
        if membership.position is not None
    }
    return AthleteIdentity(
        id=first.id,
        name=first.name,
        position=next(iter(positions)) if len(positions) == 1 else first.position,
        team=next(iter(teams)) if len(teams) == 1 else None,
        season=next(iter(seasons)) if len(seasons) == 1 else None,
    )


def _safe_summary(value: object) -> str:
    """Return a bounded candidate summary containing only identity fields."""
    identifier = getattr(value, "id", "unknown")
    name = next(
        (
            candidate
            for candidate in (
                getattr(value, "school", None),
                getattr(value, "name", None),
            )
            if isinstance(candidate, str)
        ),
        "unknown",
    )
    return f"{identifier}:{name[:80]}"
