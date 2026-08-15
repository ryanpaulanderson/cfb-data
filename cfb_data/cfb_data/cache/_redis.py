"""Persist validated responses and normalized identity facts in Redis."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import unicodedata
from collections.abc import Awaitable, Iterable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self, cast

from redis.asyncio import Redis

from cfb_data._catalog.merge import merge_catalog_observations
from cfb_data._catalog.models import (
    AthleteFact,
    CatalogCounts,
    CatalogFact,
    CatalogObservation,
    CatalogProjection,
    CoachFact,
    CoachTeamSeasonFact,
    ConferenceFact,
    CoverageRecord,
    DriveFact,
    GameFact,
    ObservationState,
    PlayFact,
    PlayoffMatchupFact,
    TeamFact,
    TeamSeasonFact,
    VenueFact,
    VocabularyFact,
)
from cfb_data._catalog.sources import projection_contract
from cfb_data.base.types import JSONValue, json_object
from cfb_data.cache._catalog_codecs import (
    decode_catalog_observation,
    encode_catalog_observation,
    observation_storage_key,
    projection_from_observations,
    projection_observations,
)
from cfb_data.cache._identity_codecs import (
    athlete_identity,
    conference_identity,
    game_identity,
    team_identity,
    venue_identity,
)
from cfb_data.cache._models import MAX_RESPONSE_BODY_BYTES, ResponseRecord
from cfb_data.cache.config import RedisCacheConfig
from cfb_data.errors import CFBDCacheBackendError, CFBDClientStateError

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity

_RECORD_VERSION = 1
_SCHEMA_VERSION = 1
_MAX_CATALOG_COMMIT_TIMEOUT_SECONDS = 30.0
_MAX_ENCODED_RESPONSE_BYTES = (MAX_RESPONSE_BODY_BYTES * 4 // 3) + 64 * 1024
_FACT_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "athlete": ("id",),
    "athlete-membership": ("athlete_id", "team_name", "season"),
    "recruit": ("id",),
    "coach": ("id",),
    "coach-team-season": ("coach_id", "team_id", "start_year"),
    "drive": ("id",),
    "play": ("id",),
    "vocabulary": ("namespace", "id"),
    "playoff-matchup": ("id",),
}
_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisCacheBackend:
    """Own one pooled Redis client for shared cache and catalog operations."""

    def __init__(self, config: RedisCacheConfig) -> None:
        """Initialize configuration without opening a connection pool."""
        self._config = config
        self._redis: Redis | None = None
        self._namespace = f"{config.key_prefix}:v1"

    async def open(self) -> Self:
        """Open and verify the configured Redis deployment."""
        if self._redis is not None:
            raise CFBDClientStateError("Redis cache backend is already open")
        client = Redis.from_url(
            self._config.url,
            decode_responses=False,
            socket_connect_timeout=self._config.io_timeout_seconds,
            socket_timeout=max(
                self._config.io_timeout_seconds,
                _MAX_CATALOG_COMMIT_TIMEOUT_SECONDS,
            ),
        )
        try:
            await _redis_result(client.ping())
            schema_key = self._key("meta", "schema-version")
            current = await client.get(schema_key)
            if current is None:
                await client.set(schema_key, str(_SCHEMA_VERSION).encode(), nx=True)
                current = await client.get(schema_key)
            if _text(current) != str(_SCHEMA_VERSION):
                raise CFBDCacheBackendError(
                    "Redis cache schema version is incompatible"
                )
        except Exception:
            await client.aclose()
            raise
        self._redis = client
        return self

    async def close(self) -> None:
        """Close the owned Redis client and connection pool."""
        client = self._active_client()
        self._redis = None
        await client.aclose()

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return one retained response, relying on native Redis expiry."""
        client = self._active_client()
        response_key = self._response_key(key)
        encoded_size = _integer(await _redis_result(client.strlen(response_key)))
        if encoded_size > _MAX_ENCODED_RESPONSE_BYTES:
            await client.delete(response_key)
            raise CFBDCacheBackendError("Redis response record is oversized")
        raw = await client.get(response_key)
        if raw is None:
            return None
        try:
            record = _decode_response(_bytes(raw))
        except CFBDCacheBackendError:
            await client.delete(response_key)
            raise
        if record.retained_until <= now:
            await self.delete_response(key)
            return None
        return record

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> CatalogProjection:
        """Atomically store response, projected facts, indexes, and coverage."""
        client = self._active_client()
        ttl_seconds = max(
            1,
            math.ceil((record.retained_until - datetime.now(UTC)).total_seconds()),
        )
        observed_at = record.fetched_at.isoformat()
        lock = client.lock(
            self._key("lock", "catalog-commit"),
            timeout=_MAX_CATALOG_COMMIT_TIMEOUT_SECONDS,
            blocking_timeout=self._config.io_timeout_seconds,
        )
        try:
            async with lock:
                (
                    projection,
                    encoded_observations,
                    stale_indexes,
                ) = await self._merge_projection(
                    client,
                    projection,
                    observed_at=record.fetched_at,
                    source=record.endpoint,
                )
                (
                    athlete_indexes,
                    removed_athlete_indexes,
                    membership_indexes,
                ) = await self._merge_compact_indexes(
                    client,
                    projection,
                    stale_indexes=stale_indexes,
                )
                async with client.pipeline(transaction=True) as pipeline:
                    pipeline.set(
                        self._response_key(record.key),
                        _encode_response(record),
                        ex=ttl_seconds,
                    )
                    self._project_teams(pipeline, projection, observed_at)
                    self._project_conferences(pipeline, projection, observed_at)
                    self._project_venues(pipeline, projection, observed_at)
                    self._project_games(pipeline, projection, observed_at)
                    self._project_athletes(pipeline, projection, observed_at)
                    self._project_remaining(pipeline, projection, observed_at)
                    self._delete_observed_nulls(pipeline, projection)
                    for namespace, normalized, identifier in stale_indexes:
                        if namespace == "athlete":
                            continue
                        pipeline.srem(
                            self._index_key(namespace, normalized), identifier
                        )
                    if athlete_indexes:
                        pipeline.hset(
                            self._compact_index_key("athlete"),
                            mapping=athlete_indexes,
                        )
                    if removed_athlete_indexes:
                        pipeline.hdel(
                            self._compact_index_key("athlete"),
                            *removed_athlete_indexes,
                        )
                    if membership_indexes:
                        pipeline.hset(
                            self._compact_index_key("athlete-membership"),
                            mapping=membership_indexes,
                        )
                    if encoded_observations:
                        pipeline.hset(
                            self._observation_hash_key(),
                            mapping=dict(encoded_observations),
                        )
                    if projection.coverage is not None:
                        self._project_coverage(pipeline, projection.coverage)
                    await pipeline.execute()
                return projection
        except TimeoutError as exc:
            raise CFBDCacheBackendError("Redis catalog commit lock timed out") from exc

    async def merge_catalog_projection(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> CatalogProjection:
        """Merge a projection with durable observations without writing it."""
        merged, _, _ = await self._merge_projection(
            self._active_client(),
            projection,
            observed_at=record.fetched_at,
            source=record.endpoint,
        )
        return merged

    async def delete_response(self, key: str) -> None:
        """Delete one invalid response record without catalog pruning."""
        await self._active_client().delete(self._response_key(key))

    async def cleanup_responses(self, now: datetime) -> int:
        """Return zero because Redis expires response keys natively."""
        return 0

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Return whether complete fresh coverage proves one capability."""
        identity = _digest(f"{endpoint}:{canonical_filters}")
        raw = await self._active_client().get(self._key("coverage", identity))
        if raw is None:
            return False
        record = json_object(json.loads(_bytes(raw)))
        status = _json_required_text(record, "status")
        fresh_until = datetime.fromisoformat(_json_required_text(record, "fresh_until"))
        capabilities = record.get("capabilities")
        stored_contract = _json_required_text(record, "projection_contract")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) for item in capabilities
        ):
            raise CFBDCacheBackendError("Redis coverage capabilities are corrupt")
        return (
            status == "complete"
            and fresh_until > now
            and capability in capabilities
            and stored_contract == projection_contract(endpoint)
        )

    async def record_coverage_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
        failed_at: datetime,
    ) -> None:
        """Record the latest failure for one canonical hydration partition."""
        partition_key = f"{endpoint}:{canonical_filters}"
        payload: dict[str, JSONValue] = {
            "partition_key": partition_key,
            "endpoint": endpoint,
            "canonical_filters": canonical_filters,
            "failure_category": failure_category,
            "failed_at": failed_at.isoformat(),
        }
        await self._active_client().set(
            self._coverage_failure_key(partition_key),
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Acquire one lease with atomic ``SET NX PX`` semantics."""
        ttl_ms = max(1, math.ceil((expires_at - now).total_seconds() * 1000))
        result = await self._active_client().set(
            self._lease_key(key), owner_token.encode(), nx=True, px=ttl_ms
        )
        return result is True

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a lease through a token-comparing server-side operation."""
        ttl_ms = max(
            1,
            math.ceil((expires_at - datetime.now(UTC)).total_seconds() * 1000),
        )
        result = await _redis_result(
            self._active_client().eval(
                _RENEW_SCRIPT, 1, self._lease_key(key), owner_token, ttl_ms
            )
        )
        return _integer(result) == 1

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a lease through a token-comparing server-side operation."""
        result = await _redis_result(
            self._active_client().eval(
                _RELEASE_SCRIPT, 1, self._lease_key(key), owner_token
            )
        )
        return _integer(result) == 1

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return exact provider-ID, school, abbreviation, or alias matches."""
        if isinstance(query, int):
            ids = {str(query)}
            normalized_query = None
        else:
            normalized_query = _normalize(query)
            ids = await self._index_members("team", normalized_query)
        records = await self._hash_records("team", ids)
        identities = [
            team_identity(
                id=_required_int(record, "id"),
                school=_required_text(record, "school"),
                abbreviation=_optional_text(record, "abbreviation"),
                alternate_names=tuple(
                    _string_list(record.get(b"alternate_names", b"[]"))
                ),
            )
            for record in records
        ]
        if normalized_query is None:
            return identities
        return [
            identity
            for identity in identities
            if _matches_normalized(
                normalized_query,
                identity.school,
                identity.abbreviation,
                *identity.alternate_names,
            )
        ]

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact provider-ID, name, or abbreviation matches."""
        if isinstance(query, int):
            ids = {str(query)}
            normalized_query = None
        else:
            normalized_query = _normalize(query)
            ids = await self._index_members("conference", normalized_query)
        records = await self._hash_records("conference", ids)
        identities = [
            conference_identity(
                id=_required_int(record, "id"),
                name=_required_text(record, "name"),
                abbreviation=_optional_text(record, "abbreviation"),
                classification=_optional_text(record, "classification"),
            )
            for record in records
        ]
        if normalized_query is None:
            return identities
        return [
            identity
            for identity in identities
            if _matches_normalized(
                normalized_query, identity.name, identity.abbreviation
            )
        ]

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact provider-ID or name matches."""
        if isinstance(query, int):
            ids = {str(query)}
            normalized_query = None
        else:
            normalized_query = _normalize(query)
            ids = await self._index_members("venue", normalized_query)
        records = await self._hash_records("venue", ids)
        identities = [
            venue_identity(
                id=_required_int(record, "id"),
                name=_required_text(record, "name"),
                city=_optional_text(record, "city"),
                state=_optional_text(record, "state"),
            )
            for record in records
        ]
        if normalized_query is None:
            return identities
        return [
            identity
            for identity in identities
            if _matches_normalized(normalized_query, identity.name)
        ]

    async def find_game(self, game_id: int) -> GameIdentity | None:
        """Return one compact game identity by provider ID."""
        record = await _redis_result(
            self._active_client().hgetall(self._entity_key("game", game_id))
        )
        if not record:
            return None
        return _game_from_hash(_byte_mapping(record))

    async def find_games(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return games in one season partition with optional exact filters."""
        raw_ids = await _redis_result(
            self._active_client().smembers(self._key("idx", "game-season", str(season)))
        )
        records = await self._hash_records("game", {_text(item) for item in raw_ids})
        team_ids: set[int] | None = None
        if team is not None:
            team_ids = {item.id for item in await self.find_teams(team)}
        games = [_game_from_hash(record) for record in records]
        return sorted(
            (
                game
                for game in games
                if (week is None or game.week == week)
                and (
                    team_ids is None
                    or game.home_team_id in team_ids
                    or game.away_team_id in team_ids
                )
            ),
            key=lambda game: (
                game.start_date or datetime.min.replace(tzinfo=UTC),
                game.id,
            ),
        )

    async def find_athletes(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return exact athlete matches within optional team-season scope."""
        normalized_name = _normalize(name)
        athlete_ids = await self._index_members("athlete", normalized_name)
        records = await self._hash_records("athlete", athlete_ids)
        results: list[AthleteIdentity] = []
        for record in records:
            athlete_name = _required_text(record, "name")
            if not _matches_normalized(normalized_name, athlete_name):
                continue
            athlete_id = _required_text(record, "id")
            raw_membership_fields = await _redis_result(
                self._active_client().hget(
                    self._compact_index_key("athlete-membership"),
                    _digest(athlete_id),
                )
            )
            membership_fields = set(_stored_string_list(raw_membership_fields))
            memberships = await self._compact_json_records(
                "athlete-membership", membership_fields
            )
            matching = [
                membership
                for membership in memberships
                if (
                    team is None
                    or _normalize(_json_required_text(membership, "team"))
                    == _normalize(team)
                )
                and (
                    season is None or _json_required_int(membership, "season") == season
                )
            ]
            if (team is not None or season is not None) and not matching:
                continue
            if not matching:
                results.append(
                    athlete_identity(
                        id=athlete_id,
                        name=athlete_name,
                        position=_optional_text(record, "position"),
                    )
                )
            else:
                results.extend(
                    athlete_identity(
                        id=athlete_id,
                        name=athlete_name,
                        position=_optional_text(record, "position"),
                        team=_json_required_text(membership, "team"),
                        season=_json_required_int(membership, "season"),
                    )
                    for membership in matching
                )
        return results

    async def catalog_counts(self) -> CatalogCounts:
        """Return row counts for every explicit Redis catalog namespace."""
        namespaces = (
            "team",
            "team-season",
            "conference",
            "affiliation",
            "venue",
            "game",
            "athlete",
            "athlete-membership",
            "recruit",
            "coach",
            "coach-team-season",
            "drive",
            "play",
            "vocabulary",
            "playoff-matchup",
        )
        client = self._active_client()
        counts: list[int] = []
        for namespace in namespaces:
            if namespace in {"athlete", "athlete-membership", "recruit"}:
                counts.append(
                    _integer(
                        await _redis_result(
                            client.hlen(self._compact_catalog_key(namespace))
                        )
                    )
                )
                continue
            count = 0
            async for _ in client.scan_iter(
                match=self._key("catalog", namespace, "*"), count=250
            ):
                count += 1
            counts.append(count)
        return CatalogCounts(*counts)

    async def _merge_projection(
        self,
        client: Redis,
        projection: CatalogProjection,
        *,
        observed_at: datetime,
        source: str,
    ) -> tuple[
        CatalogProjection,
        tuple[tuple[str, bytes], ...],
        tuple[tuple[str, str, str], ...],
    ]:
        """Merge canonical observations while holding the Redis commit lock."""
        candidates = projection_observations(
            projection, observed_at=observed_at, source=source
        )
        if not candidates:
            return projection, (), ()
        storage_fields = tuple(self._observation_field(item) for item in candidates)
        stored = await _redis_result(
            client.hmget(self._observation_hash_key(), list(storage_fields))
        )
        merged: list[CatalogObservation] = []
        encoded: list[tuple[str, bytes]] = []
        stale_indexes: list[tuple[str, str, str]] = []
        for candidate, field, raw in zip(
            candidates, storage_fields, stored, strict=True
        ):
            current = None if raw is None else decode_catalog_observation(_bytes(raw))
            selected = merge_catalog_observations(current, candidate)
            if current is not None:
                stale_indexes.extend(_stale_index_members(current, selected))
            merged.append(selected)
            encoded.append((field, encode_catalog_observation(selected).encode()))
        return (
            projection_from_observations(tuple(merged), original=projection),
            tuple(encoded),
            tuple(stale_indexes),
        )

    async def _merge_compact_indexes(
        self,
        client: Redis,
        projection: CatalogProjection,
        *,
        stale_indexes: tuple[tuple[str, str, str], ...],
    ) -> tuple[dict[str, bytes], tuple[str, ...], dict[str, bytes]]:
        """Merge high-cardinality athlete indexes into three bounded commands."""
        athlete_additions: dict[str, set[str]] = {}
        for fact in projection.athletes:
            athlete_additions.setdefault(_normalize(fact.name), set()).add(fact.id)
        athlete_removals: dict[str, set[str]] = {}
        for namespace, normalized, identifier in stale_indexes:
            if namespace == "athlete":
                athlete_removals.setdefault(normalized, set()).add(identifier)
        names = tuple(sorted(athlete_additions.keys() | athlete_removals.keys()))
        name_fields = [_digest(name) for name in names]
        stored_names = (
            await _redis_result(
                client.hmget(self._compact_index_key("athlete"), name_fields)
            )
            if name_fields
            else []
        )
        athlete_updates: dict[str, bytes] = {}
        athlete_deletes: list[str] = []
        for name, field, raw in zip(names, name_fields, stored_names, strict=True):
            members = set(_stored_string_list(raw))
            members.difference_update(athlete_removals.get(name, set()))
            members.update(athlete_additions.get(name, set()))
            if members:
                athlete_updates[field] = _encode_string_list(members)
            else:
                athlete_deletes.append(field)

        membership_additions: dict[str, set[str]] = {}
        for membership_fact in projection.athlete_team_seasons:
            payload = _dataclass_json(membership_fact)
            membership_additions.setdefault(membership_fact.athlete_id, set()).add(
                _fact_identity("athlete-membership", payload)
            )
        athlete_fields = [_digest(athlete_id) for athlete_id in membership_additions]
        stored_memberships = (
            await _redis_result(
                client.hmget(
                    self._compact_index_key("athlete-membership"),
                    athlete_fields,
                )
            )
            if athlete_fields
            else []
        )
        membership_updates: dict[str, bytes] = {}
        for athlete_id, field, raw in zip(
            membership_additions,
            athlete_fields,
            stored_memberships,
            strict=True,
        ):
            members = set(_stored_string_list(raw))
            members.update(membership_additions[athlete_id])
            membership_updates[field] = _encode_string_list(members)
        return athlete_updates, tuple(athlete_deletes), membership_updates

    def _delete_observed_nulls(
        self, pipeline: object, projection: CatalogProjection
    ) -> None:
        """Queue hash deletions for authoritative canonical null observations."""
        pipe = cast(Redis, pipeline)
        for observation in projection.observations:
            key = self._hash_fact_key(observation)
            if key is None:
                continue
            null_fields = [
                field.field
                for field in observation.fields
                if field.value.state is ObservationState.null
            ]
            if null_fields:
                pipe.hdel(key, *null_fields)

    def _hash_fact_key(self, observation: CatalogObservation) -> str | None:
        """Return the explicit Redis hash key for one hash-backed fact."""
        fact = observation.fact
        if isinstance(fact, TeamFact):
            return self._entity_key("team", fact.id)
        if isinstance(fact, TeamSeasonFact):
            return self._key(
                "catalog",
                "team-season",
                str(fact.team_id),
                str(fact.season),
            )
        if isinstance(fact, ConferenceFact):
            return self._entity_key("conference", fact.id)
        if isinstance(fact, VenueFact):
            return self._entity_key("venue", fact.id)
        if isinstance(fact, GameFact):
            return self._entity_key("game", fact.id)
        namespaces: tuple[tuple[type[object], str], ...] = (
            (CoachFact, "coach"),
            (CoachTeamSeasonFact, "coach-team-season"),
            (DriveFact, "drive"),
            (PlayFact, "play"),
            (VocabularyFact, "vocabulary"),
            (PlayoffMatchupFact, "playoff-matchup"),
        )
        for fact_type, namespace in namespaces:
            if isinstance(fact, fact_type):
                payload = _dataclass_json(fact)
                return self._key(
                    "catalog", namespace, _fact_identity(namespace, payload)
                )
        return None

    def _observation_field(self, observation: CatalogObservation) -> str:
        """Return the opaque provenance-hash field for one fact grain."""
        namespace, grain = observation_storage_key(observation)
        return _digest(f"{namespace}:{grain}")

    def _observation_hash_key(self) -> str:
        """Return the permanent shared hash for canonical merge provenance."""
        return self._key("catalog-observations")

    def _project_teams(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue team facts and exact-match indexes in one transaction."""
        pipe = cast(Redis, pipeline)
        for team_fact in projection.teams:
            key = self._entity_key("team", team_fact.id)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "id": str(team_fact.id),
                        "school": team_fact.school,
                        "abbreviation": team_fact.abbreviation,
                        "alternate_names": (
                            json.dumps(team_fact.alternate_names)
                            if team_fact.alternate_names is not None
                            else None
                        ),
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            names = [team_fact.school, *(team_fact.alternate_names or ())]
            if team_fact.abbreviation is not None:
                names.append(team_fact.abbreviation)
            for name in names:
                pipe.sadd(self._index_key("team", _normalize(name)), str(team_fact.id))
        for season_fact in projection.team_seasons:
            key = self._key(
                "catalog",
                "team-season",
                str(season_fact.team_id),
                str(season_fact.season),
            )
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "team_id": str(season_fact.team_id),
                        "season": str(season_fact.season),
                        "conference_name": season_fact.conference_name,
                        "venue_id": str(season_fact.venue_id)
                        if season_fact.venue_id is not None
                        else None,
                        "last_seen_at": observed_at,
                    }
                ),
            )

    def _project_conferences(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue conference identities and affiliation intervals."""
        pipe = cast(Redis, pipeline)
        for conference_fact in projection.conferences:
            key = self._entity_key("conference", conference_fact.id)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "id": str(conference_fact.id),
                        "name": conference_fact.name,
                        "abbreviation": conference_fact.abbreviation,
                        "classification": conference_fact.classification,
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            for name in (conference_fact.name, conference_fact.abbreviation):
                if name:
                    pipe.sadd(
                        self._index_key("conference", _normalize(name)),
                        str(conference_fact.id),
                    )
        for affiliation_fact in projection.affiliations:
            self._queue_json(
                pipe,
                self._key(
                    "catalog",
                    "affiliation",
                    str(affiliation_fact.team_id),
                    str(affiliation_fact.conference_id),
                    str(affiliation_fact.start_year),
                ),
                {
                    "team_id": affiliation_fact.team_id,
                    "conference_id": affiliation_fact.conference_id,
                    "start_year": affiliation_fact.start_year,
                    "end_year": affiliation_fact.end_year,
                    "last_seen_at": observed_at,
                },
            )

    def _project_venues(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue venue identities and exact-name indexes."""
        pipe = cast(Redis, pipeline)
        for fact in projection.venues:
            key = self._entity_key("venue", fact.id)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "id": str(fact.id),
                        "name": fact.name,
                        "city": fact.city,
                        "state": fact.state,
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            pipe.sadd(self._index_key("venue", _normalize(fact.name)), str(fact.id))

    def _project_games(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue game identities, relationships, and season indexes."""
        pipe = cast(Redis, pipeline)
        for fact in projection.games:
            key = self._entity_key("game", fact.id)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "id": str(fact.id),
                        "season": str(fact.season) if fact.season is not None else None,
                        "week": str(fact.week) if fact.week is not None else None,
                        "season_type": fact.season_type,
                        "start_date": fact.start_date.isoformat()
                        if fact.start_date
                        else None,
                        "status": fact.status,
                        "home_team_id": str(fact.home_team_id)
                        if fact.home_team_id is not None
                        else None,
                        "away_team_id": str(fact.away_team_id)
                        if fact.away_team_id is not None
                        else None,
                        "venue_id": str(fact.venue_id)
                        if fact.venue_id is not None
                        else None,
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            if fact.season is not None:
                pipe.sadd(
                    self._key("idx", "game-season", str(fact.season)), str(fact.id)
                )

    def _project_athletes(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue compact athlete identities and time-varying memberships."""
        pipe = cast(Redis, pipeline)
        athlete_payloads = _compact_fact_payloads(
            "athlete", projection.athletes, projection, observed_at
        )
        if athlete_payloads:
            pipe.hset(self._compact_catalog_key("athlete"), mapping=athlete_payloads)
        membership_payloads = _compact_fact_payloads(
            "athlete-membership",
            projection.athlete_team_seasons,
            projection,
            observed_at,
        )
        if membership_payloads:
            pipe.hset(
                self._compact_catalog_key("athlete-membership"),
                mapping=membership_payloads,
            )

    def _project_remaining(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue the remaining typed relationship and vocabulary schemas."""
        pipe = cast(Redis, pipeline)
        groups: tuple[tuple[str, Iterable[object]], ...] = (
            ("coach", projection.coaches),
            ("drive", projection.drives),
            ("play", projection.plays),
            ("vocabulary", projection.vocabularies),
            ("playoff-matchup", projection.playoff_matchups),
        )
        for namespace, facts in groups:
            for fact in facts:
                payload = _dataclass_json(fact)
                payload["last_seen_at"] = observed_at
                identity = _fact_identity(namespace, payload)
                key = self._key("catalog", namespace, identity)
                pipe.hsetnx(key, "first_seen_at", observed_at)
                payload["source_version"] = 1
                payload["schema_version"] = 1
                pipe.hset(
                    key,
                    mapping={
                        field: str(value)
                        for field, value in payload.items()
                        if value is not None
                    },
                )
        recruit_payloads = _compact_fact_payloads(
            "recruit", projection.recruits, projection, observed_at
        )
        if recruit_payloads:
            pipe.hset(self._compact_catalog_key("recruit"), mapping=recruit_payloads)
        self._project_coach_team_seasons(pipe, projection, observed_at)

    def _project_coach_team_seasons(
        self, pipe: Redis, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue fully merged coach relationships and optional-field clearing."""
        for fact in projection.coach_team_seasons:
            payload = _dataclass_json(fact)
            identity = _fact_identity("coach-team-season", payload)
            key = self._key("catalog", "coach-team-season", identity)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "coach_id": str(fact.coach_id),
                        "team_id": str(fact.team_id),
                        "start_year": str(fact.start_year),
                        "end_year": (
                            str(fact.end_year) if fact.end_year is not None else None
                        ),
                        "tenure_id": (
                            str(fact.tenure_id) if fact.tenure_id is not None else None
                        ),
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )

    def _project_coverage(self, pipeline: object, coverage: CoverageRecord) -> None:
        """Queue one permanent capability-aware coverage ledger record."""
        pipe = cast(Redis, pipeline)
        payload: dict[str, JSONValue] = {
            "partition_key": coverage.partition_key,
            "namespace": coverage.namespace,
            "canonical_filters": coverage.canonical_filters,
            "capabilities": list(coverage.capabilities),
            "status": str(coverage.status),
            "response_key": coverage.response_key,
            "endpoint": coverage.endpoint,
            "fetched_at": coverage.fetched_at.isoformat(),
            "validated_at": coverage.validated_at.isoformat(),
            "fresh_until": coverage.fresh_until.isoformat(),
            "retained_until": coverage.retained_until.isoformat(),
            "row_count": coverage.row_count,
            "known_cap": coverage.known_cap,
            "projection_contract": coverage.projection_contract,
            "api_version": "5.24.0",
            "cache_key_version": 1,
            "response_contract_version": 1,
            "projector_version": 1,
            "catalog_schema_version": 1,
        }
        self._queue_json(
            pipe,
            self._key("coverage", _digest(coverage.partition_key)),
            payload,
        )
        pipe.delete(self._coverage_failure_key(coverage.partition_key))

    async def _index_members(self, namespace: str, normalized: str) -> set[str]:
        """Return source identifiers from a hashed exact-match index."""
        if namespace == "athlete":
            raw = await _redis_result(
                self._active_client().hget(
                    self._compact_index_key(namespace), _digest(normalized)
                )
            )
            return set(_stored_string_list(raw))
        values = await _redis_result(
            self._active_client().smembers(self._index_key(namespace, normalized))
        )
        return {_text(value) for value in values}

    async def _hash_records(
        self, namespace: str, identifiers: set[str]
    ) -> list[dict[bytes, bytes]]:
        """Return existing typed hash records for opaque source identifiers."""
        if not identifiers:
            return []
        client = self._active_client()
        if namespace == "athlete":
            rows = await _redis_result(
                client.hmget(
                    self._compact_catalog_key(namespace),
                    [
                        _fact_identity("athlete", {"id": identifier})
                        for identifier in sorted(identifiers)
                    ],
                )
            )
            return [
                _json_byte_mapping(json_object(json.loads(_bytes(row))))
                for row in rows
                if row is not None
            ]
        async with client.pipeline(transaction=False) as pipeline:
            for identifier in sorted(identifiers):
                pipeline.hgetall(self._entity_key(namespace, identifier))
            rows = await pipeline.execute()
        return [
            _byte_mapping(row) for row in rows if isinstance(row, Mapping) and bool(row)
        ]

    async def _compact_json_records(
        self, namespace: str, identifiers: set[str]
    ) -> list[dict[str, JSONValue]]:
        """Return compact JSON fact records by their opaque hash fields."""
        if not identifiers:
            return []
        rows = await _redis_result(
            self._active_client().hmget(
                self._compact_catalog_key(namespace), sorted(identifiers)
            )
        )
        return [json_object(json.loads(_bytes(row))) for row in rows if row is not None]

    async def _json_records(
        self, identifiers: set[str], *, absolute: bool = False
    ) -> list[dict[str, JSONValue]]:
        """Return validated non-executable JSON records by key."""
        if not identifiers:
            return []
        client = self._active_client()
        async with client.pipeline(transaction=False) as pipeline:
            for identifier in sorted(identifiers):
                pipeline.get(identifier if absolute else self._key(identifier))
            rows = await pipeline.execute()
        records: list[dict[str, JSONValue]] = []
        for row in rows:
            if row is None:
                continue
            records.append(json_object(json.loads(_bytes(row))))
        return records

    def _queue_json(
        self, pipeline: Redis, key: str, payload: Mapping[str, JSONValue]
    ) -> None:
        """Queue one compact deterministic non-executable JSON value."""
        pipeline.set(
            key,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )

    def _response_key(self, digest: str) -> str:
        """Return one expiring response-record key."""
        return self._key("response", digest)

    def _lease_key(self, digest: str) -> str:
        """Return one temporary refresh-lease key."""
        return self._key("lease", digest)

    def _coverage_failure_key(self, partition_key: str) -> str:
        """Return one permanent hydration-failure ledger key."""
        return self._key("coverage-failure", _digest(partition_key))

    def _entity_key(self, namespace: str, identifier: int | str) -> str:
        """Return a permanent typed catalog entity key."""
        return self._key("catalog", namespace, _digest(str(identifier)))

    def _compact_catalog_key(self, namespace: str) -> str:
        """Return one explicit high-cardinality fact hash."""
        return self._key("catalog", namespace)

    def _compact_index_key(self, namespace: str) -> str:
        """Return one explicit high-cardinality exact-match index hash."""
        return self._key("idx", namespace)

    def _index_key(self, namespace: str, normalized: str) -> str:
        """Return a permanent hashed exact-match index key."""
        return self._key("idx", namespace, _digest(normalized))

    def _key(self, *parts: str) -> str:
        """Return one backend-owned versioned namespace key."""
        return ":".join((self._namespace, *parts))

    def _active_client(self) -> Redis:
        """Return the active Redis client or reject lifecycle misuse."""
        if self._redis is None:
            raise CFBDClientStateError("Cache access requires an active client context")
        return self._redis


def _encode_response(record: ResponseRecord) -> bytes:
    """Serialize one versioned response record without executable content."""
    payload: dict[str, JSONValue] = {
        "version": _RECORD_VERSION,
        "key": record.key,
        "endpoint": record.endpoint,
        "response_contract": record.response_contract,
        "body": base64.b64encode(record.body).decode("ascii"),
        "fetched_at": record.fetched_at.isoformat(),
        "fresh_until": record.fresh_until.isoformat(),
        "retained_until": record.retained_until.isoformat(),
        "etag": record.etag,
        "last_modified": record.last_modified,
        "row_count": record.row_count,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _decode_response(raw: bytes) -> ResponseRecord:
    """Decode and validate one untrusted versioned Redis response record."""
    try:
        payload = json_object(json.loads(raw))
        if _json_required_int(payload, "version") != _RECORD_VERSION:
            raise ValueError("unsupported record version")
        body = base64.b64decode(_json_required_text(payload, "body"), validate=True)
        if len(body) > MAX_RESPONSE_BODY_BYTES:
            raise ValueError("response body exceeds the storage contract")
        return ResponseRecord(
            key=_json_required_text(payload, "key"),
            endpoint=_json_required_text(payload, "endpoint"),
            response_contract=_json_required_text(payload, "response_contract"),
            body=body,
            fetched_at=datetime.fromisoformat(
                _json_required_text(payload, "fetched_at")
            ),
            fresh_until=datetime.fromisoformat(
                _json_required_text(payload, "fresh_until")
            ),
            retained_until=datetime.fromisoformat(
                _json_required_text(payload, "retained_until")
            ),
            etag=_json_optional_text(payload, "etag"),
            last_modified=_json_optional_text(payload, "last_modified"),
            row_count=_json_required_int(payload, "row_count"),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CFBDCacheBackendError("Redis response record is corrupt") from exc


def _game_from_hash(record: Mapping[bytes, bytes]) -> GameIdentity:
    """Build one compact validated game identity from a Redis hash."""
    start_date = _optional_text(record, "start_date")
    return game_identity(
        id=_required_int(record, "id"),
        season=_optional_int(record, "season"),
        week=_optional_int(record, "week"),
        season_type=_optional_text(record, "season_type"),
        start_date=datetime.fromisoformat(start_date) if start_date else None,
        status=_optional_text(record, "status"),
        home_team_id=_optional_int(record, "home_team_id"),
        away_team_id=_optional_int(record, "away_team_id"),
        venue_id=_optional_int(record, "venue_id"),
    )


def _stale_index_members(
    current: CatalogObservation, selected: CatalogObservation
) -> tuple[tuple[str, str, str], ...]:
    """Return exact-index memberships superseded by merged canonical values."""
    previous = _fact_index_identity(current)
    replacement = _fact_index_identity(selected)
    if previous is None or replacement is None or previous[:2] != replacement[:2]:
        return ()
    namespace, identifier, previous_names = previous
    replacement_names = replacement[2]
    return tuple(
        (namespace, normalized, identifier)
        for normalized in previous_names - replacement_names
    )


def _fact_index_identity(
    observation: CatalogObservation,
) -> tuple[str, str, frozenset[str]] | None:
    """Return the exact-match index identity carried by a public entity fact."""
    fact = observation.fact
    if isinstance(fact, TeamFact):
        names = frozenset(
            name
            for name in (
                fact.school,
                fact.abbreviation,
                *(fact.alternate_names or ()),
            )
            if name
        )
        return "team", str(fact.id), frozenset(_normalize(name) for name in names)
    if isinstance(fact, ConferenceFact):
        return (
            "conference",
            str(fact.id),
            frozenset(
                _normalize(name) for name in (fact.name, fact.abbreviation) if name
            ),
        )
    if isinstance(fact, VenueFact):
        return "venue", str(fact.id), frozenset((_normalize(fact.name),))
    if isinstance(fact, AthleteFact):
        return "athlete", fact.id, frozenset((_normalize(fact.name),))
    return None


def _normalize(value: str) -> str:
    """Apply exact Unicode, case, trim, and whitespace normalization."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(value: str) -> str:
    """Return a key-safe digest so source and query values stay out of Redis keys."""
    return hashlib.sha256(value.encode()).hexdigest()


def _without_none(values: Mapping[str, str | None]) -> dict[str, str]:
    """Return Redis hash fields with absent optional values omitted."""
    return {key: value for key, value in values.items() if value is not None}


def _bytes(value: object) -> bytes:
    """Narrow a Redis protocol response to bytes."""
    if isinstance(value, bytes):
        return value
    raise CFBDCacheBackendError("Redis record has an unexpected value type")


def _text(value: object) -> str:
    """Decode one UTF-8 Redis protocol value."""
    try:
        return _bytes(value).decode()
    except UnicodeDecodeError as exc:
        raise CFBDCacheBackendError("Redis record contains invalid UTF-8") from exc


def _integer(value: object) -> int:
    """Narrow one Redis integer protocol response."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise CFBDCacheBackendError("Redis operation returned an unexpected value")


async def _redis_result[ResultT](
    value: Awaitable[ResultT] | ResultT,
) -> ResultT:
    """Await an async Redis result despite the package's sync/async union types."""
    if isinstance(value, Awaitable):
        return await value
    return value


def _byte_mapping(value: object) -> dict[bytes, bytes]:
    """Narrow one Redis hash response to byte keys and values."""
    if not isinstance(value, Mapping):
        raise CFBDCacheBackendError("Redis hash has an unexpected value type")
    result: dict[bytes, bytes] = {}
    for key, item in value.items():
        result[_bytes(key)] = _bytes(item)
    return result


def _required_text(record: Mapping[bytes, bytes], name: str) -> str:
    """Return one required UTF-8 hash field."""
    value = record.get(name.encode())
    if value is None:
        raise CFBDCacheBackendError("Redis catalog record is missing a field")
    return _text(value)


def _optional_text(record: Mapping[bytes, bytes], name: str) -> str | None:
    """Return one optional UTF-8 hash field."""
    value = record.get(name.encode())
    return _text(value) if value is not None else None


def _required_int(record: Mapping[bytes, bytes], name: str) -> int:
    """Return one required integer hash field."""
    try:
        return int(_required_text(record, name))
    except ValueError as exc:
        raise CFBDCacheBackendError("Redis catalog integer is invalid") from exc


def _optional_int(record: Mapping[bytes, bytes], name: str) -> int | None:
    """Return one optional integer hash field."""
    value = _optional_text(record, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise CFBDCacheBackendError("Redis catalog integer is invalid") from exc


def _string_list(value: object) -> list[str]:
    """Decode a JSON string list stored in one Redis hash field."""
    parsed: object = json.loads(_text(value))
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise CFBDCacheBackendError("Redis catalog string list is corrupt")
    return cast(list[str], parsed)


def _stored_string_list(value: object | None) -> list[str]:
    """Decode an optional compact string-list index value."""
    return [] if value is None else _string_list(value)


def _encode_string_list(values: Iterable[str]) -> bytes:
    """Encode a deterministic compact string-list index value."""
    return json.dumps(sorted(values), separators=(",", ":")).encode()


def _compact_fact_payloads(
    namespace: str,
    facts: Iterable[CatalogFact],
    projection: CatalogProjection,
    observed_at: str,
) -> dict[str, bytes]:
    """Encode one high-cardinality fact namespace as a Redis hash mapping."""
    evidence = {
        observation.fact: observation for observation in projection.observations
    }
    payloads: dict[str, bytes] = {}
    for fact in facts:
        payload = _dataclass_json(fact)
        identity = _fact_identity(namespace, payload)
        observation = evidence.get(fact)
        first_observed_at = (
            observation.first_observed_at.isoformat()
            if observation is not None and observation.first_observed_at is not None
            else observed_at
        )
        if namespace == "athlete-membership":
            payload["team"] = payload.pop("team_name")
        payload.update(
            {
                "first_seen_at": first_observed_at,
                "last_seen_at": observed_at,
                "source_version": 1,
                "schema_version": 1,
            }
        )
        payloads[identity] = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    return payloads


def _json_byte_mapping(value: Mapping[str, JSONValue]) -> dict[bytes, bytes]:
    """Convert a compact JSON object to the existing validated hash view."""
    result: dict[bytes, bytes] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, str | int | float | bool):
            result[key.encode()] = str(item).encode()
            continue
        result[key.encode()] = json.dumps(item, separators=(",", ":")).encode()
    return result


def _matches_normalized(query: str, *values: str | None) -> bool:
    """Return whether a normalized query matches any current identity value."""
    return any(value is not None and _normalize(value) == query for value in values)


def _json_required_text(record: Mapping[str, JSONValue], name: str) -> str:
    """Return one required string from validated JSON."""
    value = record.get(name)
    if isinstance(value, str):
        return value
    raise CFBDCacheBackendError("Redis JSON record is missing a string field")


def _json_optional_text(record: Mapping[str, JSONValue], name: str) -> str | None:
    """Return one optional string from validated JSON."""
    value = record.get(name)
    if value is None or isinstance(value, str):
        return value
    raise CFBDCacheBackendError("Redis JSON record has an invalid string field")


def _json_required_int(record: Mapping[str, JSONValue], name: str) -> int:
    """Return one required non-boolean integer from validated JSON."""
    value = record.get(name)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise CFBDCacheBackendError("Redis JSON record is missing an integer field")


def _dataclass_json(value: object) -> dict[str, JSONValue]:
    """Serialize one known frozen identity-fact dataclass without reflection leaks."""
    fields = getattr(value, "__dataclass_fields__", None)
    if not isinstance(fields, dict):
        raise AssertionError("Catalog projection contains a non-dataclass fact")
    result: dict[str, JSONValue] = {}
    for name in fields:
        raw = getattr(value, name)
        if isinstance(raw, datetime):
            result[name] = raw.isoformat()
        elif raw is None or isinstance(raw, str | int | float | bool):
            result[name] = raw
        else:
            raise AssertionError("Catalog fact contains an unsupported field")
    return result


def _fact_identity(namespace: str, payload: Mapping[str, JSONValue]) -> str:
    """Return a stable opaque key suffix for one typed fact record."""
    field_names = _FACT_IDENTITY_FIELDS.get(namespace)
    if field_names is None:
        raise AssertionError("Catalog fact namespace has no stable key contract")
    try:
        identity = [payload[field_name] for field_name in field_names]
    except KeyError as exc:
        raise AssertionError("Catalog fact is missing a stable key field") from exc
    material = json.dumps(
        [namespace, identity], sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(material).hexdigest()
