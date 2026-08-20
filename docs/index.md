# cfb-data

`cfb-data` is a beta Python toolkit for enthusiasts exploring the public
[CollegeFootballData API](https://collegefootballdata.com/). Most calls return
eager pandas DataFrames that are ready for analysis; Polars is available as an
optional backend, and a few naturally nested results return Pydantic models.

Two paths stay deliberately short:

```text
pick a football question → call an endpoint → get a DataFrame → analyze it
                                  │
                                  └── optionally reuse data from SQLite or Redis

pick a reusable product → call a dataset/workflow recipe → validated outputs
                                                       └── durable artifacts
```

Start with the [installation and first-request guide](getting-started.md). Use
the [endpoint reference](cfbd_api/README.md) to choose an endpoint, the
[request guide](guides/requests.md) to understand filters and allowed values,
and the generated [namespace API](reference/namespaces.rst) for exact method
signatures.

## Choose a path

| I want to... | Start here |
| --- | --- |
| Fetch games, plays, ratings, or another dataset | [Getting started](getting-started.md) |
| Run, compose, or author a durable analytics recipe | [Modular analytics recipes](guides/modular-analytics.md) |
| Copy a notebook recipe for a common question | [Common notebook recipes](guides/common-recipes.md) |
| Understand a method's filters | [Requests and allowed values](guides/requests.md) |
| Work with pandas, Polars, or nested results | [Work with results](guides/results.md) |
| Avoid repeated calls or join data by IDs | [Cache responses and look up identities](guides/cache-and-identities.md) |
| Fix an error | [Troubleshooting requests](guides/errors-and-retries.md) |
| Look up every available endpoint | [Endpoint reference](cfbd_api/README.md) |

```{toctree}
:maxdepth: 2
:caption: Use cfb-data

getting-started
guides/modular-analytics
guides/common-recipes
guides/requests
guides/results
guides/errors-and-retries
guides/cache-and-identities
cfbd_api/README
```

```{toctree}
:maxdepth: 1
:caption: Advanced details

advanced/index
advanced/request-details
advanced/result-details
advanced/cache-behavior
advanced/observability
advanced/errors-and-retries
```

```{toctree}
:maxdepth: 2
:caption: API reference

reference/public-api
reference/namespaces
reference/requests
reference/responses
```

```{toctree}
:maxdepth: 1
:caption: Project internals

project-status
product-constitution
architecture/request-lifecycle
architecture/0001-validated-models-before-dataframes
architecture/0002-heterogeneous-stat-scalars
architecture/0003-canonical-arrow-parquet
architecture/0004-api-cache-identity-catalog
architecture/0005-client-retrieval-observability
architecture/0006-modular-analytics-recipes
architecture/analytics-foundation-plan
notices-of-decision/README
notices-of-decision/0001-canonical-nested-tabular-representation
```

## What to expect

- Every request and response is validated before DataFrame conversion. This
  catches misspelled filters and unexpected upstream data before they quietly
  affect an analysis.
- Unknown filters and invalid selector combinations fail before network I/O.
- pandas and Polars results materialize from one canonical Arrow table and have
  the same columns, row order, nulls, and logical values.
- Calls made within one client context share an HTTP session, which is closed
  when the context exits.
- Requests have timeouts and a small retry policy for temporary failures.
- Optional SQLite or Redis caching can reduce repeated API calls and keep a
  locally queryable identity catalog. Both are useful on a single computer;
  Redis can also be shared by several scripts or machines.
- Callable datasets and workflows coordinate validated sources, pure
  transformations, canonical artifacts, recovery, and observation without
  changing the source-shaped endpoint results beneath them.

This is an enthusiast-focused beta project. Its core retrieval, validation,
DataFrame, caching, and identity workflows are usable and carefully tested.
Public APIs and local cache formats may still change before 1.0. The
documentation describes the current version.

Curious about the implementation? The [request lifecycle
diagram](architecture/request-lifecycle.md) shows the validation, HTTP, Arrow,
and DataFrame layers. Those internals are optional reading, not prerequisites
for using the library.

The project is not affiliated with CollegeFootballData.com.
