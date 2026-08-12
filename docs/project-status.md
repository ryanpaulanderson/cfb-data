# Project status

> Status as of August 12, 2026: foundation rebuild; not ready for general use.

## Intended direction

The repository began as a hand-written Python toolkit for the
CollegeFootballData REST API. Its distinguishing ideas were asynchronous HTTP
access, Pydantic request and response validation, and Pandera-validated pandas
DataFrames.

Those ideas are still present in the codebase, but they do not yet form a
stable product interface. The current work is rebuilding packaging,
dependencies, documentation, and automation before making further API-design
decisions.

## What exists

- A shared asynchronous HTTP and route-discovery layer.
- Raw, Pydantic-validated, and pandas-oriented internal client layers.
- Request and response models for several games endpoints and the drives
  endpoint.
- Route handlers for `/games`, `/records`, `/calendar`, `/games/media`,
  `/games/weather`, `/games/players`, `/games/teams`,
  `/game/box/advanced`, and `/drives`.
- A substantial mocked test suite covering validation and internal request
  behavior.

At the beginning of the foundation rebuild, the existing suite contained 200
passing tests. That is useful evidence for internal behavior, but not evidence
of a complete installed-user workflow.

## What does not exist yet

- A cohesive, supported top-level client API.
- A documented end-user workflow.
- Broad CollegeFootballData endpoint coverage.
- Production-ready HTTP session, timeout, TLS, and error-handling behavior.
- Confidence that all response schemas match the latest live API responses.

The public client design is tracked in
[GitHub issue #53](https://github.com/ryanpaulanderson/cfb-data/issues/53).
HTTP transport and error hardening are tracked in
[GitHub issue #54](https://github.com/ryanpaulanderson/cfb-data/issues/54).

## Development contract

The package metadata and dependency groups live in `pyproject.toml`.

```sh
make install
make check
```

These are the same installation and verification commands used by GitHub
Actions. See `CONTRIBUTING.md` for the complete contributor workflow.

## Historical design material

Earlier analysis, implementation plans, and completion summaries have been
retained under [`docs/history/`](history/README.md). They are useful for
understanding why parts of the current architecture exist, but they are not a
current roadmap or an authoritative statement of implementation status.
