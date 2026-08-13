# Playoffs API

| Method | Route | Required selector | Optional filters | Result |
| --- | --- | --- | --- | --- |
| `client.playoffs.cfp` | `GET /playoffs/cfp` | `year` | none | nested `CfpPlayoff` model |
| `client.playoffs.participants` | `GET /playoffs/cfp/participants` | `year` | none | participant DataFrame |
| `client.playoffs.games` | `GET /playoffs/cfp/games` | `year` | `round` | matchup DataFrame |

CFP years start at 2014. The optional round accepts `first_round`,
`quarterfinal`, `semifinal`, or `championship`.

The complete playoff route returns a validated nested model because bracket,
participant, game, and outcome sections do not form one natural table. The
participant and game routes return the selected eager DataFrame backend.
Timestamps must identify a timezone and are normalized to UTC.

```python
async with CFBDClient() as client:
    bracket = await client.playoffs.cfp(year=2024)
    semifinals = await client.playoffs.games(year=2024, round="semifinal")

print(bracket.champion)
```
