# Project status

> Status as of August 12, 2026: version 0.2.0 implements the supported Games,
> Drives, and Plays client surface. Broader endpoint, dataset, and workflow
> coverage remains future work.

## Current product surface

`CFBDClient` is the sole primary client. It owns one context-managed,
connection-pooled `aiohttp.ClientSession` and exposes typed `games`, `drives`,
and `plays` namespaces. Every endpoint follows the same boundary sequence:

```text
HTTP → decoded JSON → Pydantic response validation → logical schema → DataFrame
```

pandas is the default backend. Polars is available through the `polars` extra.
Both return eager frames with the same endpoint methods, request validation,
column names/order, API row order, nulls, and logical values. Advanced box
score and live plays intentionally return validated models because their
nested sections do not form one natural table.

The implemented routes are `/games`, `/records`, `/calendar`, `/scoreboard`,
`/games/media`, `/games/weather`, `/games/players`, `/games/teams`,
`/game/box/advanced`, `/drives`, `/plays`, `/plays/types`, `/plays/stats`,
`/plays/stats/types`, and `/live/plays`.

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
- Black-box tests through the installed client and a local HTTP boundary.
- CI installation checks for base pandas and the Polars extra on Python 3.11
  and 3.13.

## Removed 0.1.x surface

The raw/Pydantic/pandas inheritance hierarchy, domain-specific client classes,
generic route decorator, public path router, Pandera schemas, and Pandera
dependency have been removed. Raw JSON and general response-model return modes
are not part of the supported client.

## Deliberately not included in 0.2.0

- Endpoint families beyond Games, Drives, and Plays.
- Credentialed live-API tests; deterministic tests use a local HTTP server.
- Polars `LazyFrame` results.
- Public dataset or workflow namespaces.

Future datasets will compose validated endpoint results and validated
subdatasets through joins into an authoritative tabular row model. Future
workflows will orchestrate endpoints and datasets with broader control flow and
may return multiple artifacts. The accepted decision is recorded in
[`architecture/0001-validated-models-before-dataframes.md`](architecture/0001-validated-models-before-dataframes.md).

## Development contract

Package metadata and dependency groups live in `pyproject.toml`.

```sh
make install
make format
make check
```

`make install` installs the complete contributor environment, including both
DataFrame backends. GitHub Actions runs the shared quality contract on Python
3.11 and 3.13 and separately smoke-tests base and Polars installations.

## Historical material

Earlier analyses and implementation plans remain under
[`history/`](history/README.md). They explain superseded designs and are not a
current roadmap or API reference.
