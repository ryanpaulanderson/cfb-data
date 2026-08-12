# Project documentation

## Current documentation

- [`../README.md`](../README.md) — installation, client usage, DataFrame
  contract, retries, errors, and 0.1.x migration.
- [`project-status.md`](project-status.md) — implemented release scope and
  deliberately deferred work.
- [`architecture/0001-validated-models-before-dataframes.md`](architecture/0001-validated-models-before-dataframes.md)
  — accepted validation, DataFrame, dataset, and workflow layering decision.
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
