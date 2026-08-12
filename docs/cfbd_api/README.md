# Implemented CFBD endpoint contracts

These notes cover only endpoint contracts implemented by `CFBDClient`. They
were reconciled on August 12, 2026 with the current
[CFBD API reference](https://api.collegefootballdata.com/api) and versioned
official [`CFBD/cfb-api-v2`](https://github.com/CFBD/cfb-api-v2) source.

| Family | Routes | Public namespace |
| --- | ---: | --- |
| [Games](games_api.md) | 9 | `client.games` |
| [Drives](drives_api.md) | 1 | `client.drives` |

`CFBDClient` sends authenticated GET requests to the canonical API origin by
default. Request fields use snake case in Python and serialize to upstream
aliases such as `seasonType`, `gameId`, or `id`. `game_id` is the consistent
public ID name. Unknown fields and invalid combinations fail before HTTP.

All decoded responses pass through the endpoint's Pydantic model before frame
conversion. Nested `/games/teams`, `/games/players`, scoreboard, records, and
drives structures remain nested. pandas stores nested values in `object`
columns; Polars uses native `Struct` and `List` columns. Advanced box score is
returned as one nested Pydantic model.

See the top-level [`README.md`](../../README.md) for lifecycle, authentication,
retry, error, dtype, and installation contracts.
