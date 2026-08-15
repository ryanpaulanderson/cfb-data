# Teams API

| Method | Route | Filters | Result grain |
| --- | --- | --- | --- |
| `client.teams.list` | `GET /teams` | `conference`, `year` | one row per team |
| `client.teams.fbs` | `GET /teams/fbs` | `year` | one row per FBS team |
| `client.teams.matchup` | `GET /teams/matchup` | required `team1`, `team2`; optional `min_year`, `max_year` | one summary row |
| `client.teams.ats` | `GET /teams/ats` | required `year`; optional `conference`, `team` | one row per team |
| `client.teams.roster` | `GET /roster` | `team`, `year`, `classification` | one row per player |
| `client.teams.talent` | `GET /talent` | required `year` | one row per team |

Team rows embed the shared `Venue` location shape. Matchup returns a
one-row frame containing summary values and nested historical games; its
`games` column is pandas `object` or Polars `List[Struct]`. Matchup dates are
required to identify an instant and are normalized to UTC.
