"""Exercise every public REST route and identity operation against real CFBD."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import subprocess
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from time import monotonic

import aiohttp
import pandas as pd
import polars as pl
import pytest
from cfb_data._catalog.models import CatalogCounts
from cfb_data._transport import _HTTPTransport, _ResponseEnvelope, _RetryDecision
from cfb_data.base.types import QueryParameters
from cfb_data.cache._redis import RedisCacheBackend
from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.cache.config import CachePolicyConfig, CacheProfile, CacheTTL
from cfb_data.errors import (
    CFBDCacheMissError,
    CFBDIdentityAmbiguityError,
    CFBDRateLimitError,
)
from cfb_data.tests._live_budget import LiveCallLedger
from cfb_data.tests._live_manifest import LIVE_ENDPOINT_CASES, LiveEndpointCase
from pydantic import BaseModel

from cfb_data import (
    CFBDClient,
    FreshnessMode,
    RedisCacheConfig,
    RetryPolicy,
    SQLiteCacheConfig,
)

_YEAR = 2024
_TEAM = "Michigan"
_OPPONENT = "Ohio State"
_CONFERENCE = "Big Ten"
_OPERATIONAL = frozenset({"/info", "/info/usage"})
type _BackendConfig = SQLiteCacheConfig | RedisCacheConfig


@dataclass(slots=True)
class _Seeds:
    """Carry non-secret selectors discovered from validated live results."""

    year: int = _YEAR
    team: str = _TEAM
    opponent: str = _OPPONENT
    conference: str = _CONFERENCE
    team_id: int | None = None
    team_abbreviation: str | None = None
    team_alias: str | None = None
    alias_team_id: int | None = None
    conference_id: int | None = None
    conference_abbreviation: str | None = None
    venue_id: int | None = None
    venue_name: str | None = None
    game_id: int | None = None
    week: int = 1
    athlete_id: str | None = None
    athlete_name: str = "Donovan Edwards"
    ambiguous_athlete_name: str | None = None
    overview_year: int = 2023
    overview_athlete_name: str = "Caleb Williams"
    overview_athlete_id: int | None = None
    coach_id: int | None = None
    live_game_id: int | None = None


@dataclass(frozen=True, slots=True)
class _Evidence:
    """Record redacted verification evidence for one route/backend pair."""

    backend: str
    endpoint: str
    row_count: int
    schema_digest: str
    local_replay: bool
    status: str
    attempts: int = 0
    reopen_replay: bool = False
    alternate_presentation: bool = False


@dataclass(frozen=True, slots=True)
class _IdentityEvidence:
    """Record one public identity or hydration operation without source data."""

    backend: str
    operation: str
    status: str


@dataclass(frozen=True, slots=True)
class _CatalogEvidence:
    """Record backend-neutral counts for all canonical catalog grains."""

    backend: str
    counts: dict[str, int]


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_all_public_routes_and_identities_with_sqlite_and_redis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate all 74 routes, cache replays, and identities on both stores."""
    if os.getenv("CFB_DATA_RUN_LIVE_API_ALL") != "1":
        pytest.skip("set CFB_DATA_RUN_LIVE_API_ALL=1 for exhaustive live testing")
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        pytest.skip("set CFBD_API_KEY for exhaustive live testing")
    redis_url = os.getenv("CFB_DATA_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")
    ledger_path = Path(
        os.getenv("CFB_DATA_LIVE_LEDGER", ".cfb-data-live/call-ledger.json")
    )
    ledger = LiveCallLedger(ledger_path)
    pacer = _AttemptPacer(minimum_interval_seconds=1.35)
    original_request = _HTTPTransport._request_once

    async def budgeted_request(
        transport: _HTTPTransport,
        *,
        session: aiohttp.ClientSession,
        url: str,
        endpoint: str,
        params: QueryParameters,
        attempt: int,
        conditional_headers: Mapping[str, str] | None,
    ) -> _ResponseEnvelope | _RetryDecision:
        await pacer.wait()
        ledger.reserve(endpoint)
        return await original_request(
            transport,
            session=session,
            url=url,
            endpoint=endpoint,
            params=params,
            attempt=attempt,
            conditional_headers=conditional_headers,
        )

    monkeypatch.setattr(_HTTPTransport, "_request_once", budgeted_request)
    retry_policy = RetryPolicy()
    selected_cases = _selected_cases()
    selected_backends = _selected_backends(
        sqlite_path=tmp_path / "live-all.sqlite3", redis_url=redis_url
    )

    async with CFBDClient(api_key, retry_policy=retry_policy) as preflight:
        account = await preflight.info.account()
    features = account.features
    assert account.patron_level >= 3
    assert all(
        (
            features.adjusted_metrics,
            features.weather,
            features.scoreboard,
            features.live_play_by_play,
        )
    )
    if account.remaining_calls is not None:
        required_attempts = (
            len(selected_cases) * len(selected_backends) * retry_policy.max_attempts
        )
        assert account.remaining_calls >= required_attempts

    redis_prefix = f"cfb-data-live-{uuid.uuid4().hex}"
    selected_backends = tuple(
        (
            name,
            RedisCacheConfig(url=redis_url, key_prefix=redis_prefix)
            if name == "redis"
            else backend,
        )
        for name, backend in selected_backends
    )
    evidence: list[_Evidence] = []
    identity_evidence: list[_IdentityEvidence] = []
    catalog_evidence: list[_CatalogEvidence] = []
    failures: list[str] = []
    try:
        for name, backend in selected_backends:
            (
                backend_evidence,
                backend_identity_evidence,
                backend_catalog_evidence,
                backend_failures,
            ) = await _exercise_backend(
                api_key,
                name=name,
                backend=backend,
                retry_policy=retry_policy,
                cases=selected_cases,
                ledger=ledger,
            )
            evidence.extend(backend_evidence)
            identity_evidence.extend(backend_identity_evidence)
            catalog_evidence.append(backend_catalog_evidence)
            failures.extend(backend_failures)
    finally:
        await _clean_redis_prefix(redis_url, redis_prefix)
        _write_report(
            Path(".cfb-data-live/live-api-all-report.json"),
            evidence,
            identity_evidence,
            catalog_evidence,
            failures,
            ledger,
        )

    assert not failures, "; ".join(failures)
    assert len(evidence) == len(selected_cases) * len(selected_backends)


