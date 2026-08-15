# Getting started

This guide takes you from installation to a validated DataFrame without making
you learn the entire API first.

## Requirements

- Python 3.12 or 3.13.
- A [CollegeFootballData API key](https://collegefootballdata.com/).
- An async entry point. A complete script can use `asyncio.run()` as shown
  below; applications that already run an event loop can await the client
  directly.

## Install

pandas is the default DataFrame backend:

```shell
python -m pip install cfb-data
```

To use Polars instead:

```shell
python -m pip install "cfb-data[polars]"
```

SQLite response caching and identity lookup need no extra. Install the Redis
extra only for a shared Redis backend:

```shell
python -m pip install "cfb-data[redis]"
```

## Configure authentication

Set the API key in the environment so it does not appear in source code:

```shell
export CFBD_API_KEY="your-api-key"
```

An explicit non-empty `api_key` passed to {class}`cfb_data.CFBDClient` takes
precedence over `CFBD_API_KEY`. Passing an empty explicit value is an error; it
does not fall back to the environment.

## Make a first request

Create one client for a related group of calls and enter it with `async with`.
The client is one-shot: do not call it before entry, reuse it after exit, nest
its context, or enter the same instance twice.

```python
import asyncio

from cfb_data import CFBDClient


async def main() -> None:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024, team="Michigan")
        records = await client.games.records(year=2024, team="Michigan")

    print(games[["week", "home_team", "away_team", "home_points", "away_points"]])
    print(records)


asyncio.run(main())
```

Both calls return eager `pandas.DataFrame` objects. The session is pooled across
the two requests and closed when the context exits, including when a request
raises an exception.

The async boundary covers data retrieval and validation. Once the completed
frames are returned, calculations use normal synchronous pandas operations.
The client does not require a custom query or analysis layer:

```python
completed = games.dropna(subset=["home_points", "away_points"])
high_scoring = completed.assign(
    total_points=completed["home_points"] + completed["away_points"]
).sort_values("total_points", ascending=False)

print(high_scoring[["home_team", "away_team", "total_points"]].head())
```

## Choose an endpoint

Methods are grouped by subject on the client. For example:

```python
async with CFBDClient() as client:
    games = await client.games.list(year=2024, conference="SEC")
    drives = await client.drives.list(year=2024, team="Georgia")
    plays = await client.plays.list(year=2024, week=1, team="Georgia")
    team_stats = await client.stats.team_season(year=2024, team="Georgia")
    elo = await client.ratings.elo(year=2024, team="Georgia")
```

The [endpoint index](cfbd_api/README.md) lists every supported namespace and
links to its request and result details. The generated
[namespace API](reference/namespaces.rst) gives exact callable signatures.

## Pass a request model when filters are reused

Every filtered method accepts either keyword filters or one matching Pydantic
request model. The two styles produce the same request and cannot be mixed.

```python
from cfb_data import CFBDClient, GamesRequest, SeasonType

request = GamesRequest(
    year=2024,
    season_type=SeasonType.regular,
    conference="Big Ten",
)

async with CFBDClient() as client:
    games = await client.games.list(request)
```

See [Requests and allowed values](guides/requests.md) for validation rules,
enum strings, aliases, and failure behavior.

## Select Polars

Only client construction changes. Namespace names, request models, filters,
validation, row order, and logical schemas remain the same.

```python
from cfb_data import CFBDClient

async with CFBDClient(dataframe_backend="polars") as client:
    calendar = await client.games.calendar(year=2024)
```

Type checkers infer `pandas.DataFrame` for the default client and
`polars.DataFrame` when the literal backend is `"polars"`. See [Work with
results](guides/results.md) for examples and nested-value details.

## Handle failures

All library exceptions inherit from {class}`cfb_data.CFBDError`. Catch a
specific subclass when the recovery behavior differs:

```python
from cfb_data import (
    CFBDAuthenticationError,
    CFBDClient,
    CFBDRateLimitError,
    CFBDRequestValidationError,
)

try:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024)
except CFBDRequestValidationError:
    print("The filters are invalid; fix the request before retrying.")
except CFBDAuthenticationError:
    print("Check CFBD_API_KEY.")
except CFBDRateLimitError as exc:
    print(f"Rate limited after {exc.attempts} attempts.")
```

The [troubleshooting guide](guides/errors-and-retries.md) covers common errors
and when to handle them separately. The complete exception and retry reference
lives under [Advanced details](advanced/errors-and-retries.md).

## Avoid repeated calls and resolve IDs

Caching is opt-in. It is useful when a notebook or script repeatedly fetches
the same season while you change the analysis. SQLite is the simplest choice
and persists both responses and compact identity facts:

```python
from cfb_data import CFBDClient, SQLiteCacheConfig

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    games = await client.games.list(year=2025)
    michigan = await client.identities.teams.resolve("MICH")
    game = await client.identities.games.resolve(game_id=401628347)
```

Redis is also useful on one machine if you already have it running or want
several scripts to share cached data:

```python
from cfb_data import CFBDClient, RedisCacheConfig

cache = RedisCacheConfig(url="redis://127.0.0.1:6379/0")

async with CFBDClient(cache=cache) as client:
    games = await client.games.list(year=2025)
```

Install the optional client with `python -m pip install "cfb-data[redis]"`.
See [Cache responses and look up identities](guides/cache-and-identities.md)
for local SQLite and Redis examples, cache modes, identity lookup, and common
fixes.

## Where to go next

| If you want to... | Continue with... |
| --- | --- |
| Find another dataset or method | [CFBD endpoint reference](cfbd_api/README.md) |
| Find IDs, hydrate minimally, or gather several calls | [Common notebook recipes](guides/common-recipes.md) |
| Check allowed filters and enum values | [Requests and allowed values](guides/requests.md) |
| Flatten nested data or compare pandas and Polars | [Work with results](guides/results.md) |
| Reuse data across notebook runs | [Cache responses and look up identities](guides/cache-and-identities.md) |
| Diagnose an exception | [Troubleshooting requests](guides/errors-and-retries.md) |
| Tune exact behavior | [Advanced details](advanced/index.md) |
