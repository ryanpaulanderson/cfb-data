# Advanced cache and identity behavior

This page collects the detailed settings and edge cases behind the shorter
[caching and identity guide](../guides/cache-and-identities.md). Start there if
you only need to avoid repeated calls or resolve a team ID.

For a notebook-oriented explanation of minimal hydration, IDs, and full
endpoint results, see [Common notebook recipes](../guides/common-recipes.md).

## What is stored

Persistence contains two related kinds of data:

- The response cache stores validated JSON for an exact endpoint request. A
  fresh match avoids an API call. A retained stale match can support
  conditional requests or limited stale-on-error behavior.
- The identity catalog stores normalized teams, conferences, venues, games,
  athletes, and their relationships. Identity facts and the coverage ledger
  last beyond the response that originally supplied them.

Both are rebuildable. Endpoint calls still return complete upstream-shaped
results in upstream order; the cache does not answer a narrow request by
filtering a different cached response.

## Cache locations

Without an explicit SQLite path, the file is named `cache-v1.sqlite3` under:

- `~/Library/Caches/cfb-data` on macOS;
- `%LOCALAPPDATA%/cfb-data` on Windows; or
- `$XDG_CACHE_HOME/cfb-data` or `~/.cache/cfb-data` on other systems.

SQLite uses WAL mode and supports several local processes. Keep the file on
local storage; Redis is the better choice for multiple machines.

## Redis outside the local machine

Use an environment variable when the URL contains credentials or belongs to a
shared service:

```python
import os

from cfb_data import RedisCacheConfig

cache = RedisCacheConfig(
    url=os.environ["CFB_DATA_REDIS_URL"],
    key_prefix="my-cfb-data",
)
```

The URL accepts `redis://` or `rediss://`. Use `rediss://` when traffic crosses
an untrusted network, and keep credentials out of source control. Because
identity records do not expire automatically, choose Redis persistence and an
eviction policy that retain non-expiring keys. The included local Compose
configuration already uses AOF, snapshots, and `volatile-ttl` eviction.

## Freshness and retention

Each cache profile has two durations. `fresh_for` controls how long a response
can be returned without contacting the API. `retain_for` controls how long the
body remains available for conditional requests, `local_only`, or permitted
stale-on-error use.

| Profile | Fresh | Retained | Example data |
| --- | ---: | ---: | --- |
| Stable reference | 180 days | 730 days | Teams, conferences, venues, affiliations |
| Reference vocabulary | 365 days | 1,825 days | Play/stat types and draft vocabularies |
| Roster | 7 days | 30 days | Current or future rosters |
| Schedule | 3 days | 14 days | Broad game schedules |
| Active season | 24 hours | 14 days | Rankings, ratings, records, season statistics |
| Recruiting | 3 days | 30 days | Recruiting and transfer data |
| Historical | 365 days | 1,825 days | Completed game data |
| Betting | 15 minutes | 6 hours | Lines and markets |
| Weather | 1 hour | 12 hours | Forecasts and conditions |
| Live scoreboard | 15 seconds | 2 minutes | Scoreboard data |
| Live plays | 5 seconds | 30 seconds | Active play-by-play |
| Account | not cached | not cached | Account, usage, quota, authorization |

An imminent or recently completed game uses 24-hour freshness. Completed games
switch to the historical profile after a 72-hour correction window. Mixed
responses use the shortest relevant profile, and empty current or future
partitions stay fresh for at most 24 hours.

Override a profile at client construction:

```python
from datetime import timedelta

from cfb_data import (
    CachePolicyConfig,
    CacheProfile,
    CacheTTL,
    CFBDClient,
    SQLiteCacheConfig,
)

policy = CachePolicyConfig(
    ttl_overrides={
        CacheProfile.roster: CacheTTL(
            fresh_for=timedelta(days=14),
            retain_for=timedelta(days=60),
        )
    },
    stale_if_error=True,
)
cache = SQLiteCacheConfig()

async with CFBDClient(cache=cache, cache_policy=policy) as client:
    roster = await client.teams.roster(year=2025)
```

`retain_for` must be at least as long as `fresh_for`.

## Stale responses and validation

When a retained response has an ETag or Last-Modified value, a refresh can use
a conditional request. After normal retries are exhausted, retained data may
be used before its retention deadline for timeouts, connection failures,
truncated responses, or HTTP `408`, `429`, and `5xx` errors.

Stale data is not used for authentication, authorization, invalid-request,
redirect, decode, or response-validation errors. Set `stale_if_error=False` to
turn the behavior off.

Every cache hit is decoded and validated again with the current Pydantic model.
Corrupt, oversized, or incompatible entries are evicted and treated as misses.

`local_only` never performs HTTP. A retained response normally uses a read-only
durable catalog merge and mirrors the result into the client-local catalog. If
its projection metadata is missing or outdated, the client may durably
reproject that retained response to repair the catalog; a repair failure still
returns the validated response through the client-local projection.

## Exact identity matching

Identity resolution tries a provider ID first, followed by an exact normalized
canonical name, abbreviation, or known alternate name. Normalization applies
Unicode normalization, case folding, trimming, and whitespace normalization;
it does not make fuzzy guesses.

Multiple exact matches raise `CFBDIdentityAmbiguityError` with candidate
summaries. No match raises `CFBDIdentityNotFoundError`.

Freshness modes control whether a lookup can contact the API:

- `ensure_fresh` refreshes missing or stale coverage when needed.
- `allow_stale` returns a known fact without spending an API call.
- `local_only` queries only retained or client-local facts.

Normal endpoint calls add identity facts after response validation, so a
separate hydration step is not always necessary.

## Hydrate identity data ahead of time

Hydration fetches the common reference partitions explicitly and saves
progress to SQLite or Redis. A dry run reports the remaining calls:

```python
from cfb_data import CFBDClient, SQLiteCacheConfig

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    plan = await client.identities.hydrate(
        seasons=[2024, 2025],
        classification="fbs",
        include_vocabularies=True,
        dry_run=True,
    )
    print(plan.planned_calls, plan.endpoints)

    completed = await client.identities.hydrate(
        seasons=[2024, 2025],
        classification="fbs",
        include_vocabularies=True,
        max_concurrency=4,
    )
```

For `S` seasons, core hydration makes `4 + 2S` calls: teams, venues,
conferences, affiliations, and one games and roster call per season. Including
play types, play-stat types, and team-stat categories makes `7 + 2S` calls.
Completed partitions are saved independently, so another run resumes only the
missing or stale work.

## Cleanup and rebuilds

Remove expired SQLite response bodies without deleting identities:

```python
async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    deleted = await client.cleanup_cache()
```

Redis expires response and temporary lease keys itself, so this method normally
returns zero for Redis. Identity pruning is a separate manual action.

To rebuild, stop active clients, preserve a backup if useful, remove the exact
SQLite cache file or the application's exact Redis key prefix, and hydrate
again. Avoid removing unrelated Redis keys or neighboring files.

Debug logging distinguishes hits, misses, stale entries, revalidations,
refreshes, bypasses, followers, lease waits, backend failures, stale identity
fallback, and corruption. Logs omit API tokens, Redis passwords, response
bodies, and raw query values. For typed counters and events that do not depend
on log-message text, use [retrieval observability](observability.md).
