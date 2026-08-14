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
from pathlib import Path
from platform import system
from typing import Self

import aiosqlite

from cfb_data.cache._catalog import CatalogProjection, CoverageRecord
from cfb_data.cache._models import MAX_RESPONSE_BODY_BYTES, ResponseRecord
from cfb_data.cache.config import SQLiteCacheConfig
from cfb_data.errors import CFBDCacheBackendError, CFBDClientStateError
from cfb_data.identities.models import (
    AthleteIdentity,
    ConferenceIdentity,
    GameIdentity,
    TeamIdentity,
    VenueIdentity,
)

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS response_records (
    key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    response_contract TEXT NOT NULL,
    body BLOB NOT NULL,
    fetched_at TEXT NOT NULL,
    fresh_until TEXT NOT NULL,
    retained_until TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    row_count INTEGER NOT NULL CHECK (row_count >= 0)
) STRICT;
CREATE INDEX IF NOT EXISTS response_retention_idx
ON response_records(retained_until);
CREATE TABLE IF NOT EXISTS refresh_leases (
    key TEXT PRIMARY KEY,
    owner_token TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    school TEXT NOT NULL,
    normalized_school TEXT NOT NULL,
    abbreviation TEXT,
    normalized_abbreviation TEXT,
    alternate_names_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS team_school_idx ON teams(normalized_school);
CREATE INDEX IF NOT EXISTS team_abbreviation_idx ON teams(normalized_abbreviation);
CREATE TABLE IF NOT EXISTS team_aliases (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    PRIMARY KEY (team_id, normalized_alias)
) STRICT;
CREATE INDEX IF NOT EXISTS team_alias_idx ON team_aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS team_seasons (
    team_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    conference_name TEXT,
    venue_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (team_id, season)
) STRICT;
CREATE TABLE IF NOT EXISTS conferences (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    abbreviation TEXT,
    normalized_abbreviation TEXT,
    classification TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS conference_name_idx ON conferences(normalized_name);
CREATE INDEX IF NOT EXISTS conference_abbreviation_idx
ON conferences(normalized_abbreviation);
CREATE TABLE IF NOT EXISTS conference_affiliations (
    team_id INTEGER NOT NULL,
    conference_id INTEGER NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (team_id, conference_id, start_year)
) STRICT;
CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS venue_name_idx ON venues(normalized_name);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    season INTEGER,
    week INTEGER,
    season_type TEXT,
    start_date TEXT,
    status TEXT,
    home_team_id INTEGER,
    away_team_id INTEGER,
    venue_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS game_partition_idx ON games(season, week);
CREATE TABLE IF NOT EXISTS athletes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    position TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS athlete_name_idx ON athletes(normalized_name);
CREATE TABLE IF NOT EXISTS athlete_team_seasons (
    athlete_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    normalized_team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (athlete_id, normalized_team_name, season)
) STRICT;
CREATE TABLE IF NOT EXISTS recruits (
    id TEXT PRIMARY KEY,
    athlete_id TEXT,
    name TEXT NOT NULL,
    year INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coaches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    wikidata_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coach_team_seasons (
    coach_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    tenure_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (coach_id, team_id, start_year)
) STRICT;
CREATE TABLE IF NOT EXISTS drives (
    id TEXT PRIMARY KEY,
    game_id INTEGER NOT NULL,
    offense_team_id INTEGER,
    offense_team TEXT,
    defense_team_id INTEGER,
    defense_team TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS plays (
    id TEXT PRIMARY KEY,
    game_id INTEGER NOT NULL,
    drive_id TEXT,
    play_type_id INTEGER,
    play_type TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS vocabularies (
    namespace TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    abbreviation TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    PRIMARY KEY (namespace, id)
) STRICT;
CREATE TABLE IF NOT EXISTS playoff_matchups (
    id INTEGER PRIMARY KEY,
    season INTEGER,
    linked_game_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS coverage (
    partition_key TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    canonical_filters TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    status TEXT NOT NULL,
    response_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    fresh_until TEXT NOT NULL,
    retained_until TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    known_cap INTEGER,
    api_version TEXT NOT NULL,
    cache_key_version INTEGER NOT NULL,
    response_contract_version INTEGER NOT NULL,
    projector_version INTEGER NOT NULL,
    catalog_schema_version INTEGER NOT NULL,
    failure_category TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS coverage_namespace_idx ON coverage(namespace);
CREATE TABLE IF NOT EXISTS coverage_failures (
    partition_key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    canonical_filters TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    failed_at TEXT NOT NULL
) STRICT;
"""


class SQLiteCacheBackend:
    """Own one WAL-mode SQLite connection for cache and catalog operations."""

    def __init__(self, config: SQLiteCacheConfig) -> None:
        """Initialize configuration without opening a database connection."""
        self._config = config
        self._path = config.path or _default_path()
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
            busy_cursor = await connection.execute(
                f"PRAGMA busy_timeout={int(self._config.busy_timeout.total_seconds() * 1000)}"
            )
            await busy_cursor.close()
            for statement in (
                "PRAGMA foreign_keys=ON",
                "PRAGMA journal_mode=WAL",
                "PRAGMA synchronous=NORMAL",
            ):
                cursor = await _retry_locked(
                    partial(_execute_statement, connection, statement),
                    deadline=initialization_deadline,
                )
                await cursor.close()
            schema_cursor = await _retry_locked(
                lambda: connection.executescript(_SCHEMA),
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
                "SELECT length(body) FROM response_records WHERE key = ?", (key,)
            )
            size_row = await size_cursor.fetchone()
            await size_cursor.close()
            if size_row is None:
                return None
            if _row_int(size_row, 0) > MAX_RESPONSE_BODY_BYTES:
                await connection.execute(
                    "DELETE FROM response_records WHERE key = ?", (key,)
                )
                raise CFBDCacheBackendError("SQLite response record is oversized")
            cursor = await connection.execute(
                "SELECT key, endpoint, response_contract, body, fetched_at, "
                "fresh_until, retained_until, etag, last_modified, row_count "
                "FROM response_records WHERE key = ?",
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
                    "DELETE FROM response_records WHERE key = ?", (key,)
                )
                raise CFBDCacheBackendError(
                    "SQLite response record is corrupt"
                ) from exc
            if record.retained_until <= now:
                await connection.execute(
                    "DELETE FROM response_records WHERE key = ?", (key,)
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
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    "INSERT INTO response_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET endpoint=excluded.endpoint, "
                    "response_contract=excluded.response_contract, body=excluded.body, "
                    "fetched_at=excluded.fetched_at, fresh_until=excluded.fresh_until, "
                    "retained_until=excluded.retained_until, etag=excluded.etag, "
                    "last_modified=excluded.last_modified, row_count=excluded.row_count",
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
                await self._commit_projection(connection, projection, observed_at)
                await connection.commit()
            except Exception as exc:
                await connection.rollback()
                raise CFBDCacheBackendError("SQLite cache commit failed") from exc

    async def delete_response(self, key: str) -> None:
        """Delete one invalid or expired response record."""
        async with self._operation_lock:
            await self._active_connection().execute(
                "DELETE FROM response_records WHERE key = ?", (key,)
            )

    async def cleanup_responses(self, now: datetime) -> int:
        """Delete expired response records without pruning catalog facts."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                "DELETE FROM response_records WHERE retained_until <= ?",
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
                "SELECT capabilities_json FROM coverage WHERE endpoint = ? "
                "AND canonical_filters = ? AND status = 'complete' AND fresh_until > ?",
                (endpoint, canonical_filters, now.isoformat()),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            for row in rows:
                raw = _row_str(row, 0)
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
                "INSERT INTO coverage_failures VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(partition_key) DO UPDATE SET "
                "failure_category=excluded.failure_category, "
                "failed_at=excluded.failed_at",
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
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    "INSERT INTO refresh_leases(key, owner_token, acquired_at, expires_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                    "owner_token=excluded.owner_token, acquired_at=excluded.acquired_at, "
                    "expires_at=excluded.expires_at WHERE refresh_leases.expires_at <= ?",
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
            except Exception as exc:
                await connection.rollback()
                raise CFBDCacheBackendError("SQLite lease acquisition failed") from exc

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a lease only if the caller remains its owner."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                "UPDATE refresh_leases SET expires_at = ? "
                "WHERE key = ? AND owner_token = ?",
                (expires_at.isoformat(), key, owner_token),
            )
            changed = cursor.rowcount == 1
            await cursor.close()
            return changed

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a lease only if the caller remains its owner."""
        async with self._operation_lock:
            cursor = await self._active_connection().execute(
                "DELETE FROM refresh_leases WHERE key = ? AND owner_token = ?",
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
                "SELECT id, school, abbreviation, alternate_names_json "
                "FROM teams WHERE id = ?",
                (query,),
            )
        else:
            normalized = _normalize(query)
            cursor = await connection.execute(
                "SELECT DISTINCT t.id, t.school, t.abbreviation, "
                "t.alternate_names_json FROM teams t LEFT JOIN team_aliases a "
                "ON a.team_id = t.id WHERE t.normalized_school = ? "
                "OR t.normalized_abbreviation = ? OR a.normalized_alias = ?",
                (normalized, normalized, normalized),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            TeamIdentity(
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
                "SELECT id, name, abbreviation, classification FROM conferences "
                "WHERE id = ?",
                (query,),
            )
        else:
            normalized = _normalize(query)
            cursor = await connection.execute(
                "SELECT id, name, abbreviation, classification FROM conferences "
                "WHERE normalized_name = ? OR normalized_abbreviation = ?",
                (normalized, normalized),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            ConferenceIdentity(
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
                "SELECT id, name, city, state FROM venues WHERE id = ?", (query,)
            )
        else:
            cursor = await connection.execute(
                "SELECT id, name, city, state FROM venues WHERE normalized_name = ?",
                (_normalize(query),),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            VenueIdentity(
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
            "SELECT id, season, week, season_type, start_date, status, "
            "home_team_id, away_team_id, venue_id FROM games WHERE id = ?",
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
        clauses = ["g.season = ?"]
        arguments: list[object] = [season]
        if week is not None:
            clauses.append("g.week = ?")
            arguments.append(week)
        if team is not None:
            clauses.append("(home.normalized_school = ? OR away.normalized_school = ?)")
            normalized = _normalize(team)
            arguments.extend([normalized, normalized])
        cursor = await self._active_connection().execute(
            "SELECT g.id, g.season, g.week, g.season_type, g.start_date, g.status, "
            "g.home_team_id, g.away_team_id, g.venue_id FROM games g "
            "LEFT JOIN teams home ON home.id = g.home_team_id "
            "LEFT JOIN teams away ON away.id = g.away_team_id WHERE "
            + " AND ".join(clauses)
            + " ORDER BY g.start_date, g.id",
            arguments,
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
        clauses = ["a.normalized_name = ?"]
        arguments: list[object] = [_normalize(name)]
        if team is not None:
            clauses.append("m.normalized_team_name = ?")
            arguments.append(_normalize(team))
        if season is not None:
            clauses.append("m.season = ?")
            arguments.append(season)
        cursor = await self._active_connection().execute(
            "SELECT DISTINCT a.id, a.name, a.position, m.team_name, m.season "
            "FROM athletes a LEFT JOIN athlete_team_seasons m "
            "ON m.athlete_id = a.id WHERE "
            + " AND ".join(clauses)
            + " ORDER BY a.id, m.season",
            arguments,
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            AthleteIdentity(
                id=_row_str(row, 0),
                name=_row_str(row, 1),
                position=_row_optional_str(row, 2),
                team=_row_optional_str(row, 3),
                season=_row_optional_int(row, 4),
            )
            for row in rows
        ]

    async def _validate_schema(self, connection: aiosqlite.Connection) -> None:
        """Initialize or reject the versioned catalog schema."""
        insert_cursor = await connection.execute(
            "INSERT INTO cache_meta(key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO NOTHING",
            (str(_SCHEMA_VERSION),),
        )
        await insert_cursor.close()
        cursor = await connection.execute(
            "SELECT value FROM cache_meta WHERE key = 'schema_version'"
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise CFBDCacheBackendError("SQLite cache schema metadata is missing")
        if _row_str(row, 0) != str(_SCHEMA_VERSION):
            raise CFBDCacheBackendError("SQLite cache schema version is incompatible")

    async def _commit_projection(
        self,
        connection: aiosqlite.Connection,
        projection: CatalogProjection,
        observed_at: str,
    ) -> None:
        """Upsert all projected fact types inside the caller's transaction."""
        await connection.executemany(
            "INSERT INTO teams VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET school=excluded.school, "
            "normalized_school=excluded.normalized_school, "
            "abbreviation=COALESCE(excluded.abbreviation, teams.abbreviation), "
            "normalized_abbreviation=COALESCE(excluded.normalized_abbreviation, "
            "teams.normalized_abbreviation), alternate_names_json=excluded.alternate_names_json, "
            "last_seen_at=excluded.last_seen_at",
            [
                (
                    fact.id,
                    fact.school,
                    _normalize(fact.school),
                    fact.abbreviation,
                    _normalize(fact.abbreviation) if fact.abbreviation else None,
                    json.dumps(fact.alternate_names, separators=(",", ":")),
                    observed_at,
                    observed_at,
                )
                for fact in projection.teams
            ],
        )
        await connection.executemany(
            "INSERT INTO team_aliases VALUES (?, ?, ?) "
            "ON CONFLICT(team_id, normalized_alias) DO UPDATE SET alias=excluded.alias",
            [
                (fact.id, alias, _normalize(alias))
                for fact in projection.teams
                for alias in fact.alternate_names
            ],
        )
        await connection.executemany(
            "INSERT INTO team_seasons VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, season) DO UPDATE SET "
            "conference_name=COALESCE(excluded.conference_name, team_seasons.conference_name), "
            "venue_id=COALESCE(excluded.venue_id, team_seasons.venue_id), "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO conferences VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "normalized_name=excluded.normalized_name, abbreviation=excluded.abbreviation, "
            "normalized_abbreviation=excluded.normalized_abbreviation, "
            "classification=excluded.classification, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO conference_affiliations VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, conference_id, start_year) DO UPDATE SET "
            "end_year=excluded.end_year, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO venues VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "normalized_name=excluded.normalized_name, city=excluded.city, "
            "state=excluded.state, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET season=COALESCE(excluded.season, games.season), "
            "week=COALESCE(excluded.week, games.week), "
            "season_type=COALESCE(excluded.season_type, games.season_type), "
            "start_date=COALESCE(excluded.start_date, games.start_date), "
            "status=COALESCE(excluded.status, games.status), "
            "home_team_id=COALESCE(excluded.home_team_id, games.home_team_id), "
            "away_team_id=COALESCE(excluded.away_team_id, games.away_team_id), "
            "venue_id=COALESCE(excluded.venue_id, games.venue_id), "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO athletes VALUES (?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "normalized_name=excluded.normalized_name, "
            "position=COALESCE(excluded.position, athletes.position), "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO athlete_team_seasons VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(athlete_id, normalized_team_name, season) DO UPDATE SET "
            "team_name=excluded.team_name, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO recruits VALUES (?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET athlete_id=COALESCE(excluded.athlete_id, "
            "recruits.athlete_id), name=excluded.name, year=excluded.year, "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO coaches VALUES (?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "normalized_name=excluded.normalized_name, "
            "wikidata_id=COALESCE(excluded.wikidata_id, coaches.wikidata_id), "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO coach_team_seasons VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(coach_id, team_id, start_year) DO UPDATE SET "
            "end_year=excluded.end_year, "
            "tenure_id=COALESCE(excluded.tenure_id, coach_team_seasons.tenure_id), "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO drives VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET game_id=excluded.game_id, "
            "offense_team_id=COALESCE(excluded.offense_team_id, drives.offense_team_id), "
            "offense_team=excluded.offense_team, "
            "defense_team_id=COALESCE(excluded.defense_team_id, drives.defense_team_id), "
            "defense_team=excluded.defense_team, "
            "last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET game_id=excluded.game_id, "
            "drive_id=excluded.drive_id, play_type_id=excluded.play_type_id, "
            "play_type=excluded.play_type, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO vocabularies VALUES (?, ?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(namespace, id) DO UPDATE SET name=excluded.name, "
            "abbreviation=excluded.abbreviation, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO playoff_matchups VALUES (?, ?, ?, ?, ?, 1, 1) "
            "ON CONFLICT(id) DO UPDATE SET season=excluded.season, "
            "linked_game_id=excluded.linked_game_id, last_seen_at=excluded.last_seen_at",
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
            "INSERT INTO coverage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "'5.24.0', 1, 1, 1, 1, NULL) ON CONFLICT(partition_key) DO UPDATE SET "
            "namespace=excluded.namespace, canonical_filters=excluded.canonical_filters, "
            "capabilities_json=excluded.capabilities_json, status=excluded.status, "
            "response_key=excluded.response_key, endpoint=excluded.endpoint, "
            "fetched_at=excluded.fetched_at, validated_at=excluded.validated_at, "
            "fresh_until=excluded.fresh_until, retained_until=excluded.retained_until, "
            "row_count=excluded.row_count, known_cap=excluded.known_cap, "
            "failure_category=NULL",
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
            ),
        )
        await connection.execute(
            "DELETE FROM coverage_failures WHERE partition_key = ?",
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
    return GameIdentity(
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
