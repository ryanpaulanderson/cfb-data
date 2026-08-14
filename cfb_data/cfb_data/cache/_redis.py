"""Persist validated responses and normalized identity facts in Redis."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import unicodedata
from collections.abc import Awaitable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Self, cast

from redis.asyncio import Redis

from cfb_data.base.types import JSONValue, json_object
from cfb_data.cache._catalog import CatalogProjection, CoverageRecord
from cfb_data.cache._models import MAX_RESPONSE_BODY_BYTES, ResponseRecord
from cfb_data.cache.config import RedisCacheConfig
from cfb_data.errors import CFBDCacheBackendError, CFBDClientStateError
from cfb_data.identities.models import (
    AthleteIdentity,
    ConferenceIdentity,
    GameIdentity,
    TeamIdentity,
    VenueIdentity,
)

_RECORD_VERSION = 1
_SCHEMA_VERSION = 1
_MAX_ENCODED_RESPONSE_BYTES = (MAX_RESPONSE_BODY_BYTES * 4 // 3) + 64 * 1024
_FACT_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
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
            socket_timeout=self._config.io_timeout_seconds,
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
    ) -> None:
        """Atomically store response, projected facts, indexes, and coverage."""
        client = self._active_client()
        ttl_seconds = max(
            1,
            math.ceil((record.retained_until - datetime.now(UTC)).total_seconds()),
        )
        observed_at = record.fetched_at.isoformat()
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
            if projection.coverage is not None:
                self._project_coverage(pipeline, projection.coverage)
            await pipeline.execute()

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
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) for item in capabilities
        ):
            raise CFBDCacheBackendError("Redis coverage capabilities are corrupt")
        return status == "complete" and fresh_until > now and capability in capabilities

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
        else:
            ids = await self._index_members("team", _normalize(query))
        records = await self._hash_records("team", ids)
        return [
            TeamIdentity(
                id=_required_int(record, "id"),
                school=_required_text(record, "school"),
                abbreviation=_optional_text(record, "abbreviation"),
                alternate_names=tuple(
                    _string_list(record.get(b"alternate_names", b"[]"))
                ),
            )
            for record in records
        ]

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact provider-ID, name, or abbreviation matches."""
        if isinstance(query, int):
            ids = {str(query)}
        else:
            ids = await self._index_members("conference", _normalize(query))
        records = await self._hash_records("conference", ids)
        return [
            ConferenceIdentity(
                id=_required_int(record, "id"),
                name=_required_text(record, "name"),
                abbreviation=_optional_text(record, "abbreviation"),
                classification=_optional_text(record, "classification"),
            )
            for record in records
        ]

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact provider-ID or name matches."""
        if isinstance(query, int):
            ids = {str(query)}
        else:
            ids = await self._index_members("venue", _normalize(query))
        records = await self._hash_records("venue", ids)
        return [
            VenueIdentity(
                id=_required_int(record, "id"),
                name=_required_text(record, "name"),
                city=_optional_text(record, "city"),
                state=_optional_text(record, "state"),
            )
            for record in records
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
        athlete_ids = await self._index_members("athlete", _normalize(name))
        records = await self._hash_records("athlete", athlete_ids)
        results: list[AthleteIdentity] = []
        for record in records:
            athlete_id = _required_text(record, "id")
            membership_keys = await _redis_result(
                self._active_client().smembers(
                    self._key("idx", "athlete-memberships", _digest(athlete_id))
                )
            )
            memberships = await self._json_records(
                {_text(key) for key in membership_keys}, absolute=True
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
                    AthleteIdentity(
                        id=athlete_id,
                        name=_required_text(record, "name"),
                        position=_optional_text(record, "position"),
                    )
                )
            else:
                results.extend(
                    AthleteIdentity(
                        id=athlete_id,
                        name=_required_text(record, "name"),
                        position=_optional_text(record, "position"),
                        team=_json_required_text(membership, "team"),
                        season=_json_required_int(membership, "season"),
                    )
                    for membership in matching
                )
        return results

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
                        "alternate_names": json.dumps(team_fact.alternate_names),
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            names = [team_fact.school, *team_fact.alternate_names]
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
                        if season_fact.venue_id
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
        """Queue athlete identities and time-varying memberships."""
        pipe = cast(Redis, pipeline)
        for athlete_fact in projection.athletes:
            key = self._entity_key("athlete", athlete_fact.id)
            pipe.hsetnx(key, "first_seen_at", observed_at)
            pipe.hset(
                key,
                mapping=_without_none(
                    {
                        "id": athlete_fact.id,
                        "name": athlete_fact.name,
                        "position": athlete_fact.position,
                        "last_seen_at": observed_at,
                        "source_version": "1",
                        "schema_version": "1",
                    }
                ),
            )
            pipe.sadd(
                self._index_key("athlete", _normalize(athlete_fact.name)),
                athlete_fact.id,
            )
        for membership_fact in projection.athlete_team_seasons:
            membership_key = self._key(
                "catalog",
                "athlete-membership",
                _digest(membership_fact.athlete_id),
                str(membership_fact.season),
                _digest(_normalize(membership_fact.team_name)),
            )
            self._queue_json(
                pipe,
                membership_key,
                {
                    "athlete_id": membership_fact.athlete_id,
                    "team": membership_fact.team_name,
                    "season": membership_fact.season,
                    "last_seen_at": observed_at,
                },
            )
            pipe.sadd(
                self._key(
                    "idx",
                    "athlete-memberships",
                    _digest(membership_fact.athlete_id),
                ),
                membership_key,
            )

    def _project_remaining(
        self, pipeline: object, projection: CatalogProjection, observed_at: str
    ) -> None:
        """Queue the remaining typed relationship and vocabulary schemas."""
        pipe = cast(Redis, pipeline)
        groups: tuple[tuple[str, Iterable[object]], ...] = (
            ("recruit", projection.recruits),
            ("coach", projection.coaches),
            ("coach-team-season", projection.coach_team_seasons),
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
        async with client.pipeline(transaction=False) as pipeline:
            for identifier in sorted(identifiers):
                pipeline.hgetall(self._entity_key(namespace, identifier))
            rows = await pipeline.execute()
        return [
            _byte_mapping(row) for row in rows if isinstance(row, Mapping) and bool(row)
        ]

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
    return GameIdentity(
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
