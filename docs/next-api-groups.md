# Next CFBD API groups

> Discovery status as of August 13, 2026. This recommendation is based on the
> official CFBD API v5.24.0 controllers and response types. It is a planning
> document, not a supported endpoint contract.

## Recommendation

Venues, Conferences, Teams, Stats, Metrics, Ratings, Players, Rankings,
Betting, Recruiting, and Coaches are now implemented. The next deliverable
should be **Draft**.

The completed Rankings and Betting tables preserve their upstream nested poll
and provider collections. Recruiting exposes its three distinct grains, and
Coaches exposes the historical summary, profile, season, and tenure routes.

## Recommended sequence

| Priority | Group or tranche | Routes | Rationale | Main complication |
| ---: | --- | ---: | --- | --- |
| 1 | Draft | 3 | Adds player outcome data that now composes naturally with the implemented player and recruiting identities. | Picks, team aggregates, and position aggregates form separate grains. |
| 2 | Playoffs | 3 | Supports the new CFP-specific competition model. | New nested bracket and advancement models are specialized and still evolving. |
| 3 | Adjusted Metrics | 4 | Adds opponent-adjusted WEPA and player value measures. | All routes require Patreon Tier 1 and depend conceptually on Plays/Metrics. |
| 4 | Info | 2 | Exposes account and usage metadata. | Operational metadata is separate from the analytical DataFrame product. |

The route count reflects the current v5.24.0 source, not the legacy Swagger
grouping. Implemented Players coverage excludes the controller's deliberately
hidden rolling passing-PPA route.

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
- [Rankings response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/rankings/types.ts)
- [Betting response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/lines/types.ts)
- [Recruiting response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/recruiting/types.ts)
- [Coaches response types](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/coaches/types.ts)
