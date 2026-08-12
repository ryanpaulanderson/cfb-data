# Next CFBD API groups

> Discovery status as of August 12, 2026. This recommendation is based on the
> official CFBD API v5.24.0 controllers and response types. It is a planning
> document, not a supported endpoint contract.

## Recommendation

Venues, Conferences, and Teams are now implemented. The next deliverable
should be **Stats**, followed by **Metrics**.

## Recommended sequence

| Priority | Group or tranche | Routes | Rationale | Main complication |
| ---: | --- | ---: | --- | --- |
| 1 | Stats | 8 | Adds the most familiar team and player analysis surface after play data exists. | `TeamStat.statValue` is `string | number`, which the current logical schema cannot represent without an explicit policy. |
| 2 | Metrics | 8 | Adds PPA, win probability, and expected-points products that compose naturally with Plays. | Several nested schemas and mixed game/player identifiers increase validation scope. |
| 3 | Ratings | 7 | High-value comparative team data with mostly season/team filters. | Multiple rating systems have distinct nested response contracts. |
| 4 | Players | 6 | Adds discovery, usage, returning production, and transfer data. | Season overview is a single nested object; transfer and search identity semantics differ. |
| 5 | Rankings | 1 | Small, recognizable feature and useful historical context. | A poll week contains nested polls and ranks rather than one obvious table. |
| 6 | Betting | 1 | Directly complements Games and the existing scoreboard betting summary. | A game contains a provider list; the public table shape needs an explicit decision. |
| 7 | Recruiting | 3 | Enables roster-building and talent-pipeline analysis. | Recruit identity, commitments, and aggregated position groups form separate grains. |
| 8 | Coaches | 4 | Useful historical team context. | Profiles, seasons, and tenures were recently split into separate routes. |
| 9 | Draft | 3 | Useful outcome data for player and program analysis. | Lower compositional value until player identity coverage exists. |
| 10 | Playoffs | 3 | Supports the new CFP-specific competition model. | New nested bracket and advancement models are specialized and still evolving. |
| 11 | Adjusted Metrics | 4 | Adds opponent-adjusted WEPA and player value measures. | All routes require Patreon Tier 1 and depend conceptually on Plays/Metrics. |
| 12 | Info | 2 | Exposes account and usage metadata. | Operational metadata is separate from the analytical DataFrame product. |

The route count reflects the current v5.24.0 source, not the legacy Swagger
grouping. In particular, Conferences now has three routes, Teams includes ATS,
and Ratings includes Core and Expanded SRS endpoints.

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
