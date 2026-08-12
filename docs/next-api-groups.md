# Next CFBD API groups

> Discovery status as of August 12, 2026. This recommendation is based on the
> official CFBD API v5.24.0 controllers and response types. It is a planning
> document, not a supported endpoint contract.

## Recommendation

Implement **Plays next**, followed by a dependency-ordered **Venues,
Conferences, and Teams** tranche. Implement **Stats** and **Metrics** after
those foundations are in place.

The next deliverable should cover the complete official `plays` group:

| Route | Proposed method | Proposed return |
| --- | --- | --- |
| `GET /plays` | `client.plays.list` | selected DataFrame |
| `GET /plays/types` | `client.plays.types` | selected DataFrame |
| `GET /plays/stats` | `client.plays.stats` | selected DataFrame |
| `GET /plays/stats/types` | `client.plays.stat_types` | selected DataFrame |
| `GET /live/plays` | `client.plays.live` | validated `LiveGame` model |

The four historical responses are naturally tabular. The live response is one
game with nested teams, drives, and plays, so it should follow the advanced box
score precedent and return one validated model. It also requires Patreon Tier
2 access; deterministic tests should continue to use a local HTTP server.

## Why Plays is next

Plays completes the core game hierarchy already started by Games and Drives:

```text
game → drive → play → athlete play stat
```

It has the highest immediate compositional value. Existing game IDs and drive
IDs become useful join keys, while play rows unlock success rate, expected
points, win probability, and player attribution workflows. The four historical
models are also a good fit for the current schema system: their fields are
scalars plus the already-supported nested clock shape.

This is a bounded extension of the current architecture rather than a new
abstraction. It exercises request aliases, typed empty frames, nested clock
conversion, and a justified model-returning endpoint without requiring dataset
or workflow APIs.

## Recommended sequence

| Priority | Group or tranche | Routes | Rationale | Main complication |
| ---: | --- | ---: | --- | --- |
| 1 | Plays | 5 | Completes game/drive/play flow and enables most downstream analytics. | Live response is nested and Tier 2; play stats are capped at 2,000 rows. |
| 2 | Venues, Conferences, Teams | 10 | Supplies stable reference data, roster identities, affiliations, and join dimensions used across the API. | Shared `Venue` and conference-classification types need one authoritative owner. |
| 3 | Stats | 8 | Adds the most familiar team and player analysis surface after play data exists. | `TeamStat.statValue` is `string | number`, which the current logical schema cannot represent without an explicit policy. |
| 4 | Metrics | 8 | Adds PPA, win probability, and expected-points products that compose naturally with Plays. | Several nested schemas and mixed game/player identifiers increase validation scope. |
| 5 | Ratings | 7 | High-value comparative team data with mostly season/team filters. | Multiple rating systems have distinct nested response contracts. |
| 6 | Players | 6 | Adds discovery, usage, returning production, and transfer data. | Season overview is a single nested object; transfer and search identity semantics differ. |
| 7 | Rankings | 1 | Small, recognizable feature and useful historical context. | A poll week contains nested polls and ranks rather than one obvious table. |
| 8 | Betting | 1 | Directly complements Games and the existing scoreboard betting summary. | A game contains a provider list; the public table shape needs an explicit decision. |
| 9 | Recruiting | 3 | Enables roster-building and talent-pipeline analysis. | Recruit identity, commitments, and aggregated position groups form separate grains. |
| 10 | Coaches | 4 | Useful historical team context. | Profiles, seasons, and tenures were recently split into separate routes. |
| 11 | Draft | 3 | Useful outcome data for player and program analysis. | Lower compositional value until player identity coverage exists. |
| 12 | Playoffs | 3 | Supports the new CFP-specific competition model. | New nested bracket and advancement models are specialized and still evolving. |
| 13 | Adjusted Metrics | 4 | Adds opponent-adjusted WEPA and player value measures. | All routes require Patreon Tier 1 and depend conceptually on Plays/Metrics. |
| 14 | Info | 2 | Exposes account and usage metadata. | Operational metadata is separate from the analytical DataFrame product. |

The route count reflects the current v5.24.0 source, not the legacy Swagger
grouping. In particular, Conferences now has three routes, Teams includes ATS,
and Ratings includes Core and Expanded SRS endpoints.

## Second tranche: reference data

After Plays, implement three public namespaces in this order:

1. `client.venues` for `GET /venues`;
2. `client.conferences` for `GET /conferences`, `/conferences/changes`, and
   `/conferences/affiliations`;
3. `client.teams` for `GET /teams`, `/teams/fbs`, `/teams/matchup`,
   `/teams/ats`, `/roster`, and `/talent`.

Although the upstream implementation keeps these routes in one controller,
the official tags represent three user-facing groups. They should remain
separate public namespaces. Implementing them as one tranche allows shared
response concepts to be designed once: a Team embeds a Venue-shaped location,
and conference classification is used by both Teams and Conferences.

Before coding this tranche, decide and document which domain owns the shared
`Venue` response model. Do not create structurally duplicate Team-location and
Venue models merely to avoid a domain import.

## Decisions required before Stats

The Stats group exposes `TeamStat.statValue` as either a string or a number.
The current logical DataFrame schema supports nullable unions but deliberately
rejects general unions. Stats must not silently coerce this field or degrade it
to an unspecified pandas object column.

Choose one cross-backend contract before implementing Stats:

- normalize all stat values to strings in the validated external model only if
  the upstream semantic contract treats them as display values; or
- add a deliberate heterogeneous scalar representation supported and tested
  in both pandas and Polars; or
- return a non-tabular validated model for that endpoint if no honest common
  table type exists.

This decision should be made from representative official responses and
documented in an ADR if it changes the global logical schema.

## Acceptance criteria for Plays

- Add a typed `client.plays` namespace without a generic public path router.
- Model and export every request, response, and relevant enum from one
  authoritative owner.
- Validate required `year` and `week` for historical plays and positive IDs
  for live/stat filters before HTTP.
- Preserve row order, exact column order, UTC timestamps, typed empty frames,
  and nested clock values in pandas and Polars.
- Return `LiveGame` as a validated nested model and document its Tier 2 access.
- Cover all five routes through the installed client and local HTTP boundary,
  including malformed responses, invalid requests, aliases, and cleanup.
- Update the README, project status, implemented-contract index, and package
  exports in the same change.
- Run `make format` followed by `make check`.

## Primary sources

- [Current CFBD API reference](https://api.collegefootballdata.com/api)
- [CFBD API v5.24.0 source](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app)
- [Plays controller](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/plays/controller.ts)
- [Plays response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/plays/types.ts)
- [Live plays controller](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/live/controller.ts)
- [Endpoint access rules](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/config/auth.ts)
- [Teams, Conferences, and Venues controller](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/teams/controller.ts)
- [Stats response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/stats/types.ts)
