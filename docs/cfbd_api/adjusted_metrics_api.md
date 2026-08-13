# Adjusted Metrics API

All Adjusted Metrics routes require Patreon Tier 1 access.

| Method | Route | Filters | Result grain |
| --- | --- | --- | --- |
| `client.adjusted_metrics.team_season` | `GET /wepa/team/season` | `year`, `team`, `conference` | one row per team season |
| `client.adjusted_metrics.player_passing` | `GET /wepa/players/passing` | `year`, `team`, `conference`, `position` | one row per passer |
| `client.adjusted_metrics.player_rushing` | `GET /wepa/players/rushing` | `year`, `team`, `conference`, `position` | one row per rusher |
| `client.adjusted_metrics.kicker_paar` | `GET /wepa/players/kicking` | `year`, `team`, `conference` | one row per kicker |

All filters are optional according to the upstream routes. Years start at 1869
and text filters must be non-empty when supplied. Team results preserve nested
EPA, success-rate, and rushing splits. Player results preserve weighted EPA or
points-above-average metrics in their declared response fields.

Every method returns the selected eager DataFrame backend while preserving API
row order and exact response-model field order.
