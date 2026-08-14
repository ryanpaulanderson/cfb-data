# Response caching and identity lookup

`cfb-data` can persist validated API responses and the stable identities learned
from them. Caching is opt-in: `cache=None`, the default, preserves network-only
response behavior while keeping projected identities in a client-local
transient catalog. Choose SQLite for one machine or Redis for workers that need
to share responses, catalog facts, and refresh leases.

This persistence has two distinct lifecycles:

- The exact response cache retains non-executable JSON for a bounded time. A
  fresh exact match avoids an API request; a retained stale match can support
  conditional revalidation or narrowly defined stale-on-error behavior.
- The identity catalog stores normalized teams, conferences, venues, games,
  athletes, recruits, coaches, drives, plays, vocabularies, and their typed
  relationships. Facts and the coverage ledger do not expire with a response.

Neither component is a workflow checkpoint, public data mirror, or replacement
for the provider. Cache data remains private and rebuildable. Existing endpoint
methods always return complete upstream-shaped results in upstream order; the
cache never answers them by filtering a broader stored response.

Source-domain Pydantic models own all upstream field expectations and their
typed identity or relationship declarations. Context-dependent mappings such
as roster seasons, player stints, and nested game/drive/play relationships are
pure hooks beside those source models. The catalog owns normalized grains,
three-state observations, merge behavior, provenance, coverage, and indexes;
it does not copy upstream response models. Every identity lookup follows the
same projection and catalog path with transient memory, SQLite, or Redis.

Compact identity results live in their source domains and retain domain enums:
`TeamIdentity`, `ConferenceIdentity`, `VenueIdentity`, `GameIdentity`, and
`AthleteIdentity`. The `client.identities` namespace is the resolver and
hydration facade, not a second schema namespace.

## Use SQLite locally

`aiosqlite` is included in the normal installation. Pass an explicit path when
an application owns cache placement:

```python
from pathlib import Path

from cfb_data import CFBDClient, SQLiteCacheConfig

cache = SQLiteCacheConfig(path=Path(".cache/cfb-data.sqlite3"))

async with CFBDClient(cache=cache) as client:
    first = await client.games.list(year=2025)
    second = await client.games.list(year=2025)  # validated cache hit
```

Without `path`, the database is `cache-v1.sqlite3` under the platform's normal
per-user cache directory: `~/Library/Caches/cfb-data` on macOS,
`%LOCALAPPDATA%/cfb-data` on Windows, and `$XDG_CACHE_HOME/cfb-data` or
`~/.cache/cfb-data` on other systems. The parent and database receive private
permissions where the platform supports them.

SQLite uses WAL mode, a finite busy timeout, and one serialized connection per
client. It supports multiple local processes through database refresh leases,
but the database must remain on local storage. Do not use SQLite WAL on NFS or
as multi-host coordination. The installed package keeps SQLite DDL and queries
in dedicated `.sql` resources rendered by a strict Jinja loader. Jinja supplies
only validated SQL structure; all request and catalog values remain bound
SQLite parameters.

## Use shared Redis

Install the optional client and provide an explicit service location:

```shell
python -m pip install "cfb-data[redis]"
```

```python
import os

from cfb_data import CFBDClient, RedisCacheConfig

cache = RedisCacheConfig(
    url=os.environ["CFB_DATA_REDIS_URL"],
    key_prefix="my-private-cfb-data",
)

async with CFBDClient(cache=cache) as client:
    games = await client.games.list(year=2025)
```

The URL must use `redis://` or `rediss://`. The `redis` extra supplies one
pooled `redis.asyncio` client per `CFBDClient`; selecting Redis without the
extra raises `CFBDOptionalDependencyError`. A configured Redis backend never
silently falls back to SQLite.

For a hosted service:

- require `rediss://` TLS and normal certificate validation;
- put a scoped ACL username and password in an environment variable or secret
  manager, never source control;
- allow only the selected key prefix and the commands needed for strings,
  hashes, sets, transactions, expiry, and the lease scripts;
- keep finite connect and socket timeouts;
- enable durable persistence for the non-expiring catalog; and
- use an eviction policy such as `volatile-ttl`, which selects expiring
  response and lease keys instead of permanent catalog keys.

Use a dedicated Redis deployment if a hosted plan cannot guarantee that
non-expiring catalog keys are protected from eviction. Passwords are omitted
from configuration representations and logs, and source/query values are
hashed before they appear in Redis key names.

