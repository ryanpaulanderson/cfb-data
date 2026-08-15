# CFBD API group coverage

> Coverage status as of August 13, 2026. This record is based on the official
> CFBD API v5.24.0 controllers and response types.

## Status

There is no remaining public v5.24.0 REST endpoint group to schedule. Draft,
Playoffs, Adjusted Metrics, and Info complete the controller coverage that was
previously recommended here.

| Completed group | Routes | Result | Why it is shaped this way |
| --- | ---: | --- | --- |
| Draft | 3 | Separate team, position, and pick DataFrames | Preserve each upstream grain instead of joining identities into picks. |
| Playoffs | 3 | Participant and matchup DataFrames; complete bracket model | Keep the nested bracket, rounds, slots, linked games, and advancement graph together. |
| Adjusted Metrics | 4 | Team, passing, rushing, and kicking DataFrames | Keep player WEPA and kicker PAAR as distinct measures; all routes require Patreon Tier 1. |
| Info | 2 | Account and usage models | Account details are not naturally analytical tables. |

The package now covers the public controllers for Games, Drives, Plays, Live,
Teams, Stats, Metrics, Ratings, Players, Rankings, Betting, Recruiting,
Coaches, Draft, Playoffs, Adjusted Metrics, and Info. The source-level
`boxScores` controller is exposed through the Games advanced-box-score route;
the Teams controller also owns Venues and Conferences routes in the public API.

## Routes not included

- `auth` contains server authentication machinery rather than a public data
  endpoint group.
- The controller's hidden rolling player passing-PPA route remains outside the
  supported client surface.
- Raw JSON and a public generic route router remain intentionally unsupported.

With public REST group coverage complete, future roadmap work belongs in
validated datasets, workflows, deeper cross-endpoint identity composition, or
new upstream API versions—not another v5.24.0 endpoint tranche.

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
- [Draft controller and response types](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app/draft)
- [Playoffs controller and response types](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app/playoffs)
- [Adjusted Metrics controller and response types](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app/wepa)
- [Info controller and response types](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0/src/app/info)