async def _exercise_backend(
    api_key: str,
    *,
    name: str,
    backend: _BackendConfig,
    retry_policy: RetryPolicy,
    cases: tuple[LiveEndpointCase, ...],
    ledger: LiveCallLedger,
) -> tuple[
    list[_Evidence],
    list[_IdentityEvidence],
    _CatalogEvidence,
    list[str],
]:
    """Run the cold and immediate local-replay matrix for one backend."""
    seeds = _Seeds()
    evidence: list[_Evidence] = []
    identity_evidence: list[_IdentityEvidence] = []
    failures: list[str] = []
    policy = CachePolicyConfig(
        ttl_overrides={
            CacheProfile.live_plays: CacheTTL(
                fresh_for=timedelta(minutes=5), retain_for=timedelta(minutes=30)
            ),
            CacheProfile.live_scoreboard: CacheTTL(
                fresh_for=timedelta(minutes=5), retain_for=timedelta(minutes=30)
            ),
        }
    )
    async with CFBDClient(
        api_key,
        cache=backend,
        retry_policy=retry_policy,
        cache_policy=policy,
    ) as client:
        for case in cases:
            attempts_before = ledger.snapshot().spent
            try:
                result = await _invoke(client, case, seeds)
                _update_seeds(case.endpoint, result, seeds)
                digest = _result_digest(result)
                replayed = False
                if case.endpoint in _OPERATIONAL:
                    with client.cache_mode("local_only"):
                        with pytest.raises(CFBDCacheMissError):
                            await _invoke(client, case, seeds)
                else:
                    with client.cache_mode("local_only"):
                        replay = await _invoke(client, case, seeds)
                    assert _result_digest(replay) == digest
                    replayed = True
                evidence.append(
                    _Evidence(
                        backend=name,
                        endpoint=case.endpoint,
                        row_count=_row_count(result),
                        schema_digest=_schema_digest(result),
                        local_replay=replayed,
                        status="passed",
                        attempts=ledger.snapshot().spent - attempts_before,
                    )
                )
            except Exception as exc:
                if isinstance(exc, CFBDRateLimitError):
                    raise
                failures.append(f"{name}:{case.endpoint}:{type(exc).__name__}")
                evidence.append(
                    _Evidence(
                        name,
                        case.endpoint,
                        0,
                        "",
                        False,
                        "failed",
                        ledger.snapshot().spent - attempts_before,
                    )
                )
        if len(cases) == len(LIVE_ENDPOINT_CASES):
            try:
                identity_evidence.extend(
                    await _exercise_identity_operations(
                        client, backend=name, seeds=seeds
                    )
                )
                identity_evidence.append(
                    await _exercise_hydration(client, backend=name, year=seeds.year)
                )
            except Exception as exc:
                if isinstance(exc, CFBDRateLimitError):
                    raise
                failures.append(f"{name}:identities:{type(exc).__name__}")
    try:
        evidence = await _verify_reopen_with_polars(
            api_key,
            backend=backend,
            retry_policy=retry_policy,
            policy=policy,
            cases=cases,
            seeds=seeds,
            evidence=evidence,
            ledger=ledger,
        )
    except Exception as exc:
        if isinstance(exc, CFBDRateLimitError):
            raise
        failures.append(f"{name}:reopen:{type(exc).__name__}")
    counts = await _catalog_counts(backend)
    return (
        evidence,
        identity_evidence,
        _CatalogEvidence(name, asdict(counts)),
        failures,
    )


