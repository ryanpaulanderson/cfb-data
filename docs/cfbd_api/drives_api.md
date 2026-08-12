# CFBD drives endpoint contract

Contract basis: the current
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
from cfb_data.drives import CFBDDrivesValidationAPI

api = CFBDDrivesValidationAPI(api_key="...")
drives = await api.make_request(
    "/drives",
    {"year": 2024, "team": "Michigan"},
)
```

Use `CFBDDrivesAPI` for raw JSON responses or `CFBDDrivesPandasAPI` for a
Pandera-validated DataFrame. Request models accept snake-case Python names and
serialize them to the API's camel-case query names.
