# Requests and allowed values

Every filtered endpoint has one Pydantic request model. It checks field names,
types, numeric bounds, enum values, aliases, and relationships between
selectors.

## Two equivalent call styles

Use explicit snake-case keywords for one-off calls:

```python
from cfb_data.enums import teams

games = await client.games.list(
    year=2024,
    season_type="regular",
    team=teams.Michigan,
)
```

Use a request object when validation or reuse belongs outside the call:

```python
from cfb_data import GamesRequest, SeasonType
from cfb_data.enums import teams

request = GamesRequest(
    year=2024,
    season_type=SeasonType.regular,
    team=teams.Michigan,
)
games = await client.games.list(request)
```

Do not mix a positional request model with keyword filters. Passing the wrong
request model or mixing styles raises `TypeError`. Unknown keyword filters,
invalid values, and invalid selector combinations raise
{class}`cfb_data.CFBDRequestValidationError` before HTTP. Constructing a
Pydantic request model directly instead raises Pydantic's `ValidationError` at
construction time.

## Python names and upstream names

Public Python fields are always snake case. Models serialize the spelling
expected by the upstream API, such as `seasonType`, `mediaType`, `gameId`, or
`id`. A game identifier is consistently named `game_id` in Python even when
the upstream route calls it `id`.

This means application code should use:

```python
weather = await client.games.weather(game_id=401628347)
```

not `gameId` or `id`. Extra fields are forbidden so misspellings cannot become
silent no-op query parameters.

## Use documented string values

Enum fields accept either the exported enum member or its documented string.
For example, these calls are equivalent:

```python
regular_games = await client.games.list(year=2024, season_type="regular")
regular_games = await client.games.list(
    year=2024,
    season_type=SeasonType.regular,
)
```

Strings are case-sensitive. See [Advanced request
details](../advanced/request-details.md) for the complete enum table and
cross-field validation rules. The [endpoint reference](../cfbd_api/README.md)
lists requirements and access tiers for each method.

## Use team and conference names without retyping them

The `teams` and `conferences` enum namespaces contain the exact names returned
by CFBD's season-specific reference endpoints. Their members are strings, so
the same value works in request filters and DataFrame comparisons:

```python
from cfb_data.enums import conferences, teams

games = await client.games.list(
    year=2026,
    team=teams.Michigan,
    conference=conferences.BIGTEN,
)
michigan_home_games = games[games["home_team"] == teams.Michigan]
```

Team members use readable Python names such as `teams.OhioState`,
`teams.MiamiOH`, and `teams.TexasAM`. Conference members use uppercase names
such as `conferences.BIGTEN`, `conferences.SEC`, and
`conferences.MOUNTAINWEST`. Their string values preserve the upstream spelling
and punctuation exactly.

The checked-in catalog covers every FBS, FCS, Division II, and Division III
team and conference returned for {data}`cfb_data.enums.REFERENCE_SEASON`.
Because historical and defunct names can fall outside that snapshot, all team
and conference filters continue to accept ordinary strings. Contributors can
refresh the catalog with an authenticated live API key by running
`REFERENCE_YEAR=2026 make update-reference-enums` for the intended season.

## Requests without filters

Reference endpoints such as `client.venues.list()`, `client.plays.types()`,
`client.stats.categories()`, `client.draft.teams()`, and
`client.metrics.field_goal_expected_points()` take no request object and no
filters. Their empty call signature is intentional.

## Validate before opening a client

Request models are normal Pydantic models, so an application can validate
configuration before it acquires network resources:

```python
from pydantic import ValidationError

from cfb_data import PlaysRequest
from cfb_data.enums import teams

try:
    request = PlaysRequest(year=2024, week=1, team=teams.Michigan)
except ValidationError as exc:
    print(exc)
else:
    async with CFBDClient() as client:
        plays = await client.plays.list(request)
```

## Troubleshooting

| What you see | What to check |
| --- | --- |
| `TypeError` about mixed styles | Pass either one request model or keyword filters, not both. |
| `CFBDRequestValidationError` for an extra field | Use the snake-case Python name from the endpoint reference. |
| A selector is reported as missing | Some endpoints require a year, team, game ID, or combination of filters. |
| An enum value is rejected | Check spelling and capitalization; string values are case-sensitive. |
| Direct model construction raises `ValidationError` | This is Pydantic validating before the client call; fix the same field or selector issue. |
