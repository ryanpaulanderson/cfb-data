# Draft API

| Method | Route | Filters | Result grain |
| --- | --- | --- | --- |
| `client.draft.teams` | `GET /draft/teams` | none | one row per NFL team |
| `client.draft.positions` | `GET /draft/positions` | none | one row per draft position |
| `client.draft.picks` | `GET /draft/picks` | `year`, `team`, `school`, `conference`, `position` | one row per pick |

Draft-pick years start at 1936. Team, school, conference, and position filters
must be non-empty when supplied. Picks preserve NFL team, college, athlete,
position, hometown, round, pick, and pre-draft ranking information in exact
response-model field order.

All three methods return the selected eager DataFrame backend. The team and
position routes are reference-data requests and accept no filters.

```python
async with CFBDClient() as client:
    positions = await client.draft.positions()
    picks = await client.draft.picks(year=2024, school="Michigan")
```