## Run the local Redis example

The repository includes [a Redis Dockerfile](../../docker/redis/Dockerfile), a
volume-backed AOF configuration, a health check, and
[`compose.redis.yaml`](../../compose.redis.yaml). It binds only
`127.0.0.1:6379` on the host and deliberately disables Redis protected mode
inside the development container. It is a local integration service, not a
production security configuration.

```shell
make redis-up
make test-redis
make redis-down
```

`make redis-down` preserves the named volume. The supplied Redis configuration
uses `appendonly yes`, `appendfsync everysec`, snapshotting, and
`maxmemory-policy volatile-ttl`, so eviction targets the expiring entry with
the shortest remaining lifetime and cannot directly select the non-expiring
catalog. The Compose default bounds Redis at 4 GB; override it with
`CFB_DATA_REDIS_MAXMEMORY` when the host allocation requires a different
limit. Add authentication and network isolation before adapting the example
beyond local development.

## Override freshness policy

Built-in policy is selected by semantic profile. Each policy has two durations:
`fresh_for` avoids network access and `retain_for` keeps the original validated
body available for revalidation and permitted stale use. Retention must be at
least freshness.

```python
from datetime import timedelta

from cfb_data import CachePolicyConfig, CacheProfile, CacheTTL, CFBDClient

policy = CachePolicyConfig(
    ttl_overrides={
        CacheProfile.roster: CacheTTL(
            fresh_for=timedelta(days=14),
            retain_for=timedelta(days=60),
        )
    },
    stale_if_error=True,
)

async with CFBDClient(cache=cache, cache_policy=policy) as client:
    roster = await client.teams.roster(year=2025)
```

The defaults are:

| Profile | Fresh | Retained | Representative data |
| --- | ---: | ---: | --- |
| Stable reference | 180 days | 730 days | Teams, conferences, venues, affiliations |
| Reference vocabulary | 365 days | 1,825 days | Play/stat types and draft vocabularies |
| Roster | 7 days | 30 days | Current or future roster snapshots |
| Schedule | 3 days | 14 days | Broad game schedules |
| Active season | 24 hours | 14 days | Rankings, ratings, records, and season statistics |
| Recruiting | 3 days | 30 days | Recruiting and portal data |
| Historical | 365 days | 1,825 days | Closed completed game data |
| Betting | 15 minutes | 6 hours | Lines and markets |
| Weather | 1 hour | 12 hours | Forecasts and conditions |
| Live scoreboard | 15 seconds | 2 minutes | Scoreboard data |
| Live plays | 5 seconds | 30 seconds | Active play-by-play |
| Operational | never | never | Account, usage, quota, and authorization data |

An imminent game or recently completed game uses 24-hour freshness. Mixed
responses use the shortest applicable policy. Empty current or future
partitions are fresh for at most 24 hours. A completed game is not historical
until it is outside the 72-hour correction window. Operational account routes
remain non-cacheable even when a policy override is supplied.

When a retained entry has an ETag or Last-Modified validator, refresh uses a
conditional request. After normal retries are exhausted, retained data may be
served only before its retention deadline and only for timeouts, connection or
truncation failures, or HTTP `408`, `429`, and `5xx`. Stale data never masks
authentication, authorization, invalid-request, redirect, decode, or response-
validation failures. Set `stale_if_error=False` to disable this behavior.

## Select behavior for one operation

Use the synchronous context returned by `cache_mode` inside the async client:

```python
async with CFBDClient(cache=cache) as client:
    with client.cache_mode("refresh"):
        refreshed = await client.games.list(year=2025)

    with client.cache_mode("bypass"):
        network_only = await client.games.list(year=2025)

    with client.cache_mode("local_only"):
        cached_only = await client.games.list(year=2025)
```

- `default` returns a fresh exact hit or refreshes a miss.
- `refresh` contacts the API even when the entry is fresh.
- `bypass` neither reads nor populates persistence.
- `local_only` forbids network I/O and raises `CFBDCacheMissError` when no
  retained validated response can answer. It also rejects operational routes
  and response calls on a client with persistence disabled.

Modes use `contextvars`, so a mode is local to the current asynchronous task.
Every hit is decoded and validated against the current Pydantic contract.
Corrupt, oversized, or incompatible entries are evicted and treated as misses.

