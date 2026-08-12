# Implemented CFBD endpoint contracts

These notes describe only the REST endpoints implemented in this repository.
They were reconciled on August 12, 2026 with the current
[CFBD API reference](https://api.collegefootballdata.com/api) and the official
[`CFBD/cfb-api-v2` v5.24.0 source](https://github.com/CFBD/cfb-api-v2/tree/v5.24.0).
The new API reference and the versioned official source are authoritative.
Generated or downloaded API snapshots are intentionally not checked in because
they become stale and create a competing source of truth.

| Family | Routes implemented | Contract notes |
| --- | ---: | --- |
| [Games](games_api.md) | 8 | Games, team/player stats, media, weather, records, calendar, and advanced box score |
| [Drives](drives_api.md) | 1 | Historical drives and results |

The client sends requests to `https://api.collegefootballdata.com` with bearer
authentication. Python request fields use snake case and are serialized to the
API's camel-case names, such as `season_type` to `seasonType` and `game_id` to
`gameId`. Unknown request fields are rejected so a misspelling cannot silently
broaden a query.

The response models deliberately follow the current nested API structures.
In particular, `/games/teams` and `/games/players` return one object per game
with nested `teams` collections, while `/game/box/advanced` returns nested
`gameInfo`, `teams`, and `players` sections.
