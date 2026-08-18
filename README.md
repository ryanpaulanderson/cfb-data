# College Football Data Python Toolkit

`cfb-data` 0.7.0 is a pre-alpha Python toolkit for exploring the public
[CollegeFootballData API](https://collegefootballdata.com/). Most calls return
eager pandas DataFrames that are ready for analysis. Polars is available as an
option, and a few naturally nested results return Pydantic models.

This project is aimed at data professionals, statisticians, students, and fans
who want to spend their time analyzing college football rather than writing an
HTTP client or cleaning up inconsistent response shapes.

## What can I use it for?

- Pull games, plays, drives, ratings, rosters, recruiting, betting, draft, and
  other CFBD data into Python.
- Explore one team or season in a notebook.
- Build repeatable pandas or Polars analyses across several endpoints.
- Cache responses locally so rerunning an analysis does not repeat every API
  call.
- Resolve team, venue, game, and athlete names and IDs when joining data.

The package validates requests and responses before building a DataFrame. That
work happens inside the client; using it does not require knowing Pydantic,
Arrow, HTTP retry logic, or the cache implementation.

## Install

Python 3.12 and 3.13 are supported. pandas and PyArrow are included:

```shell
python -m pip install cfb-data
```

For Polars:

```shell
python -m pip install "cfb-data[polars]"
```

For Redis caching:

```shell
python -m pip install "cfb-data[redis]"
```

SQLite caching is included in the normal installation.

## Make a first request

Get an API key from [CollegeFootballData](https://collegefootballdata.com/) and
put it in the environment:

```shell
export CFBD_API_KEY="your-api-key"
```

Then fetch a team's games and start using ordinary pandas operations:

```python
import asyncio

from cfb_data import CFBDClient
from cfb_data.enums import teams


async def main() -> None:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024, team=teams.Michigan)

    completed = games.dropna(subset=["home_points", "away_points"])
    high_scoring = completed.assign(
        total_points=completed["home_points"] + completed["away_points"]
    ).sort_values("total_points", ascending=False)

    columns = ["week", "home_team", "away_team", "total_points"]
    print(high_scoring[columns].head())


asyncio.run(main())
```

The `async with` block lets related calls share one HTTP session and closes it
when the block ends. Async is limited to gathering and validating data; the
pandas calculation starts synchronously after the completed frame is returned.

## Find the data you need

Methods are grouped by subject:

| Namespace | Examples |
| --- | --- |
| `client.games` | Schedules, results, records, scoreboards, weather, box scores |
| `client.plays` and `client.drives` | Play-by-play, drive summaries, play types |
| `client.teams`, `client.players`, `client.coaches` | Teams, rosters, player search, coaches |
| `client.stats`, `client.metrics`, `client.ratings` | Team and player stats, PPA, win probability, Elo, SP+, FPI |
| `client.rankings`, `client.betting` | Polls and betting lines |
| `client.recruiting`, `client.draft` | Recruits, transfer portal, NFL draft data |
| `client.playoffs`, `client.adjusted_metrics` | CFP brackets and adjusted team/player metrics |

The [endpoint reference](docs/cfbd_api/README.md) lists every method, filter,
access tier, and returned shape.

For notebook-sized examples that answer common questions, see [Common notebook
recipes](docs/guides/common-recipes.md). It covers IDs versus full DataFrames,
minimal cache hydration, season summaries, joins, and concurrent async calls.

## Pass filters

For one-off calls, use snake-case keyword filters:

```python
from cfb_data.enums import conferences

async with CFBDClient() as client:
    games = await client.games.list(
        year=2024,
        season_type="regular",
        conference=conferences.BIGTEN,
    )
```

Use a request model when the same validated filters are shared or reused:

```python
from cfb_data import CFBDClient, GamesRequest, SeasonType
from cfb_data.enums import conferences, teams

request = GamesRequest(
    year=2024,
    season_type=SeasonType.regular,
    team=teams.Michigan,
    conference=conferences.BIGTEN,
)

async with CFBDClient() as client:
    games = await client.games.list(request)
```

Unknown filters and invalid combinations fail before an API call. See
[Requests and allowed values](docs/guides/requests.md) for common patterns.
The `teams` and `conferences` string enums provide autocomplete-friendly names
that exactly match season-specific API values while remaining directly
comparable with returned DataFrame strings.

## Choose pandas or Polars

pandas is the default. Selecting Polars only changes client construction:

```python
from cfb_data import CFBDClient

async with CFBDClient(dataframe_backend="polars") as client:
    calendar = await client.games.calendar(year=2024)
```

The two backends preserve the same columns, row order, nulls, and logical
values. pandas keeps nested values as Python dictionaries and lists; Polars
uses native `Struct` and `List[Struct]` columns.

See [Work with results](docs/guides/results.md) for analysis examples and
nested data, or [Advanced result details](docs/advanced/result-details.md) for
the exact dtype and Arrow behavior.

## Avoid repeated API calls

You do not need a cache for quick experiments. Add one when a notebook or
script repeatedly requests the same data while the analysis changes.

SQLite is the easiest option:

```python
from cfb_data import CFBDClient, SQLiteCacheConfig
from cfb_data.enums import teams

async with CFBDClient(cache=SQLiteCacheConfig()) as client:
    games = await client.games.list(year=2025)
    repeated = await client.games.list(year=2025)  # reused locally
    michigan = await client.identities.teams.resolve(teams.Michigan)
```

Redis is also a good local option if you already run it or want several
notebooks, scripts, or processes to share one cache:

```python
from cfb_data import CFBDClient, RedisCacheConfig

cache = RedisCacheConfig(url="redis://127.0.0.1:6379/0")

async with CFBDClient(cache=cache) as client:
    games = await client.games.list(year=2025)
```

Add a bounded in-memory collector when you want to see whether calls reached
the API or were served from cache:

```python
from cfb_data import CFBDClient, RetrievalStats, SQLiteCacheConfig

stats = RetrievalStats()

async with CFBDClient(cache=SQLiteCacheConfig(), observer=stats) as client:
    await client.games.list(year=2025)
    await client.games.list(year=2025)

snapshot = stats.snapshot()
print(snapshot.http_attempts)       # actual client-side HTTP attempts
print(snapshot.fresh_cache_hits)    # fresh initial cache hits
print(snapshot.fresh_hit_rate)
```

See [Cache responses and look up
identities](docs/guides/cache-and-identities.md) for use cases, the included
local Redis setup, cache modes, observability, identity examples, and
troubleshooting.

## Troubleshooting

| What you see | Start here |
| --- | --- |
| API key or access error | Check `CFBD_API_KEY` and the endpoint's Patreon tier. |
| Invalid filter or selector | Compare the call with the [endpoint reference](docs/cfbd_api/README.md). |
| Rate-limit error | Wait before retrying; consider SQLite or Redis for repeated calls. |
| Unexpected pandas dtype or nested value | See [Work with results](docs/guides/results.md). |
| Cache or identity lookup error | See [Cache troubleshooting](docs/guides/cache-and-identities.md#troubleshooting). |
| Another library exception | See [Troubleshooting requests](docs/guides/errors-and-retries.md). |

## Documentation

The [complete documentation](https://ryanpaulanderson.github.io/cfb-data/)
is organized in layers:

- **Start and use:** installation, examples, requests, results, caching, and
  troubleshooting, including [common notebook
  recipes](docs/guides/common-recipes.md).
- **Advanced details:** exact enum values, dtypes, TTLs, retries, and storage
  behavior.
- **Project internals:** architecture decisions and contributor-facing design.

The [product constitution](docs/product-constitution.md) is the concise north
star used to evaluate product and engineering decisions.

The project is pre-alpha, and the documentation describes the current version.

## Development

```shell
git clone https://github.com/ryanpaulanderson/cfb-data.git
cd cfb-data
make install
make hooks
make format
make docs
make check
```

Contributor standards, testing, release details, and architecture expectations
live in [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md). They
are intentionally separate from the steps required to use the library.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

This project is not affiliated with CollegeFootballData.com.
