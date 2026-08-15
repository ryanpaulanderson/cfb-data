# Plays endpoint reference

Sources: the current
[CFBD API reference](https://api.collegefootballdata.com/api) and the official
[`plays/controller.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/plays/controller.ts),
[`plays/types.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/plays/types.ts),
and
[`live/controller.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/live/controller.ts)
from API version 5.24.0.

## Request options

| Route | Required selector | Optional filters |
| --- | --- | --- |
| `GET /plays` | `year` and `week` | `team`, `offense`, `defense`, `offenseConference`, `defenseConference`, `conference`, `playType`, `seasonType`, `classification` |
| `GET /plays/types` | None | None |
| `GET /plays/stats` | None | `year`, `week`, `team`, `gameId`, `athleteId`, `statTypeId`, `seasonType`, `conference` |
| `GET /plays/stats/types` | None | None |
| `GET /live/plays` | `gameId` | None |

The historical play-stat route permits an unfiltered request but limits its
response to 2,000 rows. Years before 1869, negative weeks, and non-positive
game, athlete, and stat-type IDs fail locally before HTTP. The live route
requires Patreon Tier 2 or higher.

Python request fields use snake case and serialize to the upstream camel-case
names shown above. `game_id` remains the public name for every game identifier.

## Returned data

`GET /plays` returns one row per historical play, including game, drive, team,
score, period, clock, field position, down and distance, play text and type,
PPA, and nullable wall-clock time. `GET /plays/stats` returns athlete/stat-type
associations at play grain. The two type routes return the upstream reference
tables in their documented order.

The four historical routes return the selected pandas or Polars DataFrame.
Nested clock values remain objects in pandas and native structs in Polars;
wall-clock timestamps are validated and normalized to UTC. Empty responses
retain the complete typed schema.

`GET /live/plays` returns one `LiveGame` model containing current game state,
team aggregates, drives, and nested plays. Live play wall-clock values are
timezone-aware UTC datetimes. `deserveToWin` is optional because upstream omits
it when its auxiliary prediction service is unavailable.

```python
from cfb_data import CFBDClient
from cfb_data.enums import teams

async with CFBDClient() as client:
    plays = await client.plays.list(year=2024, week=1, team=teams.Michigan)
    play_types = await client.plays.types()
    stats = await client.plays.stats(year=2024, week=1, team=teams.Michigan)
    stat_types = await client.plays.stat_types()
    live = await client.plays.live(game_id=401628347)
```
