# Project status

> Status as of August 13, 2026: version 0.4.1 implements the supported public
> CFBD v5.24.0 REST endpoint surface. Dataset and workflow coverage remains
> future work.

## Current product surface

`CFBDClient` is the sole primary client. It owns one context-managed,
connection-pooled `aiohttp.ClientSession` and exposes typed `games`, `drives`,
`plays`, `venues`, `conferences`, `teams`, `stats`, `metrics`, `ratings`,
`players`, `rankings`, `betting`, `recruiting`, `coaches`, `draft`, `playoffs`,
`adjusted_metrics`, and `info` namespaces. Every endpoint follows the same
boundary sequence:

```text
HTTP → Pydantic response validation → logical schema → canonical Arrow table
                                                       ├── pandas DataFrame
                                                       ├── Polars DataFrame
                                                       └── versioned Parquet
```

pandas is the default backend. Polars is available through the `polars` extra.
Both return eager frames with the same endpoint methods, request validation,
column names/order, API row order, nulls, and logical values. Advanced box
score, live plays, and the complete CFP bracket intentionally return validated
models because their nested sections do not form one natural table. Info
account and usage endpoints return validated operational models.

The implemented routes are `/games`, `/records`, `/calendar`, `/scoreboard`,
`/games/media`, `/games/weather`, `/games/players`, `/games/teams`,
`/game/box/advanced`, `/drives`, `/plays`, `/plays/types`, `/plays/stats`,
`/plays/stats/types`, `/live/plays`, `/venues`, `/conferences`,
`/conferences/changes`, `/conferences/affiliations`, `/teams`, `/teams/fbs`,
`/teams/matchup`, `/teams/ats`, `/roster`, and `/talent`.
The Stats routes are `/stats/player/season`, `/stats/player/success`,
`/stats/player/success/game`, `/stats/season`, `/stats/categories`,
`/stats/season/advanced`, `/stats/game/advanced`, and `/stats/game/havoc`.
Metrics implements eight PPA and probability routes, Ratings implements seven
rating-system routes, and Players implements the five documented player
routes. The hidden `/player/ppa/passing` route is not public client surface.
Rankings implements `/rankings`, Betting implements `/lines`, Recruiting
implements `/recruiting/players`, `/recruiting/teams`, and
`/recruiting/groups`, and Coaches implements `/coaches`, `/coaches/profile`,
`/coaches/seasons`, and `/coaches/tenures`. Draft implements `/draft/teams`,
`/draft/positions`, and `/draft/picks`. Playoffs implements `/playoffs/cfp`,
`/playoffs/cfp/participants`, and `/playoffs/cfp/games`. Adjusted Metrics
implements `/wepa/team/season`, `/wepa/players/passing`,
`/wepa/players/rushing`, and `/wepa/players/kicking`; these routes require
Patreon Tier 1. Info implements `/info` and `/info/usage` as operational model
responses.

Apache Arrow is the canonical representation for tabular endpoint results.
Its explicit recursive schema preserves ordered structs, typed lists,
nullability, and UTC timestamps for populated, empty, and all-null responses.
pandas still presents nested values as Python mappings and lists in `object`
columns, while Polars presents native `Struct` and `List` columns.

The library also has a private, versioned local-file Parquet codec for future
library-owned caches. It uses the canonical Arrow schema, atomic replacement,
strict compatibility metadata, and full Pydantic validation by default. This
codec is the persistence compatibility contract; direct pandas and Polars
Parquet methods are not.

## Reliability contract

- Explicit or environment (`CFBD_API_KEY`) bearer authentication.
- Mandatory one-shot async context lifecycle and deterministic session close.
- Finite per-attempt timeouts, normal TLS verification, and disabled redirects.
- Bounded retries for safe GET transport failures and selected transient HTTP
  statuses, including capped `Retry-After` handling.
- Pydantic request and response validation before table conversion.
- Safe public exception metadata without credentials, query strings, or
  response payloads.
- Strict logical schemas and row/column assertions in both adapters.
- One explicit Arrow schema for DataFrame materialization and nested Parquet
  persistence, including empty and all-null tables.
- Atomic internal Parquet writes and strict version, row-model, logical-schema,
  physical-schema, and tagged-scalar validation on reads.
- Black-box tests through the installed client and a local HTTP boundary.
- CI installation checks for base pandas and PyArrow and for the Polars extra
  on Python 3.12 and 3.13.

## Removed 0.1.x surface

The raw/Pydantic/pandas inheritance hierarchy, domain-specific client classes,
generic route decorator, public path router, Pandera schemas, and Pandera
dependency have been removed. Raw JSON and general response-model return modes
are not part of the supported client.

## Deliberately not included in 0.4.1

- Internal authentication routes and the deliberately hidden rolling
  player-passing PPA route.
- Credentialed live-API tests; deterministic tests use a local HTTP server.
- Polars `LazyFrame` results.
- Public save/load methods and cache keys, locations, expiration, eviction,
  request hashing, remote filesystems, and partitioned Parquet datasets.
- Automatic flattening, exploding, or ML feature generation from nested
  endpoint data.
- Public dataset or workflow namespaces.

Future datasets will compose validated endpoint results and validated
subdatasets through joins into an authoritative tabular row model. They, and
future ML feature layers, will perform explicit transformations at a declared
row grain rather than changing source-faithful endpoint results. Future
workflows will orchestrate endpoints and datasets with broader control flow and
may return multiple artifacts. The layering and persistence decisions are
recorded in
[`architecture/0001-validated-models-before-dataframes.md`](architecture/0001-validated-models-before-dataframes.md)
and
[`architecture/0003-canonical-arrow-parquet.md`](architecture/0003-canonical-arrow-parquet.md).

## Development contract

Package metadata and dependency groups live in `pyproject.toml`.

```sh
make install
make format
make docs
make check
```

`make install` installs the complete contributor environment, including
PyArrow and both DataFrame backends. `make docs` performs the same strict
Sphinx HTML build used for publication. GitHub Actions runs the shared quality
contract on Python 3.12 and 3.13, separately smoke-tests base and Polars
installations, and deploys documentation from `main` to GitHub Pages. The
published URL is part of the package's project metadata so PyPI displays it as
the Documentation link.

## Historical material

Earlier analyses and implementation plans remain in the repository's
[`docs/history/`](https://github.com/ryanpaulanderson/cfb-data/tree/main/docs/history)
directory. They explain superseded designs and are not a current roadmap or
API reference.