async def _exercise_identity_operations(
    client: CFBDClient[pd.DataFrame], *, backend: str, seeds: _Seeds
) -> list[_IdentityEvidence]:
    """Exercise all eight resolver operations strictly from the local catalog."""
    team_id = seeds.team_id
    team_abbreviation = seeds.team_abbreviation
    team_alias = seeds.team_alias
    alias_team_id = seeds.alias_team_id
    conference_id = seeds.conference_id
    conference_abbreviation = seeds.conference_abbreviation
    venue_id = seeds.venue_id
    venue_name = seeds.venue_name
    game_id = seeds.game_id
    athlete_id = seeds.athlete_id
    required = (
        team_id,
        team_abbreviation,
        team_alias,
        alias_team_id,
        conference_id,
        conference_abbreviation,
        venue_id,
        venue_name,
        game_id,
        athlete_id,
    )
    if any(value is None for value in required):
        raise AssertionError("Live bootstrap did not yield every identity selector")
    assert isinstance(team_id, int)
    assert isinstance(team_abbreviation, str)
    assert isinstance(team_alias, str)
    assert isinstance(alias_team_id, int)
    assert isinstance(conference_id, int)
    assert isinstance(conference_abbreviation, str)
    assert isinstance(venue_id, int)
    assert isinstance(venue_name, str)
    assert isinstance(game_id, int)
    assert isinstance(athlete_id, str)
    evidence: list[_IdentityEvidence] = []
    freshness = FreshnessMode.local_only
    with client.cache_mode("local_only"):
        team = await client.identities.teams.resolve(team_id, freshness=freshness)
        assert team.school == seeds.team
        await client.identities.teams.resolve(team_abbreviation, freshness=freshness)
        alias_team = await client.identities.teams.resolve(
            team_alias, freshness=freshness
        )
        assert alias_team.id == alias_team_id
        evidence.append(_IdentityEvidence(backend, "teams.resolve", "passed"))

        assert (
            await client.identities.teams.resolve_id(seeds.team, freshness=freshness)
            == team_id
        )
        evidence.append(_IdentityEvidence(backend, "teams.resolve_id", "passed"))
        assert (
            await client.identities.teams.resolve_name(team_id, freshness=freshness)
            == seeds.team
        )
        evidence.append(_IdentityEvidence(backend, "teams.resolve_name", "passed"))

        conference = await client.identities.conferences.resolve(
            conference_abbreviation, freshness=freshness
        )
        assert conference.id == conference_id
        evidence.append(_IdentityEvidence(backend, "conferences.resolve", "passed"))

        venue = await client.identities.venues.resolve(venue_name, freshness=freshness)
        assert venue.id == venue_id
        evidence.append(_IdentityEvidence(backend, "venues.resolve", "passed"))

        game = await client.identities.games.resolve(
            game_id=game_id, freshness=freshness
        )
        assert game.id == game_id
        evidence.append(_IdentityEvidence(backend, "games.resolve", "passed"))

        games = await client.identities.games.find(
            season=seeds.year,
            week=seeds.week,
            team=seeds.team,
            freshness=freshness,
        )
        assert game_id in {item.id for item in games}
        evidence.append(_IdentityEvidence(backend, "games.find", "passed"))

        athlete = await client.identities.athletes.resolve(
            name=seeds.athlete_name,
            team=seeds.team,
            season=seeds.year,
            freshness=freshness,
        )
        assert athlete.id == athlete_id
        evidence.append(_IdentityEvidence(backend, "athletes.resolve", "passed"))
        if seeds.ambiguous_athlete_name is not None:
            with pytest.raises(CFBDIdentityAmbiguityError):
                await client.identities.athletes.resolve(
                    name=seeds.ambiguous_athlete_name,
                    team=seeds.team,
                    season=seeds.year,
                    freshness=freshness,
                )
            evidence.append(
                _IdentityEvidence(
                    backend,
                    "athletes.natural_ambiguity",
                    "passed",
                )
            )
    return evidence


