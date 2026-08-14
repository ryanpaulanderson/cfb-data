# Project documentation

The published Sphinx site is available at
[ryanpaulanderson.github.io/cfb-data](https://ryanpaulanderson.github.io/cfb-data/).
Build the same strict HTML output locally with:

```sh
make install
make docs
```

Open `docs/_build/html/index.html` after the build. `make check` also builds the
site with warnings treated as errors, and GitHub Actions deploys that output
from `main` through GitHub Pages.

The repository's Pages source is configured as **GitHub Actions**. Every push
to `main` rebuilds and deploys the site; the workflow can also be started
manually. Fork maintainers must make the same one-time selection under
**Settings → Pages → Build and deployment → Source** before their first
deployment.

## Current documentation

- [`index.md`](index.md) — Sphinx site entry point and navigation.
- [`getting-started.md`](getting-started.md) — installation, authentication,
  first request, backend selection, and basic error handling.
- [`guides/`](guides/) — request rules and allowed values, result contracts,
  errors, and retries.
- [`reference/`](reference/) — generated client, namespace, request, response,
  enum, and exception API reference.
- [`../README.md`](../README.md) — installation, client usage, DataFrame
  contract, retries, errors, and 0.1.x migration.
- [`project-status.md`](project-status.md) — implemented release scope and
  deliberately deferred work.
- [`architecture/0001-validated-models-before-dataframes.md`](architecture/0001-validated-models-before-dataframes.md)
  — accepted validation, DataFrame, dataset, and workflow layering decision.
- [`architecture/0002-heterogeneous-stat-scalars.md`](architecture/0002-heterogeneous-stat-scalars.md)
  — accepted representation for the Stats string-or-number value contract.
- [`architecture/0003-canonical-arrow-parquet.md`](architecture/0003-canonical-arrow-parquet.md)
  — accepted canonical Arrow table and versioned Parquet persistence contract.
- [`architecture/0004-api-cache-identity-catalog.md`](architecture/0004-api-cache-identity-catalog.md)
  — accepted API response-cache, identity-catalog, coverage, hydration, and
  identity-routing architecture.
- [`notices-of-decision/`](notices-of-decision/README.md) — decision notices
  explaining the evidence, alternatives, and reasoning behind consequential
  project choices.
- [`cfbd_api/`](cfbd_api/) — implemented endpoint contracts by public namespace.
- [`next-api-groups.md`](next-api-groups.md) — source-backed prioritization of
  the remaining official API groups.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contributor setup and quality
  contract.

## Historical documentation

[`history/`](history/README.md) retains superseded analyses, plans, and
completion summaries as context. It is not a current roadmap or statement of
package behavior.

## Authoritative upstream sources

Before changing endpoint behavior, reconcile it with the current
[CollegeFootballData API documentation](https://api.collegefootballdata.com/api)
and versioned [official API source](https://github.com/CFBD/cfb-api-v2). Do not
check in a downloaded OpenAPI snapshot as a competing source of truth.
