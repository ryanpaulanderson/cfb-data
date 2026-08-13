# cfb-data

`cfb-data` is an asynchronous, validated Python client for the public
[CollegeFootballData API](https://collegefootballdata.com/). It presents
analytical endpoint results as eager pandas DataFrames by default, with Polars
available as an optional backend, while preserving nested operational results
as Pydantic models.

The request path is intentionally strict:

```text
HTTP → Pydantic models → logical schema → canonical Arrow table → DataFrame
```

See the [request lifecycle architecture](architecture/request-lifecycle.md)
for a diagram of how a call moves through validation, transport, response
models, and result presentation.

Start with the [installation and first-request guide](getting-started.md). Use
the [namespace contracts](cfbd_api/README.md) to choose an endpoint, the
[request guide](guides/requests.md) to understand filters and allowed values,
and the generated [namespace API](reference/namespaces.rst) for exact method
signatures.

```{toctree}
:maxdepth: 2
:caption: Use cfb-data

getting-started
guides/requests
guides/results
guides/errors-and-retries
cfbd_api/README
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
:caption: Project

project-status
architecture/request-lifecycle
architecture/0001-validated-models-before-dataframes
architecture/0002-heterogeneous-stat-scalars
architecture/0003-canonical-arrow-parquet
notices-of-decision/README
notices-of-decision/0001-canonical-nested-tabular-representation
```

## What the client guarantees

- Every request and response is validated before DataFrame conversion.
- Unknown filters and invalid selector combinations fail before network I/O.
- pandas and Polars results materialize from one canonical Arrow table and have
  the same columns, row order, nulls, and logical values.
- Each client owns one connection-pooled session and closes it deterministically.
- Requests have finite timeouts, bounded retries, TLS verification, and safe
  exception messages that do not expose credentials or response payloads.

The project is not affiliated with CollegeFootballData.com.