async def _exercise_hydration(
    client: CFBDClient[pd.DataFrame], *, backend: str, year: int
) -> _IdentityEvidence:
    """Exercise dry-run, sequential hydration, resumability, and zero-work replay."""
    before = await client.identities.hydrate(
        seasons=[year],
        classification="fbs",
        include_vocabularies=True,
        dry_run=True,
        max_concurrency=1,
    )
    actual = await client.identities.hydrate(
        seasons=[year],
        classification="fbs",
        include_vocabularies=True,
        max_concurrency=1,
    )
    after = await client.identities.hydrate(
        seasons=[year],
        classification="fbs",
        include_vocabularies=True,
        dry_run=True,
        max_concurrency=1,
    )
    assert before.planned_calls == actual.completed_calls
    assert actual.completed_calls > 0
    assert after.planned_calls == 0
    return _IdentityEvidence(backend, "identities.hydrate", "passed")


async def _verify_reopen_with_polars(
    api_key: str,
    *,
    backend: _BackendConfig,
    retry_policy: RetryPolicy,
    policy: CachePolicyConfig,
    cases: tuple[LiveEndpointCase, ...],
    seeds: _Seeds,
    evidence: list[_Evidence],
    ledger: LiveCallLedger,
) -> list[_Evidence]:
    """Reopen retained responses through Polars without a transport attempt."""
    before = ledger.snapshot().spent
    by_endpoint = {item.endpoint: item for item in evidence}
    updated: dict[str, _Evidence] = {}
    async with CFBDClient(
        api_key,
        dataframe_backend="polars",
        cache=backend,
        retry_policy=retry_policy,
        cache_policy=policy,
    ) as client:
        for case in cases:
            original = by_endpoint[case.endpoint]
            if original.status != "passed":
                continue
            with client.cache_mode("local_only"):
                if case.endpoint in _OPERATIONAL:
                    with pytest.raises(CFBDCacheMissError):
                        await _invoke(client, case, seeds)
                    continue
                replay = await _invoke(client, case, seeds)
            assert _row_count(replay) == original.row_count
            updated[case.endpoint] = replace(
                original,
                reopen_replay=True,
                alternate_presentation=True,
            )
    assert ledger.snapshot().spent == before
    return [updated.get(item.endpoint, item) for item in evidence]


async def _catalog_counts(backend: _BackendConfig) -> CatalogCounts:
    """Reopen one backend through the neutral catalog inspection contract."""
    inspector = (
        SQLiteCacheBackend(backend)
        if isinstance(backend, SQLiteCacheConfig)
        else RedisCacheBackend(backend)
    )
    await inspector.open()
    try:
        counts = await inspector.catalog_counts()
    finally:
        await inspector.close()
    assert len(asdict(counts)) == 15
    return counts


def _selected_cases() -> tuple[LiveEndpointCase, ...]:
    """Return all manifest cases or an explicit iterative diagnostic subset."""
    raw = os.getenv("CFB_DATA_LIVE_ENDPOINTS")
    if not raw:
        return LIVE_ENDPOINT_CASES
    requested = {endpoint.strip() for endpoint in raw.split(",") if endpoint.strip()}
    known = {case.endpoint for case in LIVE_ENDPOINT_CASES}
    unknown = requested - known
    if unknown:
        raise ValueError(f"Unknown live endpoint selection: {sorted(unknown)}")
    return tuple(case for case in LIVE_ENDPOINT_CASES if case.endpoint in requested)


