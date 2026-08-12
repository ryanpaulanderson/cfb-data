# Stats API

| Method | Route | Required selectors | Result grain |
| --- | --- | --- | --- |
| `client.stats.player_season` | `GET /stats/player/season` | `year` | one row per player statistic |
| `client.stats.player_season_success` | `GET /stats/player/success` | `year` or `player_id` | one row per player season |
| `client.stats.player_game_success` | `GET /stats/player/success/game` | `year` and one of `week`, `team`, `player_id` | one row per player game |
| `client.stats.team_season` | `GET /stats/season` | `year` or `team` | one row per team statistic |
| `client.stats.categories` | `GET /stats/categories` | none | one row per category |
| `client.stats.advanced_season` | `GET /stats/season/advanced` | `year` or `team` | one row per team season |
| `client.stats.advanced_game` | `GET /stats/game/advanced` | `year` or `team` | one row per team game |
| `client.stats.game_havoc` | `GET /stats/game/havoc` | `year` or `team` | one row per team game |

Optional filters follow the official controller and use snake case in Python.
Fields such as `player_id`, `start_week`, `end_week`, `season_type`, and
`exclude_garbage_time` serialize to their camel-case upstream names. Reversed
week ranges and missing required selector combinations fail before HTTP.

Success-rate results retain nested passing and rushing splits. Advanced season,
advanced game, and havoc results retain nested offense and defense structures.
pandas represents these structures as mappings in `object` columns; Polars uses
native `Struct` columns.

`GET /stats/categories` returns a raw JSON string array upstream. The client
validates every item and presents it as a one-column `category` frame while
preserving order. `TeamStat.statValue` is officially `string | number`; the
public `stat_value` column preserves strings, integers, and floats without
coercion and uses pandas `object` or Polars `Object`.
