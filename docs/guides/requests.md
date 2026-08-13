# Requests and allowed values

Every filtered endpoint has one Pydantic request model. The model is the
authoritative boundary for field names, types, numeric bounds, allowed enum
values, aliases, and relationships between selectors.

## Two equivalent call styles

Use explicit snake-case keywords for one-off calls:

```python
games = await client.games.list(
    year=2024,
    season_type="regular",
    team="Michigan",
)
```

Use a request object when validation or reuse belongs outside the call:

```python
from cfb_data import GamesRequest, SeasonType

request = GamesRequest(
    year=2024,
    season_type=SeasonType.regular,
    team="Michigan",
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

## Shared allowed values

Enum fields accept either the exported enum member or its exact documented
string value. Values are case-sensitive.

| Enum | Accepted strings | Used for |
| --- | --- | --- |
| {class}`cfb_data.SeasonType` | `regular`, `postseason`, `both`, `allstar`, `spring_regular`, `spring_postseason` | Season phase |
| {class}`cfb_data.Classification` | `fbs`, `fcs`, `ii`, `iii` | Division classification |
| {class}`cfb_data.ConferenceClassification` | `fbs`, `fcs`, `ii`, `ii/iii`, `iii` | Conference classification responses and filters |
| {class}`cfb_data.MediaType` | `tv`, `radio`, `web`, `ppv`, `mobile` | Broadcast medium |
| {class}`cfb_data.RankingPoll` | `cfp` | Supported poll snapshot selector |
| {class}`cfb_data.RecruitClassification` | `JUCO`, `PrepSchool`, `HighSchool` | Recruiting source classification |
| {class}`cfb_data.PlayoffCompetition` | `cfp` | Playoff competition |
| {class}`cfb_data.PlayoffRound` | `first_round`, `quarterfinal`, `semifinal`, `championship` | CFP round |
| {class}`cfb_data.UserUsageApi` | `all`, `cfb`, `cbb` | Account usage product |

{class}`cfb_data.TransferEligibility` describes the response values
`Withdrawn`, `TBD`, `PendingAppeal`, `SittingOne`, and `Immediate`. The
live-play response enums accept `home` or `away` for
{class}`cfb_data.HomeAway`; `rush`, `pass`, or `other` for
{class}`cfb_data.RushPass`; and `passing` or `standard` for
{class}`cfb_data.DownType`. These are validated response values rather than
general request filters.

## Common validation rules

Request requirements vary by upstream route. These rules recur across
namespaces:

- Season years generally start at 1869. Draft years start at 1936 and CFP
  seasons at 2014. The client intentionally does not impose a future-year cap.
- IDs must be positive integers; weeks and similar counters cannot be negative.
- Empty strings are rejected on filters whose request model declares a
  non-empty value.
- A lower bound such as `min_year`, `start_year`, or `start_week` cannot exceed
  its corresponding upper bound.
- Some endpoints require one selector from a group, such as `year` or `team`.
  Game-stat endpoints accept a `game_id` or a grouped season selector.
- CFP `round` requires `competition="cfp"`; CFP competition can only be paired
  with postseason-compatible season types.
- Rankings `latest` and `final` snapshots require `poll="cfp"` and cannot both
  be true.

The [namespace contracts](../cfbd_api/README.md) state endpoint-specific
requirements and access tiers. The generated [request model
reference](../reference/requests.rst) exposes every request class, field type,
default, and docstring from the installed package.

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

try:
    request = PlaysRequest(year=2024, week=1, team="Michigan")
except ValidationError as exc:
    print(exc)
else:
    async with CFBDClient() as client:
        plays = await client.plays.list(request)
```