def _selected_backends(
    *, sqlite_path: Path, redis_url: str
) -> tuple[tuple[str, _BackendConfig], ...]:
    """Return both backends or an explicit iterative diagnostic subset."""
    raw = os.getenv("CFB_DATA_LIVE_BACKENDS", "sqlite,redis")
    requested = {name.strip() for name in raw.split(",") if name.strip()}
    unknown = requested - {"sqlite", "redis"}
    if unknown or not requested:
        raise ValueError(f"Unknown live backend selection: {sorted(unknown)}")
    configurations: dict[str, _BackendConfig] = {
        "sqlite": SQLiteCacheConfig(path=sqlite_path),
        "redis": RedisCacheConfig(url=redis_url, key_prefix="pending"),
    }
    return tuple(
        (name, configurations[name])
        for name in ("sqlite", "redis")
        if name in requested
    )


async def _invoke[FrameT](
    client: CFBDClient[FrameT], case: LiveEndpointCase, seeds: _Seeds
) -> object:
    """Invoke one public resource method using narrow validated selectors."""
    resource = getattr(client, case.resource)
    method: Callable[..., Awaitable[object]] = getattr(resource, case.method)
    return await method(**_filters(case.endpoint, seeds))


def _filters(endpoint: str, seeds: _Seeds) -> dict[str, object]:
    """Return a narrow selector set for one live endpoint."""
    game_id = (
        seeds.live_game_id or seeds.game_id
        if endpoint == "/live/plays"
        else seeds.game_id
    )
    mapping: dict[str, dict[str, object]] = {
        "/teams/fbs": {"year": seeds.year},
        "/conferences": {"year": seeds.year},
        "/games": {"year": seeds.year, "team": seeds.team},
        "/scoreboard": {"classification": "fbs"},
        "/roster": {"year": seeds.year, "team": seeds.team},
        "/coaches": {"year": seeds.year, "team": seeds.team},
        "/info/usage": {"days": 1, "limit": 10, "api": "cfb"},
        "/calendar": {"year": seeds.year},
        "/coaches/profile": {"coach_id": seeds.coach_id},
        "/coaches/seasons": {"coach_id": seeds.coach_id},
        "/coaches/tenures": {"coach_id": seeds.coach_id},
        "/conferences/affiliations": {"team": seeds.team, "year": seeds.year},
        "/conferences/changes": {"year": seeds.year},
        "/draft/picks": {"year": seeds.year, "school": seeds.team},
        "/drives": {"year": seeds.year, "week": seeds.week, "team": seeds.team},
        "/game/box/advanced": {"game_id": seeds.game_id},
        "/games/media": {"year": seeds.year, "team": seeds.team},
        "/games/players": {"game_id": seeds.game_id},
        "/games/teams": {"game_id": seeds.game_id},
        "/games/weather": {"game_id": seeds.game_id},
        "/lines": {"game_id": seeds.game_id},
        "/live/plays": {"game_id": game_id},
        "/metrics/wp": {"game_id": seeds.game_id},
        "/metrics/wp/pregame": {"year": seeds.year, "team": seeds.team},
        "/player/portal": {"year": seeds.year},
        "/player/returning": {"year": seeds.year, "team": seeds.team},
        "/player/search": {
            "search_term": seeds.overview_athlete_name,
            "year": seeds.overview_year,
            "team": "USC",
        },
        "/player/season/overview": {
            "year": seeds.overview_year,
            "player_id": seeds.overview_athlete_id,
        },
        "/player/usage": {
            "year": seeds.year,
            "team": seeds.team,
            "player_id": seeds.athlete_id,
        },
        "/playoffs/cfp": {"year": seeds.year},
        "/playoffs/cfp/games": {"year": seeds.year},
        "/playoffs/cfp/participants": {"year": seeds.year},
        "/plays": {"year": seeds.year, "week": seeds.week, "team": seeds.team},
        "/plays/stats": {"game_id": seeds.game_id},
        "/ppa/games": {"year": seeds.year, "team": seeds.team},
        "/ppa/players/games": {
            "year": seeds.year,
            "team": seeds.team,
            "player_id": seeds.athlete_id,
        },
        "/ppa/players/season": {
            "year": seeds.year,
            "player_id": seeds.athlete_id,
        },
        "/ppa/predicted": {"down": 1, "distance": 10},
        "/ppa/teams": {"year": seeds.year, "team": seeds.team},
        "/rankings": {"year": seeds.year},
        "/ratings/core": {"year": seeds.year, "team": seeds.team},
        "/ratings/elo": {"year": seeds.year, "team": seeds.team},
        "/ratings/fpi": {"year": seeds.year, "team": seeds.team},
        "/ratings/sp": {"year": seeds.year, "team": seeds.team},
        "/ratings/sp/conferences": {"year": seeds.year, "conference": seeds.conference},
        "/ratings/srs": {"year": seeds.year, "team": seeds.team},
        "/ratings/srs/expanded": {"year": seeds.year, "team": seeds.team},
        "/records": {"year": seeds.year, "team": seeds.team},
        "/recruiting/groups": {"team": seeds.team, "start_year": seeds.year},
        "/recruiting/players": {"year": seeds.year, "team": seeds.team},
        "/recruiting/teams": {"year": seeds.year, "team": seeds.team},
        "/stats/game/advanced": {"year": seeds.year, "team": seeds.team},
        "/stats/game/havoc": {"year": seeds.year, "team": seeds.team},
        "/stats/player/season": {"year": seeds.year, "team": seeds.team},
        "/stats/player/success": {"year": seeds.year, "team": seeds.team},
        "/stats/player/success/game": {"year": seeds.year, "team": seeds.team},
        "/stats/season": {"year": seeds.year, "team": seeds.team},
        "/stats/season/advanced": {"year": seeds.year, "team": seeds.team},
        "/talent": {"year": seeds.year},
        "/teams/ats": {"year": seeds.year, "team": seeds.team},
        "/teams/matchup": {"team1": seeds.team, "team2": seeds.opponent},
        "/wepa/players/kicking": {"year": seeds.year, "team": seeds.team},
        "/wepa/players/passing": {"year": seeds.year, "team": seeds.team},
        "/wepa/players/rushing": {"year": seeds.year, "team": seeds.team},
        "/wepa/team/season": {"year": seeds.year, "team": seeds.team},
    }
    return {
        key: value
        for key, value in mapping.get(endpoint, {}).items()
        if value is not None
    }


