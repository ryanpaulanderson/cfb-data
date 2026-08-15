# Drives endpoint reference

Sources: the current
[CFBD drives API reference](https://api.collegefootballdata.com/api/drives) and
the official
[`drives/controller.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/drives/controller.ts)
and
[`drives/types.ts`](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/drives/types.ts)
from API version 5.24.0.

## `GET /drives`

`year` is required. The optional parameters are `seasonType`, `week`, `team`,
`offense`, `defense`, `conference`, `offenseConference`,
`defenseConference`, and `classification`.

The response is an array of drive objects. Each object contains:

- offense and defense names and nullable conference names;
- `gameId`, string drive `id`, and nullable `driveNumber`;
- scoring status and home-offense status;
- start and end period, yard line, yards to goal, and clock;
- elapsed minutes and seconds;
- play count, yards, result, and start/end scores.

The `startTime`, `endTime`, and `elapsed` objects each contain nullable integer
`minutes` and `seconds` values. `offenseConference`, `defenseConference`, and
`driveNumber` are required response keys whose values may be null.

```python
from cfb_data import CFBDClient, DrivesRequest
from cfb_data.enums import teams

async with CFBDClient() as client:
    drives = await client.drives.list(year=2024, team=teams.Michigan)
    same_drives = await client.drives.list(
        DrivesRequest(year=2024, team=teams.Michigan)
    )
```

The result is the selected pandas or Polars DataFrame. Request models and
keyword filters use snake-case Python names and serialize to upstream
camel-case query names. Raw JSON and general validated-model return modes are
not exposed.
