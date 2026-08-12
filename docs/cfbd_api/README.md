# Implemented CFBD endpoint contracts

These notes cover only endpoint contracts implemented by `CFBDClient`. They
were reconciled on August 12, 2026 with the current
[CFBD API reference](https://api.collegefootballdata.com/api) and versioned
official [`CFBD/cfb-api-v2`](https://github.com/CFBD/cfb-api-v2) source.

| Family | Routes | Public namespace |
| --- | ---: | --- |
| [Games](games_api.md) | 9 | `client.games` |
| [Drives](drives_api.md) | 1 | `client.drives` |
| [Plays](plays_api.md) | 5 | `client.plays` |
| [Venues](venues_api.md) | 1 | `client.venues` |
| [Conferences](conferences_api.md) | 3 | `client.conferences` |
| [Teams](teams_api.md) | 6 | `client.teams` |
| [Stats](stats_api.md) | 8 | `client.stats` |
| [Metrics](metrics_api.md) | 8 | `client.metrics` |
| [Ratings](ratings_api.md) | 7 | `client.ratings` |
| [Players](players_api.md) | 5 | `client.players` |

`CFBDClient` sends authenticated GET requests to the canonical API origin by
default. Request fields use snake case in Python and serialize to upstream
aliases such as `seasonType`, `gameId`, or `id`. `game_id` is the consistent
public ID name. Unknown fields and invalid combinations fail before HTTP.

All decoded responses pass through the endpoint's Pydantic model before frame
conversion. Nested `/games/teams`, `/games/players`, scoreboard, records, and
drives structures remain nested. pandas stores nested values in `object`
columns; Polars uses native `Struct` and `List` columns. Team matchup is a
one-row frame with nested games. Advanced box score and live plays are returned
as nested Pydantic models. Team season Stats preserve the upstream
`string | number` value as pandas `object` or Polars `Object`.

See the top-level [`README.md`](../../README.md) for lifecycle, authentication,
retry, error, dtype, and installation contracts.
