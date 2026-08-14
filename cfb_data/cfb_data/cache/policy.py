"""Apply built-in endpoint and response-state cache freshness policy."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from cfb_data.base.types import QueryParameters
from cfb_data.cache.config import (
    CachePolicyConfig,
    CacheProfile,
    CacheTTL,
)

_DEFAULT_TTLS: dict[CacheProfile, CacheTTL] = {
    CacheProfile.stable_reference: CacheTTL(
        fresh_for=timedelta(days=180), retain_for=timedelta(days=730)
    ),
    CacheProfile.reference_vocabulary: CacheTTL(
        fresh_for=timedelta(days=365), retain_for=timedelta(days=1825)
    ),
    CacheProfile.roster: CacheTTL(
        fresh_for=timedelta(days=7), retain_for=timedelta(days=30)
    ),
    CacheProfile.schedule: CacheTTL(
        fresh_for=timedelta(days=3), retain_for=timedelta(days=14)
    ),
    CacheProfile.active_season: CacheTTL(
        fresh_for=timedelta(days=1), retain_for=timedelta(days=14)
    ),
    CacheProfile.recruiting: CacheTTL(
        fresh_for=timedelta(days=3), retain_for=timedelta(days=30)
    ),
    CacheProfile.historical: CacheTTL(
        fresh_for=timedelta(days=365), retain_for=timedelta(days=1825)
    ),
    CacheProfile.betting: CacheTTL(
        fresh_for=timedelta(minutes=15), retain_for=timedelta(hours=6)
    ),
    CacheProfile.weather: CacheTTL(
        fresh_for=timedelta(hours=1), retain_for=timedelta(hours=12)
    ),
    CacheProfile.live_scoreboard: CacheTTL(
        fresh_for=timedelta(seconds=15), retain_for=timedelta(minutes=2)
    ),
    CacheProfile.live_plays: CacheTTL(
        fresh_for=timedelta(seconds=5), retain_for=timedelta(seconds=30)
    ),
}

_STABLE_ENDPOINTS = frozenset(
    {"/teams", "/teams/fbs", "/venues", "/conferences", "/conferences/affiliations"}
)
_VOCABULARY_ENDPOINTS = frozenset(
    {
        "/plays/types",
        "/plays/stats/types",
        "/stats/categories",
        "/draft/teams",
        "/draft/positions",
    }
)


def cache_profile(endpoint: str) -> CacheProfile:
    """Return the semantic profile that owns an endpoint's base policy."""
    if endpoint in {"/info", "/info/usage"}:
        return CacheProfile.operational
    if endpoint in _STABLE_ENDPOINTS:
        return CacheProfile.stable_reference
    if endpoint in _VOCABULARY_ENDPOINTS:
        return CacheProfile.reference_vocabulary
    if endpoint == "/roster":
        return CacheProfile.roster
    if endpoint in {"/games", "/calendar", "/games/media"}:
        return CacheProfile.schedule
    if endpoint == "/scoreboard":
        return CacheProfile.live_scoreboard
    if endpoint == "/live/plays":
        return CacheProfile.live_plays
    if endpoint == "/games/weather":
        return CacheProfile.weather
    if endpoint == "/lines":
        return CacheProfile.betting
    if endpoint.startswith("/recruiting") or endpoint == "/player/portal":
        return CacheProfile.recruiting
    return CacheProfile.active_season


def resolve_ttl(
    *,
    profile: CacheProfile,
    endpoint: str,
    parameters: QueryParameters,
    value: BaseModel | Sequence[BaseModel] | Sequence[object],
    policy: CachePolicyConfig,
    now: datetime,
) -> CacheTTL | None:
    """Return configured TTL refined by current validated response state."""
    if profile is CacheProfile.operational:
        return None
    base = policy.ttl_overrides.get(profile, _DEFAULT_TTLS[profile])
    if (
        endpoint == "/games"
        and value
        and all(_is_closed_game(item, now) for item in value)
    ):
        base = policy.ttl_overrides.get(
            CacheProfile.historical,
            _DEFAULT_TTLS[CacheProfile.historical],
        )

    row_count = len(value) if isinstance(value, Sequence) else 1
    year = parameters.get("year")
    if row_count == 0 and isinstance(year, int):
        if _is_closed_season(year, now):
            base = policy.ttl_overrides.get(
                CacheProfile.historical,
                _DEFAULT_TTLS[CacheProfile.historical],
            )
        elif year >= now.year:
            base = CacheTTL(
                fresh_for=min(base.fresh_for, timedelta(days=1)),
                retain_for=base.retain_for,
            )

    refinements = [base]

    if endpoint == "/games" and isinstance(value, Sequence):
        for item in value:
            if not isinstance(item, BaseModel):
                continue
            completed = getattr(item, "completed", None)
            start_date = getattr(item, "start_date", None)
            if not isinstance(start_date, datetime):
                continue
            start_date = start_date.astimezone(UTC)
            if completed is False and abs(start_date - now) <= timedelta(hours=48):
                refinements.append(
                    CacheTTL(
                        fresh_for=timedelta(hours=24),
                        retain_for=timedelta(days=7),
                    )
                )
            if completed is True and now - start_date <= timedelta(hours=72):
                refinements.append(
                    CacheTTL(
                        fresh_for=timedelta(hours=24),
                        retain_for=timedelta(days=30),
                    )
                )
    return min(refinements, key=lambda ttl: ttl.fresh_for)


def _is_closed_game(item: object, now: datetime) -> bool:
    """Return whether a validated game is safely outside correction cadence."""
    if not isinstance(item, BaseModel) or getattr(item, "completed", None) is not True:
        return False
    start_date = getattr(item, "start_date", None)
    return isinstance(start_date, datetime) and now - start_date.astimezone(
        UTC
    ) > timedelta(hours=72)


def _is_closed_season(year: int, now: datetime) -> bool:
    """Return whether an empty season partition is conservatively historical."""
    if year < now.year - 1:
        return True
    return year == now.year - 1 and (now.month, now.day) >= (3, 1)
