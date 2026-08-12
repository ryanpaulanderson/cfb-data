# Next CFBD API groups

> Discovery status as of August 12, 2026. This recommendation is based on the
> official CFBD API v5.24.0 controllers and response types. It is a planning
> document, not a supported endpoint contract.

## Recommendation

Venues, Conferences, Teams, and Stats are now implemented. The next deliverable
should be **Metrics**.

## Recommended sequence

| Priority | Group or tranche | Routes | Rationale | Main complication |
| ---: | --- | ---: | --- | --- |
| 1 | Metrics | 8 | Adds PPA, win probability, and expected-points products that compose naturally with Plays. | Several nested schemas and mixed game/player identifiers increase validation scope. |
| 2 | Ratings | 7 | High-value comparative team data with mostly season/team filters. | Multiple rating systems have distinct nested response contracts. |
| 3 | Players | 6 | Adds discovery, usage, returning production, and transfer data. | Season overview is a single nested object; transfer and search identity semantics differ. |
| 4 | Rankings | 1 | Small, recognizable feature and useful historical context. | A poll week contains nested polls and ranks rather than one obvious table. |
| 5 | Betting | 1 | Directly complements Games and the existing scoreboard betting summary. | A game contains a provider list; the public table shape needs an explicit decision. |
| 6 | Recruiting | 3 | Enables roster-building and talent-pipeline analysis. | Recruit identity, commitments, and aggregated position groups form separate grains. |
| 7 | Coaches | 4 | Useful historical team context. | Profiles, seasons, and tenures were recently split into separate routes. |
| 8 | Draft | 3 | Useful outcome data for player and program analysis. | Lower compositional value until player identity coverage exists. |
| 9 | Playoffs | 3 | Supports the new CFP-specific competition model. | New nested bracket and advancement models are specialized and still evolving. |
| 10 | Adjusted Metrics | 4 | Adds opponent-adjusted WEPA and player value measures. | All routes require Patreon Tier 1 and depend conceptually on Plays/Metrics. |
| 11 | Info | 2 | Exposes account and usage metadata. | Operational metadata is separate from the analytical DataFrame product. |

The route count reflects the current v5.24.0 source, not the legacy Swagger
grouping. In particular, Conferences now has three routes, Teams includes ATS,
and Ratings includes Core and Expanded SRS endpoints.

## Resolved Stats scalar decision

Stats preserves `TeamStat.statValue` strings and numbers without coercion using
one narrowly defined heterogeneous scalar. It maps to pandas `object` and
Polars `Object`; unrelated general unions remain unsupported. The decision is
recorded in
[`architecture/0002-heterogeneous-stat-scalars.md`](architecture/0002-heterogeneous-stat-scalars.md).

## Primary sources

- [Current CFBD API reference](https://api.collegefootballdata.com/api)
- [CFBD API v5.24.0 source](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app)
- [Endpoint access rules](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/config/auth.ts)
- [Teams, Conferences, and Venues controller](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/teams/controller.ts)
- [Stats response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/stats/types.ts)
