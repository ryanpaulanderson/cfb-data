# Project status

`cfb-data` is a beta project for people who want to explore college
football data in Python. That includes data engineers and statisticians, but
also fans learning pandas, Polars, or sports analytics. The library is built
carefully, and its core retrieval, validation, DataFrame, caching, identity,
dataset, and local workflow paths are usable and carefully tested. The user-facing API and
documentation continue to be shaped around what is most useful in real
analyses.

The current package version is 0.8.0 and the endpoint reference was checked
against CFBD API v5.24.0 on August 13, 2026. The Python API and local cache
format may still change before 1.0.

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

## Durable datasets and local workflows

`client.datasets` provides twelve curated analytical tables above the
source-shaped endpoint resources. Each declares an authoritative Pydantic row
model and table contract, grain, candidate key, ordering, source lineage,
coverage, and quality evidence before pandas or Polars presentation.

`client.workflows` composes those tables into three named-output analyses for a
team season, one game, or a program history. The embedded local runner plans
before I/O, accounts for actual transport attempts, deduplicates exact source
requests, checkpoints validated nodes, and recovers a failed analysis as an
immutable child run. One run-wide scheduler bounds retrieval and compute even
when several child datasets are ready at once. SQLite owns run state and the
filesystem owns content-addressed Parquet or bounded modeled-JSON artifacts;
neither is part of the response cache.

Python definitions are the trusted extension surface. The optional `yaml`
extra loads a finite, allowlisted graph into the same immutable contracts while
rejecting executable or ambiguous YAML features. See [Build durable datasets
and workflows](guides/datasets-and-workflows.md).

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
- Remote artifact stores, multi-host workers, queues, cron, or side-effecting
  workflow steps.
- PyTorch training/inference, plotting, chart specifications, or generic model
  and figure codecs.
- Automatic broad per-player, per-coach, per-game win-probability, or
  `/plays/stats` fan-out.
- Raw JSON and a generic path-based request method.

Users can add explicit portable transforms or backend-specific trusted Python
transforms. The runner remains local and artifact-oriented; future modeling and
visualization layers plug into the validated artifact/table-contract boundary
without changing the source-shaped endpoint results underneath them.

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
