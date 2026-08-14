"""Resolve compact identities and plan minimal resumable hydration."""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._executor import _EndpointExecutor, _serialize_request
from cfb_data.cache._catalog import canonical_filters
from cfb_data.cache._coordinator import CacheCoordinator
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
    CFBDIdentityAmbiguityError,
    CFBDIdentityNotFoundError,
)
from cfb_data.games.models.pydantic.requests import GamesRequest
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.identities.models import (
    AthleteIdentity,
    ConferenceIdentity,
    FreshnessMode,
    GameIdentity,
    HydrationPlan,
    TeamIdentity,
    VenueIdentity,
)
from cfb_data.players.models.pydantic.requests import PlayerSearchRequest
from cfb_data.players.models.pydantic.responses import PlayerSearchResult
from cfb_data.plays.models.pydantic.responses import PlayStatType, PlayType
from cfb_data.teams.models.pydantic.requests import (
    FBSTeamsRequest,
    RosterRequest,
    TeamsRequest,
)
from cfb_data.teams.models.pydantic.responses import RosterPlayer, Team
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
_CATEGORY_VALUES = TypeAdapter(list[str])
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
        strict = freshness is FreshnessMode.local_only
        matches = await _team_matches(self._coordinator, query, strict=strict)
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Team", matches)
        if await self._coordinator.has_fresh_coverage(
            endpoint="/teams",
            canonical_filters="",
            capability="team.core_identity",
        ):
            return _one("Team", matches)
        try:
            rows = await self._executor.fetch_many(
                endpoint="/teams", request=TeamsRequest(), response_adapter=_TEAM_ROWS
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=team")
                return _one("Team", matches)
            raise
        matches = await _team_matches(self._coordinator, query, strict=False)
        if not matches:
            matches = _teams_from_rows(rows, query)
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
        strict = freshness is FreshnessMode.local_only
        matches = await _conference_matches(self._coordinator, query, strict=strict)
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Conference", matches)
        if await self._coordinator.has_fresh_coverage(
            endpoint="/conferences",
            canonical_filters="",
            capability="conference.identity",
        ):
            return _one("Conference", matches)
        try:
            rows = await self._executor.fetch_many(
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
        if not matches:
            matches = _conferences_from_rows(rows, query)
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
        strict = freshness is FreshnessMode.local_only
        matches = await _venue_matches(self._coordinator, query, strict=strict)
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Venue", matches)
        if await self._coordinator.has_fresh_coverage(
            endpoint="/venues",
            canonical_filters="",
            capability="venue.identity",
        ):
            return _one("Venue", matches)
        try:
            rows = await self._executor.fetch_many(
                endpoint="/venues", request=_EMPTY_REQUEST, response_adapter=_VENUE_ROWS
            )
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=venue")
                return _one("Venue", matches)
            raise
        matches = await _venue_matches(self._coordinator, query, strict=False)
        if not matches:
            matches = _venues_from_rows(rows, query)
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
        strict = freshness is FreshnessMode.local_only
        match = await self._coordinator.find_game(game_id, strict=strict)
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Game", [match] if match is not None else [])
        filters = canonical_filters({"id": game_id})
        broad_fresh = False
        if match is not None and match.season is not None:
            broad_fresh = await self._coordinator.has_fresh_coverage(
                endpoint="/games",
                canonical_filters=canonical_filters({"year": match.season}),
                capability="game.identity",
            )
        exact_fresh = await self._coordinator.has_fresh_coverage(
            endpoint="/games",
            canonical_filters=filters,
            capability="game.identity",
        )
        if broad_fresh or exact_fresh:
            return _one("Game", [match] if match is not None else [])
        try:
            rows = await self._executor.fetch_many(
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
        if match is None:
            converted = [_game_from_row(row) for row in rows if row.id == game_id]
            return _one("Game", converted)
        return match

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
        strict = freshness is FreshnessMode.local_only
        matches = await self._coordinator.find_games(
            season=season, week=week, team=team, strict=strict
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return matches
        if await self._coordinator.has_fresh_coverage(
            endpoint="/games",
            canonical_filters=filters,
            capability="game.identity",
        ):
            return matches
        try:
            rows = await self._executor.fetch_many(
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
        return matches or [_game_from_row(row) for row in rows]


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
        strict = freshness is FreshnessMode.local_only
        matches = await self._coordinator.find_athletes(
            name=name, team=team, season=season, strict=strict
        )
        if freshness is not FreshnessMode.ensure_fresh:
            return _one("Athlete", matches)

        if season is not None:
            request: BaseModel = RosterRequest(year=season, team=team)
            endpoint = "/roster"
            capability = "athlete.identity"
        else:
            request = PlayerSearchRequest(search_term=name, team=team)
            endpoint = "/player/search"
            capability = "athlete.identity"
        filters = canonical_filters(_serialize_request(endpoint, request))
        if await self._coordinator.has_fresh_coverage(
            endpoint=endpoint,
            canonical_filters=filters,
            capability=capability,
        ):
            return _one("Athlete", matches)

        try:
            if isinstance(request, RosterRequest):
                roster_rows = await self._executor.fetch_many(
                    endpoint=endpoint, request=request, response_adapter=_ROSTER_ROWS
                )
                in_memory = _athletes_from_roster(roster_rows, name, team, season)
            else:
                search_rows = await self._executor.fetch_many(
                    endpoint=endpoint,
                    request=request,
                    response_adapter=_PLAYER_SEARCH_ROWS,
                )
                in_memory = _athletes_from_search(search_rows, name, team, season)
        except Exception as exc:
            if matches and self._coordinator.allows_identity_stale(exc):
                _LOGGER.warning("CFBD identity stale-if-error namespace=athlete")
                return _one("Athlete", matches)
            raise
        matches = await self._coordinator.find_athletes(
            name=name, team=team, season=season
        )
        return _one("Athlete", matches or in_memory)


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
                "/teams/fbs",
                FBSTeamsRequest(),
                _TEAM_ROWS,
                "team.core_identity",
            )
            if classification is Classification.fbs
            else self._many_call(
                "/teams", TeamsRequest(), _TEAM_ROWS, "team.core_identity"
            )
        )
        calls = [
            team_call,
            self._many_call("/venues", _EMPTY_REQUEST, _VENUE_ROWS, "venue.identity"),
            self._many_call(
                "/conferences",
                ConferencesRequest(classification=conference_classification),
                _CONFERENCE_ROWS,
                "conference.identity",
            ),
            self._many_call(
                "/conferences/affiliations",
                ConferenceAffiliationsRequest(classification=conference_classification),
                _AFFILIATION_ROWS,
                "team.conference_history",
            ),
        ]
        for season in seasons:
            calls.extend(
                [
                    self._many_call(
                        "/games",
                        GamesRequest(
                            year=season,
                            classification=classification,
                        ),
                        _GAME_ROWS,
                        "game.identity",
                    ),
                    self._many_call(
                        "/roster",
                        RosterRequest(
                            year=season,
                            classification=classification,
                        ),
                        _ROSTER_ROWS,
                        "athlete.identity",
                    ),
                ]
            )
        if include_vocabularies:
            calls.extend(
                [
                    self._many_call(
                        "/plays/types",
                        _EMPTY_REQUEST,
                        _PLAY_TYPE_ROWS,
                        "play_type.identity",
                    ),
                    self._many_call(
                        "/plays/stats/types",
                        _EMPTY_REQUEST,
                        _PLAY_STAT_TYPE_ROWS,
                        "play_stat_type.identity",
                    ),
                    self._values_call(
                        "/stats/categories",
                        _EMPTY_REQUEST,
                        _CATEGORY_VALUES,
                        "stat_category.identity",
                    ),
                ]
            )
        return calls

    def _many_call[RowT: BaseModel](
        self,
        endpoint: str,
        request: BaseModel,
        adapter: TypeAdapter[list[RowT]],
        capability: str,
    ) -> _HydrationCall:
        """Build one typed model-list hydration operation."""

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
        endpoint: str,
        request: BaseModel,
        adapter: TypeAdapter[list[ValueT]],
        capability: str,
    ) -> _HydrationCall:
        """Build one typed scalar-list hydration operation."""

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


async def _team_matches(
    coordinator: CacheCoordinator, query: str | int, *, strict: bool
) -> list[TeamIdentity]:
    """Apply provider-ID precedence before normalized team-name matching."""
    if isinstance(query, str) and query.strip().isdigit():
        by_id = await coordinator.find_teams(int(query.strip()), strict=strict)
        if by_id:
            return by_id
    return await coordinator.find_teams(query, strict=strict)


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


def _normalize(value: str) -> str:
    """Apply exact Unicode, case, trim, and whitespace normalization."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _query_matches(query: str | int, identifier: int, *names: str | None) -> bool:
    """Match provider ID first, then normalized exact identity strings."""
    if isinstance(query, int):
        return query == identifier
    stripped = query.strip()
    if stripped.isdigit() and int(stripped) == identifier:
        return True
    normalized = _normalize(query)
    return any(name is not None and _normalize(name) == normalized for name in names)


def _teams_from_rows(rows: Sequence[Team], query: str | int) -> list[TeamIdentity]:
    """Return exact compact team matches from validated in-memory rows."""
    return [
        TeamIdentity(
            id=row.id,
            school=row.school,
            abbreviation=row.abbreviation,
            alternate_names=tuple(row.alternate_names or ()),
        )
        for row in rows
        if _query_matches(
            query,
            row.id,
            row.school,
            row.abbreviation,
            *(row.alternate_names or ()),
        )
    ]


def _conferences_from_rows(
    rows: Sequence[Conference], query: str | int
) -> list[ConferenceIdentity]:
    """Return exact compact conference matches from validated rows."""
    return [
        ConferenceIdentity(
            id=row.id,
            name=row.name,
            abbreviation=row.abbreviation,
            classification=str(row.classification) if row.classification else None,
        )
        for row in rows
        if _query_matches(query, row.id, row.name, row.abbreviation)
    ]


def _venues_from_rows(rows: Sequence[Venue], query: str | int) -> list[VenueIdentity]:
    """Return exact compact venue matches from validated in-memory rows."""
    return [
        VenueIdentity(id=row.id, name=row.name, city=row.city, state=row.state)
        for row in rows
        if row.id is not None
        and row.id > 0
        and row.name is not None
        and _query_matches(query, row.id, row.name)
    ]


def _game_from_row(row: Game) -> GameIdentity:
    """Return one compact game identity from a validated endpoint row."""
    return GameIdentity(
        id=row.id,
        season=row.season,
        week=row.week,
        season_type=str(row.season_type),
        start_date=row.start_date,
        status="completed" if row.completed else "scheduled",
        home_team_id=row.home_id,
        away_team_id=row.away_id,
        venue_id=row.venue_id,
    )


def _athletes_from_roster(
    rows: Sequence[RosterPlayer],
    name: str,
    team: str | None,
    season: int | None,
) -> list[AthleteIdentity]:
    """Return exact compact athlete matches from validated roster rows."""
    normalized = _normalize(name)
    return [
        AthleteIdentity(
            id=row.id,
            name=f"{row.first_name} {row.last_name}".strip(),
            position=row.position,
            team=row.team,
            season=season,
        )
        for row in rows
        if _normalize(f"{row.first_name} {row.last_name}") == normalized
        and (team is None or _normalize(row.team) == _normalize(team))
    ]


def _athletes_from_search(
    rows: Sequence[PlayerSearchResult],
    name: str,
    team: str | None,
    season: int | None,
) -> list[AthleteIdentity]:
    """Return exact compact athlete matches from validated search rows."""
    normalized = _normalize(name)
    return [
        AthleteIdentity(
            id=row.id,
            name=row.name,
            position=row.position,
            team=row.team,
            season=season,
        )
        for row in rows
        if _normalize(row.name) == normalized
        and (team is None or _normalize(row.team) == _normalize(team))
    ]
