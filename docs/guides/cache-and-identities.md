# Cache responses and look up identities

You can use `cfb-data` without a cache. Add one when repeated API calls start
getting in the way of exploring the data.

| Setup | Try it when... |
| --- | --- |
| No persistent cache | You are making a few calls or trying an endpoint for the first time. |
| SQLite | You want notebook and script reruns to reuse data from one local file. |
| Redis | Several notebooks, scripts, or processes should share cached data—even on one computer. |

SQLite is the shortest path because it needs no extra service. Redis is an
equally valid local choice if you already use it, want concurrent processes to
share results, or may later move the cache to another machine.

## Why cache football data?

An analysis often changes much faster than its source data. A cache lets you:

- rerun a notebook without fetching the same season again;
- test new pandas or Polars transformations against the same input rows;
- reduce API calls while exploring several related endpoints;
- run from retained data with `local_only` mode; and
- build a small identity catalog for joining teams, games, venues, and athletes.

Caching does not change the DataFrame returned by an endpoint. It only changes
where the validated response comes from.

```text
                    cache miss
your analysis  ─────────────────►  CollegeFootballData API
      │                                      │
      │                                      ▼
      └──────── DataFrame ◄──────── validated response
                         │
                         ▼
                  SQLite or Redis
                    for next time
```

## Start with SQLite

SQLite support is included in the normal installation. With no path, the
library chooses the usual per-user cache directory for your operating system:

```python
from cfb_data import CFBDClient, SQLiteCacheConfig

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    games = await client.games.list(year=2025)
    same_games = await client.games.list(year=2025)  # served from the cache
```

Pass a path when you want the cache beside a project or dataset:

```python
from pathlib import Path

cache = SQLiteCacheConfig(path=Path(".cache/cfb-data.sqlite3"))
```

Keep the SQLite file on a local disk. If several computers need the same
cache, use Redis instead of putting the SQLite file on a network filesystem.

## Use Redis on your computer

Install the optional Redis client:

```shell
python -m pip install "cfb-data[redis]"
```

Then point the client at a local Redis:

```python
from cfb_data import CFBDClient, RedisCacheConfig

cache = RedisCacheConfig(url="redis://127.0.0.1:6379/0")

async with CFBDClient(cache=cache) as client:
    games = await client.games.list(year=2025)
```

The repository includes a loopback-only Redis setup for local scripts,
notebooks, and integration tests:

```shell
make redis-up
make test-redis
make redis-down
```

`make redis-down` keeps the named volume, so cached data is available when you
start Redis again. The default limit is 4 GB; set
`CFB_DATA_REDIS_MAXMEMORY=1gb`, for example, to use less memory.

## Choose cache behavior for one call

Most of the time, the default behavior is enough. Use a cache mode when an
analysis needs a fresh response or should avoid the network:

```python
async with CFBDClient(cache=cache) as client:
    normal = await client.games.list(year=2025)

    with client.cache_mode("refresh"):
        fresh = await client.games.list(year=2025)

    with client.cache_mode("bypass"):
        uncached = await client.games.list(year=2025)

    with client.cache_mode("local_only"):
        retained = await client.games.list(year=2025)
```

- `default` uses a fresh cached response and calls the API on a miss.
- `refresh` calls the API even if a fresh response is cached.
- `bypass` calls the API without reading or writing the cache.
- `local_only` reads retained data without making a network call. It normally
  leaves durable catalog state unchanged, but may repair the catalog from a
  retained response when projection metadata is missing or outdated.

## Measure cache performance and API attempts

Pass a `RetrievalStats` collector to see what the client actually did without
parsing logs:

```python
from cfb_data import CFBDClient, RetrievalStats, SQLiteCacheConfig

stats = RetrievalStats()

async with CFBDClient(cache=SQLiteCacheConfig(), observer=stats) as client:
    await client.games.list(year=2025)
    await client.games.list(year=2025)

snapshot = stats.snapshot()
print(f"retrievals: {snapshot.endpoint_retrievals}")
print(f"HTTP attempts: {snapshot.http_attempts}")
print(f"fresh cache hits: {snapshot.fresh_cache_hits}")
print(f"fresh hit rate: {snapshot.fresh_hit_rate}")
```

`http_attempts` counts every attempt started by the transport, including
retries and conditional revalidation requests. It is therefore the useful
client-side quota counter; a connection failure cannot prove whether the
provider received or billed the attempt. Backend failures are counted
separately from true cache misses.

See [Retrieval observability](../advanced/observability.md) for every counter,
per-endpoint snapshots, Redis process scope, and custom observer events.

## Resolve names and IDs

The same cache also remembers identities found in endpoint results. This is
useful when one endpoint uses a name and another expects a provider ID:

```python
from cfb_data import CFBDClient, SQLiteCacheConfig
from cfb_data.enums import teams

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    michigan = await client.identities.teams.resolve(teams.Michigan)
    stadium = await client.identities.venues.resolve("Michigan Stadium")
    game = await client.identities.games.resolve(game_id=401628347)

print(michigan.id, michigan.school)
print(stadium.id, stadium.name)
print(game.home_team_id, game.away_team_id)
```

Lookups use exact IDs, canonical names, abbreviations, and known alternate
names. Athlete names often need a team and season to distinguish people with
the same name:

```python
from cfb_data.enums import teams

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    athlete = await client.identities.athletes.resolve(
        name="Example Player",
        team=teams.Michigan,
        season=2025,
    )
```

## Troubleshooting

| What you see | What to try |
| --- | --- |
| `CFBDOptionalDependencyError` with Redis | Install `cfb-data[redis]` in the environment running the script. |
| `CFBDCacheMissError` in `local_only` mode | Make the same call once in default mode while network access is available. |
| `CFBDIdentityNotFoundError` | Fetch a related endpoint first, or hydrate the relevant identity data. |
| `CFBDIdentityAmbiguityError` | Add a team, season, or another supported scope to the lookup. |
| SQLite errors from a shared/network drive | Move the database to a local disk or switch to Redis. |
| Redis connection errors | Check that Redis is running and that the URL uses `redis://` or `rediss://`. |

## Go deeper

[Common notebook recipes](common-recipes.md) shows how to choose identity
results versus DataFrames and how to hydrate only the seasons and reference
data a notebook needs.

[Advanced cache and identity behavior](../advanced/cache-behavior.md) covers
freshness defaults, stale responses, identity hydration, remote Redis,
maintenance, and the exact lookup rules.
