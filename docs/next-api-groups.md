# Next CFBD API groups

> Discovery status as of August 12, 2026. This recommendation is based on the
> official CFBD API v5.24.0 controllers and response types. It is a planning
> document, not a supported endpoint contract.

## Recommendation

Plays is now implemented. The next deliverable should be a dependency-ordered
**Venues, Conferences, and Teams** tranche, followed by **Stats** and
**Metrics** after those reference-data foundations are in place.

## Recommended sequence

| Priority | Group or tranche | Routes | Rationale | Main complication |
| ---: | --- | ---: | --- | --- |
| 1 | Venues, Conferences, Teams | 10 | Supplies stable reference data, roster identities, affiliations, and join dimensions used across the API. | Shared `Venue` and conference-classification types need one authoritative owner. |
| 2 | Stats | 8 | Adds the most familiar team and player analysis surface after play data exists. | `TeamStat.statValue` is `string | number`, which the current logical schema cannot represent without an explicit policy. |
| 3 | Metrics | 8 | Adds PPA, win probability, and expected-points products that compose naturally with Plays. | Several nested schemas and mixed game/player identifiers increase validation scope. |
| 4 | Ratings | 7 | High-value comparative team data with mostly season/team filters. | Multiple rating systems have distinct nested response contracts. |
| 5 | Players | 6 | Adds discovery, usage, returning production, and transfer data. | Season overview is a single nested object; transfer and search identity semantics differ. |
| 6 | Rankings | 1 | Small, recognizable feature and useful historical context. | A poll week contains nested polls and ranks rather than one obvious table. |
| 7 | Betting | 1 | Directly complements Games and the existing scoreboard betting summary. | A game contains a provider list; the public table shape needs an explicit decision. |
| 8 | Recruiting | 3 | Enables roster-building and talent-pipeline analysis. | Recruit identity, commitments, and aggregated position groups form separate grains. |
| 9 | Coaches | 4 | Useful historical team context. | Profiles, seasons, and tenures were recently split into separate routes. |
| 10 | Draft | 3 | Useful outcome data for player and program analysis. | Lower compositional value until player identity coverage exists. |
| 11 | Playoffs | 3 | Supports the new CFP-specific competition model. | New nested bracket and advancement models are specialized and still evolving. |
| 12 | Adjusted Metrics | 4 | Adds opponent-adjusted WEPA and player value measures. | All routes require Patreon Tier 1 and depend conceptually on Plays/Metrics. |
| 13 | Info | 2 | Exposes account and usage metadata. | Operational metadata is separate from the analytical DataFrame product. |

The route count reflects the current v5.24.0 source, not the legacy Swagger
grouping. In particular, Conferences now has three routes, Teams includes ATS,
and Ratings includes Core and Expanded SRS endpoints.

## Next tranche: reference data

Implement three public namespaces in this order:

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

## Primary sources

- [Current CFBD API reference](https://api.collegefootballdata.com/api)
- [CFBD API v5.24.0 source](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app)
- [Endpoint access rules](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/config/auth.ts)
- [Teams, Conferences, and Venues controller](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/teams/controller.ts)
- [Stats response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/stats/types.ts)
