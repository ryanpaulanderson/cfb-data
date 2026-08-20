# Project status

`cfb-data` is a beta project for people who want to explore college
football data in Python. That includes data engineers and statisticians, but
also fans learning pandas, Polars, or sports analytics. The library is built
carefully, and its core retrieval, validation, DataFrame, caching, and identity
workflows are usable and carefully tested. The user-facing API and
documentation continue to be shaped around what is most useful in real
analyses.

The current package version is 0.8.0 and the endpoint reference was checked
against CFBD API v5.24.0 on August 13, 2026. The Python API, cache formats, and
analytics artifact formats may still change before 1.0.

## What works today

`CFBDClient` covers the public Games, Drives, Plays, Venues, Conferences,
Teams, Stats, Metrics, Ratings, Players, Rankings, Betting, Recruiting,
Coaches, Draft, Playoffs, Adjusted Metrics, and Info endpoint groups.

Most calls return eager pandas DataFrames by default. Install the `polars`
extra to receive Polars DataFrames from the same methods. A few results, such
as a live game or complete playoff bracket, stay as nested Pydantic models
because forcing them into one table would make them harder to use.

Requests and responses are validated, so mistakes such as an unknown filter or
an unexpected upstream value fail with a useful exception instead of quietly
changing an analysis. Column order, row order, nulls, nested values, and empty
result schemas are preserved across the pandas and Polars backends.

The [endpoint reference](cfbd_api/README.md) lists every available method and
its filters. [Getting started](getting-started.md) shows the shortest path from
installation to a DataFrame.

## Modular analytics is available

The separate ``cfb_data_recipes`` package ships twelve independently authored
dataset modules and three workflow modules. They are callable directly,
compose through ordinary function calls, and use the same public decorators,
discovery, compiler, scheduler, persistence, and events as user recipes. There
is no client dataset/workflow manager or central recipe index.

Recipes provide pure no-I/O planning, read-only cache/checkpoint inspection,
bounded asynchronous source overlap, local or Dask transform execution,
canonical pandas/Polars parity, immutable Parquet artifacts, SQLite run
lineage, checkpoint recovery, maintenance operations, and a hardened optional
YAML composition boundary. Redis remains only the API response cache.

The included datasets cover game summaries, team games, player-game stats,
drives, plays, rosters, team seasons, player seasons, rankings, betting lines,
recruiting classes, and coach seasons. The workflows cover a team season, one
game, and bounded program history. See [Build durable analyses with modular
recipes](guides/modular-analytics.md) for usage and authoring.

Retrieval remains source-faithful. Filtering, joining, flattening, missing-data
policy, and derived metrics live in each visible versioned recipe or in user
code. Optional enrichments never change a base dataset's declared row universe.

The foundation's release evidence includes 651 default-suite tests, 20
separately enabled Redis tests, a 12-combination clean-wheel matrix across
Python 3.12 and 3.13, all four pandas/Polars by local/Dask execution paths, and
a bounded live run that consumed four attempts from the cumulative ledger.
The complete evidence and disclosed environment limitations are recorded in
the [foundation implementation
plan](architecture/analytics-foundation-plan.md).

## Caching is optional

No cache is required. This is often enough for a quick script or a small number
of calls.

SQLite is included for people who want notebook reruns and repeated scripts to
reuse responses without setting up another service. Redis is available through
the `redis` extra and is equally valid on a laptop or workstation. It is handy
when several notebooks, scripts, or local processes should share the same
cache, and it can also be shared across machines.

Both backends also keep a small identity catalog. This helps resolve names,
abbreviations, and provider IDs when an analysis joins games, teams, venues,
and athletes from different endpoints. See [Cache responses and look up
identities](guides/cache-and-identities.md) for examples.

An optional retrieval observer and included in-memory statistics collector
report actual HTTP attempts, retries, cache outcomes, stale fallback, and
backend failures without retaining requests or response bodies. See
[Retrieval observability](advanced/observability.md) for counter definitions.

## What the library handles for you

Calls made in one client context share an HTTP session. The client closes that
session when the context exits, retries a small set of temporary failures, and
uses finite timeouts. API responses are validated before they become
DataFrames. Validation and conversion errors retain their original diagnostic
causes, while authenticated transport failures omit API keys and authorization
headers.

Tabular results use a common Arrow representation before pandas or Polars
materialization:

```text
HTTP → Pydantic response validation → logical schema → Arrow table
                                                       ├── pandas DataFrame
                                                       └── Polars DataFrame
```

These details are there to make results predictable; using the client does not
require understanding the transport, Arrow conversion, cache leases, or
storage implementation.

## Not included yet

- Polars `LazyFrame` results.
- Remote or adopted multi-host Dask clusters and remote artifact stores.
- Cron, deployments, daemon workers, queues, or side-effecting recipe nodes.
- PyTorch training/inference and visualization rendering layers.
- Raw JSON and a generic path-based request method.

Users can perform additional transformations with ordinary pandas or Polars,
compose the reusable operations, or author another module through the public
recipe decorators. [ADR 0006](architecture/0006-modular-analytics-recipes.md)
records the accepted boundary and the [foundation implementation
plan](architecture/analytics-foundation-plan.md) records its release evidence.

## Architecture and contributor details

The deeper validation, DataFrame, dataset, persistence, caching, and identity
decisions are recorded in the [request lifecycle
architecture](architecture/request-lifecycle.md) and linked decision records.
They are useful for contributors and anyone curious about the internals, but
are not required reading for using the library.

Contributor setup and quality checks live in the repository's
[`CONTRIBUTING.md`](https://github.com/ryanpaulanderson/cfb-data/blob/main/CONTRIBUTING.md).
The project intentionally keeps its engineering standards there rather than
asking users to think like library maintainers.

Earlier analyses and implementation plans remain in
[`docs/history/`](https://github.com/ryanpaulanderson/cfb-data/tree/main/docs/history)
as historical context, not current usage guidance.