def _update_seeds(endpoint: str, result: object, seeds: _Seeds) -> None:
    """Reuse identifiers from already validated bootstrap responses."""
    if not isinstance(result, pd.DataFrame) or result.empty:
        return
    row = result.iloc[0]
    if endpoint == "/teams":
        matching = result[result["school"] == seeds.team]
        if not matching.empty:
            row = matching.iloc[0]
        seeds.team_id = int(row["id"])
        abbreviation = row.get("abbreviation")
        if isinstance(abbreviation, str) and abbreviation:
            seeds.team_abbreviation = abbreviation
        aliases = row.get("alternate_names")
        if isinstance(aliases, list | tuple) and aliases:
            seeds.team_alias = str(aliases[0])
        for _, candidate in result.iterrows():
            candidate_aliases = candidate.get("alternate_names")
            if not isinstance(candidate_aliases, list | tuple):
                continue
            canonical = {
                str(candidate.get("school", "")).casefold(),
                str(candidate.get("abbreviation", "")).casefold(),
            }
            distinct = next(
                (
                    str(alias)
                    for alias in candidate_aliases
                    if str(alias).casefold() not in canonical
                ),
                None,
            )
            if distinct is not None:
                seeds.team_alias = distinct
                seeds.alias_team_id = int(candidate["id"])
                break
    elif endpoint == "/conferences":
        matching = result[result["name"] == seeds.conference]
        if not matching.empty:
            row = matching.iloc[0]
        seeds.conference_id = int(row["id"])
        abbreviation = row.get("abbreviation")
        if isinstance(abbreviation, str) and abbreviation:
            seeds.conference_abbreviation = abbreviation
    elif endpoint == "/venues":
        seeds.venue_id = int(row["id"])
        seeds.venue_name = str(row["name"])
    elif endpoint == "/games":
        seeds.game_id = int(row["id"])
        seeds.week = int(row["week"])
        home = str(row["home_team"])
        away = str(row["away_team"])
        seeds.opponent = away if home == seeds.team else home
    elif endpoint == "/roster":
        roster_names = [
            f"{candidate['first_name']} {candidate['last_name']}".strip()
            for _, candidate in result.iterrows()
        ]
        counts = {name: roster_names.count(name) for name in roster_names}
        for (_, candidate), name in zip(result.iterrows(), roster_names, strict=True):
            if counts[name] == 1:
                seeds.athlete_id = str(candidate["id"])
                seeds.athlete_name = name
                break
        seeds.ambiguous_athlete_name = next(
            (name for name in roster_names if counts[name] > 1),
            None,
        )
    elif endpoint == "/player/search":
        matching = result[result["name"] == seeds.overview_athlete_name]
        if not matching.empty:
            seeds.overview_athlete_id = int(matching.iloc[0]["id"])
    elif endpoint == "/coaches":
        seeds.coach_id = int(row["id"])
    elif endpoint == "/scoreboard" and "status" in result.columns:
        in_progress = result[result["status"] == "in_progress"]
        if not in_progress.empty:
            seeds.live_game_id = int(in_progress.iloc[0]["id"])


