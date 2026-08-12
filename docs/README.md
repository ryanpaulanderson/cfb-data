# Project documentation

The documentation is split by purpose so that current project state is not
confused with earlier design plans.

## Current documentation

- [`project-status.md`](project-status.md) — current vision, implementation
  inventory, known gaps, and tracked next work.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — development setup and quality
  contract.
- [`cfbd_api/`](cfbd_api/) — endpoint research and API reference notes used to
  inform request and response modeling.

## Historical documentation

[`history/`](history/README.md) contains the original validation analyses,
implementation plans, and completion summaries. These files explain earlier
thinking and architectural intent, but they are not a current roadmap or a
reliable statement of package usability.

## Authoritative sources

Before implementing or changing API behavior, use the current
[CollegeFootballData API documentation](https://api.collegefootballdata.com/api)
and the versioned
[official API source](https://github.com/CFBD/cfb-api-v2). Do not check in a
generated or downloaded OpenAPI snapshot as a competing source of truth.