## Resolve compact identities

`client.identities` returns immutable Pydantic models without constructing
Arrow tables or DataFrames:

```python
from cfb_data import CFBDClient, FreshnessMode, SQLiteCacheConfig

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    team = await client.identities.teams.resolve("Michigan")
    team_id = await client.identities.teams.resolve_id("MICH")
    school = await client.identities.teams.resolve_name(130)
    conference = await client.identities.conferences.resolve("B1G")
    venue = await client.identities.venues.resolve("Michigan Stadium")
    game = await client.identities.games.resolve(game_id=401628347)
    games = await client.identities.games.find(
        season=2025,
        week=1,
        team="Michigan",
    )
    athlete = await client.identities.athletes.resolve(
        name="Example Player",
        team="Michigan",
        season=2025,
    )

    offline_team = await client.identities.teams.resolve(
        "Michigan",
        freshness=FreshnessMode.local_only,
    )
```

Resolution tries an exact provider ID, then normalized exact canonical name,
abbreviation, or registered alternate name. Normalization is limited to
Unicode normalization, case folding, trimming, and whitespace normalization.
It never selects a fuzzy match. Multiple exact matches raise
`CFBDIdentityAmbiguityError` with candidate summaries; no match raises
`CFBDIdentityNotFoundError`. Athlete names commonly require team and season
scope.

Freshness modes are:

- `ensure_fresh` (default): refresh missing or stale coverage using the
  smallest canonical partition; a retryable API failure may use retained facts
  when stale-on-error policy permits it.
- `allow_stale`: return a known fact without spending API quota.
- `local_only`: forbid network access and query only the configured catalog or
  facts already projected into this client's transient catalog.

Normal endpoint calls enrich the same catalog after response validation, so
hydration is not the only source of identity facts.

## Hydrate canonical identity partitions

Hydration is explicit; entering a client never spends calls automatically. A
configured, available SQLite or Redis catalog is required so a run cannot
spend quota without preserving its progress. A dry run inspects fresh coverage
and reports the remaining endpoints:

```python
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
conferences, affiliations, plus one games and one broad roster call per season.
An optional `classification` scopes conferences, games, and rosters; FBS scope
also uses `/teams/fbs`, while other classifications retain the broad `/teams`
reference call because that endpoint has no classification filter. The call
formula is unchanged.
Including play types, play-stat types, and team-stat categories makes
`7 + 2S` calls. A completed partition commits independently; failed,
cancelled, or unstarted calls do not claim coverage, so the next run resumes
only missing or stale partitions. The ledger records the latest failed or
interrupted attempt for diagnosis and clears that failure metadata when the
partition later commits successfully. Player search is capped and is not used
as a broad enumeration source.

## Maintain, rebuild, and observe

Remove expired SQLite response bodies without deleting identities or coverage:

```python
async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    deleted = await client.cleanup_cache()
```

Redis expires response and temporary lease keys natively, so this method
normally returns zero for Redis. Catalog pruning is deliberately separate and
is not automatic.

The unreleased implementation starts with final SQLite and Redis version-1
layouts; it contains no compatibility aliases or migration path for earlier
experimental branch data. Normal endpoint calls fail open to the API with a
redacted backend-failure event and mirror validated facts into transient
memory. To rebuild, stop clients, preserve a backup if needed, remove the exact
SQLite cache file or the application's exact Redis key prefix, and hydrate
again. Never delete a broad Redis database or directory when only one
application namespace is in scope.

Debug logging distinguishes hits, misses, stale entries, revalidations,
refreshes, bypasses, local followers, distributed-lease waits, backend
failures, stale identity fallback, and corruption. Logs do not contain API
tokens, Redis passwords, response bodies, or raw query values.

For repository verification, `make test` keeps external integrations skipped.
`make test-redis` uses the local Compose service. `make test-live` loads
`CFBD_API_KEY` from the repository's untracked `.env` and performs one bounded
real `/teams` request followed by local-only response and identity checks.
`make test-live-all` runs the opt-in 74-route matrix against both SQLite and the
local Redis service. It uses the transport's normal bounded retry behavior and
a process-locked ledger that reserves every attempt, including retries, before
dispatch. Local reports, databases, and the ledger stay under ignored
`.cfb-data-live/`; no response body or credential is written to the report.