def _result_digest(result: object) -> str:
    """Return a non-reversible equality digest without logging response content."""
    if isinstance(result, pd.DataFrame):
        payload = result.to_json(orient="table", date_format="iso")
    elif isinstance(result, pl.DataFrame):
        payload = result.write_json()
    elif isinstance(result, BaseModel):
        payload = result.model_dump_json(by_alias=True)
    else:
        payload = repr(result)
    return hashlib.sha256(payload.encode()).hexdigest()


def _schema_digest(result: object) -> str:
    """Return a digest of result type and tabular schema only."""
    if isinstance(result, pd.DataFrame):
        schema = [(str(column), str(dtype)) for column, dtype in result.dtypes.items()]
    elif isinstance(result, pl.DataFrame):
        schema = [(name, str(dtype)) for name, dtype in result.schema.items()]
    elif isinstance(result, BaseModel):
        schema = sorted(type(result).model_fields)
    else:
        schema = [type(result).__qualname__]
    return hashlib.sha256(json.dumps(schema).encode()).hexdigest()


def _row_count(result: object) -> int:
    """Return a safe aggregate result count."""
    if isinstance(result, pd.DataFrame):
        return len(result.index)
    if isinstance(result, pl.DataFrame):
        return result.height
    return 1


async def _clean_redis_prefix(url: str, prefix: str) -> None:
    """Delete only keys belonging to this run using bounded scans."""
    from redis.asyncio import Redis

    client = Redis.from_url(url, decode_responses=False)
    try:
        batch: list[bytes] = []
        async for key in client.scan_iter(match=f"{prefix}:*", count=100):
            batch.append(key)
            if len(batch) == 100:
                await client.delete(*batch)
                batch.clear()
        if batch:
            await client.delete(*batch)
    finally:
        await client.aclose()


def _write_report(
    report_path: Path,
    evidence: list[_Evidence],
    identity_evidence: list[_IdentityEvidence],
    catalog_evidence: list[_CatalogEvidence],
    failures: list[str],
    ledger: LiveCallLedger,
) -> None:
    """Write redacted local evidence outside version-controlled paths."""
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "versions": {
            "cfb_data": version("cfb-data"),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "polars": pl.__version__,
        },
        "ledger": asdict(ledger.snapshot()),
        "summary": {
            "route_cases": len(evidence),
            "route_passes": sum(item.status == "passed" for item in evidence),
            "identity_passes": sum(
                item.status == "passed" for item in identity_evidence
            ),
        },
        "routes": [asdict(evidence_item) for evidence_item in evidence],
        "identities": [asdict(item) for item in identity_evidence],
        "catalogs": [asdict(item) for item in catalog_evidence],
        "failures": failures,
        "cleanup": "owned Redis prefix removed; SQLite database managed by pytest",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))


def _git_sha() -> str:
    """Return the current commit identifier without including working-tree data."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class _AttemptPacer:
    """Keep sequential live dispatch below the provider's burst threshold."""

    def __init__(self, *, minimum_interval_seconds: float) -> None:
        self._minimum_interval_seconds = minimum_interval_seconds
        self._lock = asyncio.Lock()
        self._last_dispatch = 0.0

    async def wait(self) -> None:
        """Wait until one more request may be dispatched sequentially."""
        async with self._lock:
            delay = self._minimum_interval_seconds - (monotonic() - self._last_dispatch)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_dispatch = monotonic()
