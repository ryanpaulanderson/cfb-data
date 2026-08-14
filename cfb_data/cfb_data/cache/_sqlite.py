"""Persist validated responses and normalized identity facts in SQLite."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from functools import partial
from itertools import batched
from pathlib import Path
from platform import system
from typing import TYPE_CHECKING, Self

import aiosqlite

from cfb_data._catalog.merge import merge_catalog_observations
from cfb_data._catalog.models import (
    CatalogCounts,
    CatalogObservation,
    CatalogProjection,
    CoverageRecord,
)
from cfb_data._catalog.sources import projection_contract
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
from cfb_data.cache._sqlite_sql import SQLiteSQL
from cfb_data.cache.config import SQLiteCacheConfig
from cfb_data.errors import CFBDCacheBackendError, CFBDClientStateError

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity

_SCHEMA_VERSION = 1


class SQLiteCacheBackend:
    """Own one WAL-mode SQLite connection for cache and catalog operations."""

    def __init__(self, config: SQLiteCacheConfig) -> None:
        """Initialize configuration without opening a database connection."""
        self._config = config
        self._path = config.path or _default_path()
        self._sql = SQLiteSQL()
        self._connection: aiosqlite.Connection | None = None
        self._operation_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        """Return the selected database path without opening it."""
        return self._path

    async def open(self) -> Self:
        """Open, harden, configure, and migrate the local database."""
        if self._connection is not None:
            raise CFBDClientStateError("SQLite cache backend is already open")
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            connection = await aiosqlite.connect(
                self._path,
                timeout=self._config.busy_timeout.total_seconds(),
                isolation_level=None,
            )
            self._connection = connection
            initialization_deadline = (
                asyncio.get_running_loop().time()
                + self._config.busy_timeout.total_seconds()
            )
            busy_timeout_ms = int(self._config.busy_timeout.total_seconds() * 1000)
            busy_cursor = await connection.execute(
                self._sql.render(
                    "set_busy_timeout.sql", busy_timeout_ms=busy_timeout_ms
                )
            )
            await busy_cursor.close()
            for template_name in (
                "enable_foreign_keys.sql",
                "enable_wal.sql",
                "set_synchronous_normal.sql",
            ):
                cursor = await _retry_locked(
                    partial(
                        _execute_statement,
                        connection,
                        self._sql.render(template_name),
                    ),
                    deadline=initialization_deadline,
                )
                await cursor.close()
            schema_cursor = await _retry_locked(
                lambda: connection.executescript(self._sql.render("schema.sql")),
                deadline=initialization_deadline,
            )
            await schema_cursor.close()
            await _retry_locked(
                lambda: self._validate_schema(connection),
                deadline=initialization_deadline,
            )
            os.chmod(self._path, 0o600)
            return self
        except Exception as exc:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None
            raise CFBDCacheBackendError("SQLite cache initialization failed") from exc

    async def close(self) -> None:
        """Close the owned database connection."""
        async with self._operation_lock:
            connection = self._active_connection()
            self._connection = None
            await connection.close()

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return one retained record after deleting it if expired."""
        async with self._operation_lock:
            connection = self._active_connection()
            size_cursor = await connection.execute(
                self._sql.render("get_response_size.sql"), (key,)
            )
            size_row = await size_cursor.fetchone()
            await size_cursor.close()
            if size_row is None:
                return None
            if _row_int(size_row, 0) > MAX_RESPONSE_BODY_BYTES:
                await connection.execute(
                    self._sql.render("delete_response.sql"), (key,)
                )
                raise CFBDCacheBackendError("SQLite response record is oversized")
            cursor = await connection.execute(
                self._sql.render("get_response.sql"),
                (key,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return None
            try:
                record = _response_from_row(row)
            except Exception as exc:
                await connection.execute(
                    self._sql.render("delete_response.sql"), (key,)
                )
                raise CFBDCacheBackendError(
                    "SQLite response record is corrupt"
                ) from exc
            if record.retained_until <= now:
                await connection.execute(
                    self._sql.render("delete_response.sql"), (key,)
                )
                return None
            return record

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> None:
        """Atomically upsert response, catalog facts, and coverage."""
        async with self._operation_lock:
            connection = self._active_connection()
            observed_at = record.fetched_at.isoformat()
            try:
                await connection.execute(self._sql.render("begin_immediate.sql"))
                await connection.execute(
                    self._sql.render("upsert_response.sql"),
                    (
                        record.key,
                        record.endpoint,
                        record.response_contract,
                        record.body,
                        record.fetched_at.isoformat(),
                        record.fresh_until.isoformat(),
                        record.retained_until.isoformat(),
                        record.etag,
                        record.last_modified,
                        record.row_count,
                    ),
                )
                projection = await self._merge_projection(
                    connection,
                    projection,
                    observed_at=record.fetched_at,
                    source=record.endpoint,
                )
                await self._commit_projection(connection, projection, observed_at)
                await connection.commit()
            except asyncio.CancelledError:
                await connection.rollback()
                raise
            except Exception as exc:
                await connection.rollback()
                raise CFBDCacheBackendError("SQLite cache commit failed") from exc

    async def delete_response(self, key: str) -> None:
        """Delete one invalid or expired response record."""
        async with self._operation_lock:
            await self._active_connection().execute(
                self._sql.render("delete_response.sql"), (key,)
            )

    async def cleanup_responses(self, now: datetime) -> int:
        """Delete expired response records without pruning catalog facts."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                self._sql.render("cleanup_responses.sql"),
                (now.isoformat(),),
            )
            changed = max(cursor.rowcount, 0)
            await cursor.close()
            return changed

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Return whether complete fresh coverage proves one capability."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                self._sql.render("find_fresh_coverage.sql"),
                (endpoint, canonical_filters, now.isoformat()),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            for row in rows:
                raw = _row_str(row, 0)
                if _row_str(row, 1) != projection_contract(endpoint):
                    continue
                try:
                    parsed: object = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CFBDCacheBackendError(
                        "SQLite coverage record is corrupt"
                    ) from exc
                if (
                    isinstance(parsed, list)
                    and all(isinstance(item, str) for item in parsed)
                    and capability in parsed
                ):
                    return True
            return False

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
        async with self._operation_lock:
            await self._active_connection().execute(
                self._sql.render("upsert_coverage_failure.sql"),
                (
                    partition_key,
                    endpoint,
                    canonical_filters,
                    failure_category,
                    failed_at.isoformat(),
                ),
            )

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Atomically acquire a missing or expired refresh lease."""
        async with self._operation_lock:
            connection = self._active_connection()
            try:
                await connection.execute(self._sql.render("begin_immediate.sql"))
                cursor = await connection.execute(
                    self._sql.render("acquire_refresh_lease.sql"),
                    (
                        key,
                        owner_token,
                        now.isoformat(),
                        expires_at.isoformat(),
                        now.isoformat(),
                    ),
                )
                acquired = cursor.rowcount == 1
                await cursor.close()
                await connection.commit()
                return acquired
            except asyncio.CancelledError:
                await connection.rollback()
                raise
            except Exception as exc:
                await connection.rollback()
                raise CFBDCacheBackendError("SQLite lease acquisition failed") from exc

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a lease only if the caller remains its owner."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                self._sql.render("renew_refresh_lease.sql"),
                (expires_at.isoformat(), key, owner_token),
            )
            changed = cursor.rowcount == 1
            await cursor.close()
            return changed

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a lease only if the caller remains its owner."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                self._sql.render("release_refresh_lease.sql"),
                (key, owner_token),
            )
            changed = cursor.rowcount == 1
            await cursor.close()
            return changed

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return exact provider-ID, school, abbreviation, or alias matches."""
        async with self._operation_lock:
            return await self._find_teams_unlocked(query)

    async def _find_teams_unlocked(self, query: str | int) -> list[TeamIdentity]:
        """Return exact team matches while the caller owns the operation lock."""
        connection = self._active_connection()
        if isinstance(query, int):
            cursor = await connection.execute(
                self._sql.render("find_team_by_id.sql"),
                (query,),
            )
        else:
            normalized = _normalize(query)
            cursor = await connection.execute(
                self._sql.render("find_team_by_name.sql"),
                (normalized, normalized, normalized),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            team_identity(
                id=_row_int(row, 0),
                school=_row_str(row, 1),
                abbreviation=_row_optional_str(row, 2),
                alternate_names=tuple(json.loads(_row_str(row, 3))),
            )
            for row in rows
        ]

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact provider-ID, name, or abbreviation matches."""
        async with self._operation_lock:
            return await self._find_conferences_unlocked(query)

    async def _find_conferences_unlocked(
        self, query: str | int
    ) -> list[ConferenceIdentity]:
        """Return exact conference matches while holding the operation lock."""
        connection = self._active_connection()
        if isinstance(query, int):
            cursor = await connection.execute(
                self._sql.render("find_conference_by_id.sql"),
                (query,),
            )
        else:
            normalized = _normalize(query)
            cursor = await connection.execute(
                self._sql.render("find_conference_by_name.sql"),
                (normalized, normalized),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            conference_identity(
                id=_row_int(row, 0),
                name=_row_str(row, 1),
                abbreviation=_row_optional_str(row, 2),
                classification=_row_optional_str(row, 3),
            )
            for row in rows
        ]

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact provider-ID or normalized-name matches."""
        async with self._operation_lock:
            return await self._find_venues_unlocked(query)

    async def _find_venues_unlocked(self, query: str | int) -> list[VenueIdentity]:
        """Return exact venue matches while holding the operation lock."""
        connection = self._active_connection()
        if isinstance(query, int):
            cursor = await connection.execute(
                self._sql.render("find_venue_by_id.sql"), (query,)
            )
        else:
            cursor = await connection.execute(
                self._sql.render("find_venue_by_name.sql"),
                (_normalize(query),),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            venue_identity(
                id=_row_int(row, 0),
                name=_row_str(row, 1),
                city=_row_optional_str(row, 2),
                state=_row_optional_str(row, 3),
            )
            for row in rows
        ]

    async def find_game(self, game_id: int) -> GameIdentity | None:
        """Return one compact game identity by provider ID."""
        async with self._operation_lock:
            return await self._find_game_unlocked(game_id)

    async def _find_game_unlocked(self, game_id: int) -> GameIdentity | None:
        """Return one game identity while holding the operation lock."""
        cursor = await self._active_connection().execute(
            self._sql.render("find_game_by_id.sql"),
            (game_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return _game_identity(row) if row is not None else None

    async def find_games(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return games in a season partition with optional exact filters."""
        async with self._operation_lock:
            return await self._find_games_unlocked(season=season, week=week, team=team)

    async def _find_games_unlocked(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return game matches while holding the operation lock."""
        normalized_team = _normalize(team) if team is not None else None
        cursor = await self._active_connection().execute(
            self._sql.render("find_games.sql"),
            (
                season,
                week,
                week,
                normalized_team,
                normalized_team,
                normalized_team,
                normalized_team,
            ),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_game_identity(row) for row in rows]

    async def find_athletes(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return exact athlete matches within optional team-season scope."""
        async with self._operation_lock:
            return await self._find_athletes_unlocked(
                name=name, team=team, season=season
            )

    async def _find_athletes_unlocked(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return exact athlete matches while holding the operation lock."""
        normalized_team = _normalize(team) if team is not None else None
        cursor = await self._active_connection().execute(
            self._sql.render("find_athletes.sql"),
            (
                _normalize(name),
                normalized_team,
                normalized_team,
                season,
                season,
            ),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            athlete_identity(
                id=_row_str(row, 0),
                name=_row_str(row, 1),
                position=_row_optional_str(row, 2),
                team=_row_optional_str(row, 3),
                season=_row_optional_int(row, 4),
            )
            for row in rows
        ]

    async def catalog_counts(self) -> CatalogCounts:
        """Return row counts for every explicit SQLite catalog table."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                self._sql.render("catalog_counts.sql")
            )
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            raise CFBDCacheBackendError("SQLite catalog count query returned no row")
        return CatalogCounts(*(_row_int(row, index) for index in range(15)))

    async def _validate_schema(self, connection: aiosqlite.Connection) -> None:
        """Initialize or reject the versioned catalog schema."""
        insert_cursor = await connection.execute(
            self._sql.render("initialize_schema_version.sql"),
            (str(_SCHEMA_VERSION),),
        )
        await insert_cursor.close()
        cursor = await connection.execute(self._sql.render("get_schema_version.sql"))
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise CFBDCacheBackendError("SQLite cache schema metadata is missing")
        if _row_str(row, 0) != str(_SCHEMA_VERSION):
            raise CFBDCacheBackendError("SQLite cache schema version is incompatible")

    async def _merge_projection(
        self,
        connection: aiosqlite.Connection,
        projection: CatalogProjection,
        *,
        observed_at: datetime,
        source: str,
    ) -> CatalogProjection:
        """Merge typed observations and persist their provenance transactionally."""
        candidates = projection_observations(
            projection, observed_at=observed_at, source=source
        )
        keyed = tuple(
            (observation_storage_key(candidate), candidate) for candidate in candidates
        )
        stored: dict[tuple[str, str], CatalogObservation] = {}
        for chunk in batched(keyed, 400):
            arguments = tuple(
                value for (namespace, grain), _ in chunk for value in (namespace, grain)
            )
            cursor = await connection.execute(
                self._sql.render(
                    "select_catalog_observations.sql", pair_count=len(chunk)
                ),
                arguments,
            )
            rows = await cursor.fetchall()
            await cursor.close()
            stored.update(
                {
                    (_row_str(row, 0), _row_str(row, 1)): (
                        decode_catalog_observation(_row_str(row, 2))
                    )
                    for row in rows
                }
            )
        merged = tuple(
            merge_catalog_observations(stored.get(key), candidate)
            for key, candidate in keyed
        )
        await connection.executemany(
            self._sql.render("upsert_catalog_observation.sql"),
            (
                (
                    *observation_storage_key(observation),
                    encode_catalog_observation(observation),
                )
                for observation in merged
            ),
        )
        return projection_from_observations(merged, original=projection)

    async def _commit_projection(
        self,
        connection: aiosqlite.Connection,
        projection: CatalogProjection,
        observed_at: str,
    ) -> None:
        """Upsert all projected fact types inside the caller's transaction."""
        await connection.executemany(
            self._sql.render("upsert_team.sql"),
            [
                (
                    fact.id,
                    fact.school,
                    _normalize(fact.school),
                    fact.abbreviation,
                    _normalize(fact.abbreviation) if fact.abbreviation else None,
                    json.dumps(fact.alternate_names or (), separators=(",", ":")),
                    observed_at,
                    observed_at,
                )
                for fact in projection.teams
            ],
        )
        await connection.executemany(
            self._sql.render("delete_team_aliases.sql"),
            [
                (fact.id,)
                for fact in projection.teams
                if fact.alternate_names is not None
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_team_alias.sql"),
            [
                (fact.id, alias, _normalize(alias))
                for fact in projection.teams
                for alias in (fact.alternate_names or ())
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_team_season.sql"),
            [
                (
                    fact.team_id,
                    fact.season,
                    fact.conference_name,
                    fact.venue_id,
                    observed_at,
                    observed_at,
                )
                for fact in projection.team_seasons
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_conference.sql"),
            [
                (
                    fact.id,
                    fact.name,
                    _normalize(fact.name),
                    fact.abbreviation,
                    _normalize(fact.abbreviation) if fact.abbreviation else None,
                    fact.classification,
                    observed_at,
                    observed_at,
                )
                for fact in projection.conferences
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_conference_affiliation.sql"),
            [
                (
                    fact.team_id,
                    fact.conference_id,
                    fact.start_year,
                    fact.end_year,
                    observed_at,
                    observed_at,
                )
                for fact in projection.affiliations
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_venue.sql"),
            [
                (
                    fact.id,
                    fact.name,
                    _normalize(fact.name),
                    fact.city,
                    fact.state,
                    observed_at,
                    observed_at,
                )
                for fact in projection.venues
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_game.sql"),
            [
                (
                    fact.id,
                    fact.season,
                    fact.week,
                    fact.season_type,
                    fact.start_date.isoformat() if fact.start_date else None,
                    fact.status,
                    fact.home_team_id,
                    fact.away_team_id,
                    fact.venue_id,
                    observed_at,
                    observed_at,
                )
                for fact in projection.games
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_athlete.sql"),
            [
                (
                    fact.id,
                    fact.name,
                    _normalize(fact.name),
                    fact.position,
                    observed_at,
                    observed_at,
                )
                for fact in projection.athletes
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_athlete_team_season.sql"),
            [
                (
                    fact.athlete_id,
                    fact.team_name,
                    _normalize(fact.team_name),
                    fact.season,
                    observed_at,
                    observed_at,
                )
                for fact in projection.athlete_team_seasons
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_recruit.sql"),
            [
                (
                    fact.id,
                    fact.athlete_id,
                    fact.name,
                    fact.year,
                    observed_at,
                    observed_at,
                )
                for fact in projection.recruits
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_coach.sql"),
            [
                (
                    fact.id,
                    fact.name,
                    _normalize(fact.name),
                    fact.wikidata_id,
                    observed_at,
                    observed_at,
                )
                for fact in projection.coaches
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_coach_team_season.sql"),
            [
                (
                    fact.coach_id,
                    fact.team_id,
                    fact.start_year,
                    fact.end_year,
                    fact.tenure_id,
                    observed_at,
                    observed_at,
                )
                for fact in projection.coach_team_seasons
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_drive.sql"),
            [
                (
                    fact.id,
                    fact.game_id,
                    fact.offense_team_id,
                    fact.offense_team,
                    fact.defense_team_id,
                    fact.defense_team,
                    observed_at,
                    observed_at,
                )
                for fact in projection.drives
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_play.sql"),
            [
                (
                    fact.id,
                    fact.game_id,
                    fact.drive_id,
                    fact.play_type_id,
                    fact.play_type,
                    observed_at,
                    observed_at,
                )
                for fact in projection.plays
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_vocabulary.sql"),
            [
                (
                    fact.namespace,
                    fact.id,
                    fact.name,
                    fact.abbreviation,
                    observed_at,
                    observed_at,
                )
                for fact in projection.vocabularies
            ],
        )
        await connection.executemany(
            self._sql.render("upsert_playoff_matchup.sql"),
            [
                (
                    fact.id,
                    fact.season,
                    fact.linked_game_id,
                    observed_at,
                    observed_at,
                )
                for fact in projection.playoff_matchups
            ],
        )
        if projection.coverage is not None:
            await self._commit_coverage(connection, projection.coverage)

    async def _commit_coverage(
        self, connection: aiosqlite.Connection, coverage: CoverageRecord
    ) -> None:
        """Upsert one complete capability-aware coverage record."""
        await connection.execute(
            self._sql.render("upsert_coverage.sql"),
            (
                coverage.partition_key,
                coverage.namespace,
                coverage.canonical_filters,
                json.dumps(coverage.capabilities, separators=(",", ":")),
                coverage.status,
                coverage.response_key,
                coverage.endpoint,
                coverage.fetched_at.isoformat(),
                coverage.validated_at.isoformat(),
                coverage.fresh_until.isoformat(),
                coverage.retained_until.isoformat(),
                coverage.row_count,
                coverage.known_cap,
                coverage.projection_contract,
            ),
        )
        await connection.execute(
            self._sql.render("delete_coverage_failure.sql"),
            (coverage.partition_key,),
        )

    def _active_connection(self) -> aiosqlite.Connection:
        """Return the active connection or reject lifecycle misuse."""
        if self._connection is None:
            raise CFBDClientStateError("Cache access requires an active client context")
        return self._connection


async def _retry_locked[ResultT](
    operation: Callable[[], Awaitable[ResultT]], *, deadline: float
) -> ResultT:
    """Retry transient SQLite startup locks until the configured deadline."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            return await operation()
        except sqlite3.OperationalError as exc:
            error_code = getattr(exc, "sqlite_errorcode", None)
            primary_code = error_code & 0xFF if isinstance(error_code, int) else None
            remaining = deadline - loop.time()
            if primary_code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise
            if remaining <= 0:
                raise
            await asyncio.sleep(min(0.025, remaining))


async def _execute_statement(
    connection: aiosqlite.Connection, statement: str
) -> aiosqlite.Cursor:
    """Execute one SQLite initialization statement for bounded retry."""
    return await connection.execute(statement)


def _default_path() -> Path:
    """Return a platform-appropriate per-user private cache database path."""
    platform_name = system()
    if platform_name == "Darwin":
        return Path.home() / "Library" / "Caches" / "cfb-data" / "cache-v1.sqlite3"
    if platform_name == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "cfb-data" / "cache-v1.sqlite3"
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "cfb-data" / "cache-v1.sqlite3"


def _normalize(value: str) -> str:
    """Apply exact identity normalization without fuzzy matching."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _response_from_row(row: Sequence[object]) -> ResponseRecord:
    """Validate and construct one response record from SQLite columns."""
    body = row[3]
    if not isinstance(body, bytes):
        raise CFBDCacheBackendError("SQLite response record is corrupt")
    return ResponseRecord(
        key=_row_str(row, 0),
        endpoint=_row_str(row, 1),
        response_contract=_row_str(row, 2),
        body=body,
        fetched_at=datetime.fromisoformat(_row_str(row, 4)),
        fresh_until=datetime.fromisoformat(_row_str(row, 5)),
        retained_until=datetime.fromisoformat(_row_str(row, 6)),
        etag=_row_optional_str(row, 7),
        last_modified=_row_optional_str(row, 8),
        row_count=_row_int(row, 9),
    )


def _game_identity(row: Sequence[object]) -> GameIdentity:
    """Validate and construct one compact game identity from SQLite columns."""
    raw_date = _row_optional_str(row, 4)
    return game_identity(
        id=_row_int(row, 0),
        season=_row_optional_int(row, 1),
        week=_row_optional_int(row, 2),
        season_type=_row_optional_str(row, 3),
        start_date=datetime.fromisoformat(raw_date) if raw_date else None,
        status=_row_optional_str(row, 5),
        home_team_id=_row_optional_int(row, 6),
        away_team_id=_row_optional_int(row, 7),
        venue_id=_row_optional_int(row, 8),
    )


def _row_str(row: Sequence[object], index: int) -> str:
    """Return a required string column or report catalog corruption."""
    value = row[index]
    if not isinstance(value, str):
        raise CFBDCacheBackendError("SQLite catalog record is corrupt")
    return value


def _row_optional_str(row: Sequence[object], index: int) -> str | None:
    """Return an optional string column or report catalog corruption."""
    value = row[index]
    if value is None or isinstance(value, str):
        return value
    raise CFBDCacheBackendError("SQLite catalog record is corrupt")


def _row_int(row: Sequence[object], index: int) -> int:
    """Return a required integer column or report catalog corruption."""
    value = row[index]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise CFBDCacheBackendError("SQLite catalog record is corrupt")


def _row_optional_int(row: Sequence[object], index: int) -> int | None:
    """Return an optional integer column or report catalog corruption."""
    value = row[index]
    if value is None:
        return None
    return _row_int(row, index)
