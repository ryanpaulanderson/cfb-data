# CFBD games endpoint contracts

Contract basis: the current
[CFBD games API reference](https://api.collegefootballdata.com/api/games) and
the official
[`games/controller.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/games/controller.ts),
[`games/types.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/games/types.ts),
and
[`boxScores/types.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/boxScores/types.ts),
with endpoint access rules from
[`config/auth.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/config/auth.ts)
from API version 5.24.0.

## Request contracts

| Route | Required selector | Optional filters |
| --- | --- | --- |
| `GET /games` | `year`, unless upstream `id` (`game_id`) is present | `week`, `seasonType`, `classification`, `team`, `home`, `away`, `conference`, `id`, `competition`, `round` |
| `GET /games/teams` | upstream `id` (`game_id`), or `year` plus at least one of `week`, `team`, or `conference` | `classification`, `seasonType` |
| `GET /games/players` | upstream `id` (`game_id`), or `year` plus at least one of `week`, `team`, or `conference` | `classification`, `seasonType`, `category` |
| `GET /games/media` | `year` | `seasonType`, `week`, `team`, `conference`, `mediaType`, `classification` |
| `GET /games/weather` | upstream `gameId` (`game_id`), or `year` | `seasonType`, `week`, `team`, `conference`, `classification` |
| `GET /records` | At least one of `year` or `team` | `conference` |
| `GET /calendar` | `year` | None |
| `GET /scoreboard` | None; `classification` defaults upstream to `fbs` | `classification`, `conference` |
| `GET /game/box/advanced` | upstream `id` (`game_id`) | None |

`/games/weather` and `/scoreboard` require Patreon Tier 1 or higher. A `round`
filter requires `competition=cfp`. CFP competition filters may only be
combined with `seasonType=postseason` or `seasonType=both`.

Supported enums are:

- `seasonType`: `regular`, `postseason`, `both`, `allstar`,
  `spring_regular`, or `spring_postseason`;
- `classification`: `fbs`, `fcs`, `ii`, or `iii`;
- `mediaType`: `tv`, `radio`, `web`, `ppv`, or `mobile`;
- `competition`: `cfp`;
- `round`: `first_round`, `quarterfinal`, `semifinal`, or `championship`.

The upstream specification declares years, weeks, and IDs as integers without
a fixed future-year ceiling. The local client rejects seasons before 1869 and
non-positive IDs, but intentionally does not embed a stale maximum year.

## Response contracts

### `/games`

Returns `Game[]`. Each game includes scheduling and completion state, venue,
home and away team IDs and classifications, scores and line scores, Elo and win
probability values, highlights and notes, and nullable playoff metadata.

### `/games/teams`

Returns `GameTeamStats[]` in this shape:

```json
[
  {
    "id": 401628347,
    "teams": [
      {
        "teamId": 333,
        "team": "Alabama",
        "conference": "SEC",
        "homeAway": "home",
        "points": 63,
        "stats": [{ "category": "totalYards", "stat": "600" }]
      }
    ]
  }
]
```

### `/games/players`

Returns `GamePlayerStats[]`. Each game contains teams; each team contains
categories; each category contains statistic types; and each statistic type
contains athlete `id`, `name`, and `stat` values. Statistics are strings
because upstream values include compound displays such as `7/9`.

### `/games/media`

Returns one object per media outlet with `mediaType` and `outlet`, alongside the
game, season, start time, and participating teams.

### `/games/weather`

Returns game and venue identity plus temperature, dew point, humidity,
precipitation, snowfall, wind, pressure, and weather-condition fields. Numeric
weather fields are nullable.

### `/records`

Returns one object per team season. `total`, `conferenceGames`, `homeGames`,
`awayGames`, `neutralSiteGames`, `regularSeason`, and `postseason` are nested
objects containing `games`, `wins`, `losses`, and `ties`.

### `/calendar`

Returns season week, season type, start date, and end date. The API continues
to return the deprecated aliases `firstGameStart` and `lastGameStart`.

### `/scoreboard`

Returns the current scoreboard as `ScoreboardGame[]`. Each game includes its
start time and status, live clock and possession state, venue, nested home and
away teams with scores and win probabilities, weather, and betting data.
Nullable fields remain present in the response, including before kickoff or
when a data provider does not supply a value.

### `/game/box/advanced`

Returns one object with three sections:

- `gameInfo`: teams, scores, win probabilities, winner, and excitement;
- `teams`: PPA, cumulative PPA, success rates, explosiveness, rushing, havoc,
  scoring opportunities, and field position;
- `players`: usage and average/cumulative PPA.

## Client examples

```python
from cfb_data import CFBDClient, GamesRequest

async with CFBDClient() as client:
    games = await client.games.list(year=2024, team="Michigan")
    same_games = await client.games.list(
        GamesRequest(year=2024, team="Michigan")
    )
    box = await client.games.advanced_box_score(game_id=401628347)
```

All methods except `advanced_box_score` return the client's selected pandas or
Polars DataFrame. Raw JSON and general validated-model modes are not exposed.
Advanced box score returns `AdvancedBoxScore` because its three nested sections
do not have one natural row shape.
