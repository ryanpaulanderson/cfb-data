# College Football Data Python Toolkit

`cfb-data` 0.2.0 is an asynchronous, validated client for implemented
[CollegeFootballData API](https://collegefootballdata.com/) game, play, stats,
metrics, ratings, player, and reference-data endpoints. It returns eager pandas
DataFrames by default and can return the same logical tables as Polars
DataFrames.

The request path is explicit:

```text
HTTP transport → Pydantic validation → validated models → logical schema → DataFrame
```

Malformed upstream data never reaches a DataFrame. Choosing Polars changes the
concrete return type and native nested representation, not endpoint names,
validation, retry behavior, columns, row order, or logical values.

## Installation

pandas is included in the default installation:

```sh
python -m pip install cfb-data
```

Install the optional Polars backend with:

```sh
python -m pip install "cfb-data[polars]"
```

Python 3.11 through 3.13 is supported. DataFrames are eager; Polars
`LazyFrame` results are not part of the 0.2.0 contract.

## Authentication and lifecycle

Set a CollegeFootballData API key in the environment:

```sh
export CFBD_API_KEY="..."
```

Every client is one-shot and must own its reusable HTTP session through
`async with`:

```python
import asyncio

from cfb_data import CFBDClient


async def main() -> None:
    async with CFBDClient() as client:
        games = await client.games.list(year=2024, team="Michigan")
        drives = await client.drives.list(year=2024, team="Michigan")
        plays = await client.plays.list(year=2024, week=1, team="Michigan")
        stats = await client.stats.team_season(year=2024, team="Michigan")
        ratings = await client.ratings.elo(year=2024, team="Michigan")
        players = await client.players.search(
            search_term="Edwards", year=2024, team="Michigan"
        )
        teams = await client.teams.fbs(year=2024)

    print(games.head())
    print(drives.head())
    print(plays.head())
    print(stats.head())
    print(ratings.head())
    print(players.head())
    print(teams.head())


asyncio.run(main())
```

An explicit non-empty `api_key` takes precedence over `CFBD_API_KEY`. Passing
an empty explicit value is a configuration error and does not fall back to the
environment. Calls before context entry, after exit, during a nested entry, or
after attempted re-entry raise `CFBDClientStateError`.

For Polars, select only the backend:

```python
from cfb_data import CFBDClient

async with CFBDClient(dataframe_backend="polars") as client:
    calendar = await client.games.calendar(year=2024)
```

Type checkers infer `pandas.DataFrame` for the default client and
`polars.DataFrame` when the literal backend is `"polars"`.

## Endpoints

Each method accepts either one positional request model or explicit snake-case
keyword filters. The styles are mutually exclusive:

```python
from cfb_data import CFBDClient, GamesRequest, SeasonType

request = GamesRequest(year=2024, season_type=SeasonType.regular)

async with CFBDClient() as client:
    by_model = await client.games.list(request)
    by_keywords = await client.games.list(year=2024, season_type="regular")
```

Unknown filters and invalid combinations fail before HTTP. The public Python
name is always `game_id`; request serialization maps it to upstream `id` or
`gameId` as required.

| Method | Request model | Result |
| --- | --- | --- |
| `client.games.list` | `GamesRequest` | `Game` rows as selected frame |
| `client.games.records` | `RecordsRequest` | `TeamRecords` rows as selected frame |
| `client.games.calendar` | `CalendarRequest` | `CalendarWeek` rows as selected frame |
| `client.games.scoreboard` | `ScoreboardRequest` | `ScoreboardGame` rows as selected frame |
| `client.games.media` | `GameMediaRequest` | `GameMedia` rows as selected frame |
| `client.games.weather` | `GameWeatherRequest` | `GameWeather` rows as selected frame |
| `client.games.player_stats` | `PlayerGameStatsRequest` | `PlayerGameStats` rows as selected frame |
| `client.games.team_stats` | `TeamGameStatsRequest` | `TeamGameStats` rows as selected frame |
| `client.games.advanced_box_score` | `AdvancedBoxScoreRequest` | `AdvancedBoxScore` model |
| `client.drives.list` | `DrivesRequest` | `Drive` rows as selected frame |
| `client.plays.list` | `PlaysRequest` | `Play` rows as selected frame |
| `client.plays.types` | None | `PlayType` rows as selected frame |
| `client.plays.stats` | `PlayStatsRequest` | `PlayStat` rows as selected frame |
| `client.plays.stat_types` | None | `PlayStatType` rows as selected frame |
| `client.plays.live` | `LivePlaysRequest` | `LiveGame` model |
| `client.venues.list` | None | `Venue` rows as selected frame |
| `client.conferences.list` | `ConferencesRequest` | `Conference` rows as selected frame |
| `client.conferences.changes` | `ConferenceChangesRequest` | `TeamConferenceChange` rows as selected frame |
| `client.conferences.affiliations` | `ConferenceAffiliationsRequest` | `TeamConferenceAffiliation` rows as selected frame |
| `client.teams.list` | `TeamsRequest` | `Team` rows as selected frame |
| `client.teams.fbs` | `FBSTeamsRequest` | `Team` rows as selected frame |
| `client.teams.matchup` | `TeamMatchupRequest` | one `Matchup` row as selected frame |
| `client.teams.ats` | `TeamATSRequest` | `TeamATS` rows as selected frame |
| `client.teams.roster` | `RosterRequest` | `RosterPlayer` rows as selected frame |
| `client.teams.talent` | `TalentRequest` | `TeamTalent` rows as selected frame |
| `client.stats.player_season` | `PlayerSeasonStatsRequest` | `PlayerStat` rows as selected frame |
| `client.stats.player_season_success` | `PlayerSeasonSuccessRequest` | `PlayerSeasonSuccessRate` rows as selected frame |
| `client.stats.player_game_success` | `PlayerGameSuccessRequest` | `PlayerGameSuccessRate` rows as selected frame |
| `client.stats.team_season` | `TeamSeasonStatsRequest` | `TeamStat` rows as selected frame |
| `client.stats.categories` | None | `StatCategory` rows as selected frame |
| `client.stats.advanced_season` | `AdvancedSeasonStatsRequest` | `AdvancedSeasonStat` rows as selected frame |
| `client.stats.advanced_game` | `AdvancedGameStatsRequest` | `AdvancedGameStat` rows as selected frame |
| `client.stats.game_havoc` | `GameHavocRequest` | `GameHavocStats` rows as selected frame |
| `client.metrics.predicted_points` | `PredictedPointsRequest` | `PredictedPointsValue` rows as selected frame |
| `client.metrics.team_season_ppa` | `TeamSeasonPPARequest` | `TeamSeasonPredictedPointsAdded` rows as selected frame |
| `client.metrics.team_game_ppa` | `TeamGamePPARequest` | `TeamGamePredictedPointsAdded` rows as selected frame |
| `client.metrics.player_game_ppa` | `PlayerGamePPARequest` | `PlayerGamePredictedPointsAdded` rows as selected frame |
| `client.metrics.player_season_ppa` | `PlayerSeasonPPARequest` | `PlayerSeasonPredictedPointsAdded` rows as selected frame |
| `client.metrics.win_probability` | `WinProbabilityRequest` | `PlayWinProbability` rows as selected frame |
| `client.metrics.pregame_win_probability` | `PregameWinProbabilityRequest` | `PregameWinProbability` rows as selected frame |
| `client.metrics.field_goal_expected_points` | None | `FieldGoalExpectedPoints` rows as selected frame |
| `client.ratings.core` | `CoreRatingsRequest` | `TeamCoreRating` rows as selected frame |
| `client.ratings.sp` | `SPRatingsRequest` | `TeamSP` rows as selected frame |
| `client.ratings.conference_sp` | `ConferenceSPRatingsRequest` | `ConferenceSP` rows as selected frame |
| `client.ratings.srs` | `SRSRatingsRequest` | `TeamSRS` rows as selected frame |
| `client.ratings.expanded_srs` | `ExpandedSRSRatingsRequest` | `ExpandedTeamSRS` rows as selected frame |
| `client.ratings.elo` | `EloRatingsRequest` | `TeamElo` rows as selected frame |
| `client.ratings.fpi` | `FPIRatingsRequest` | `TeamFPI` rows as selected frame |
| `client.players.search` | `PlayerSearchRequest` | `PlayerSearchResult` rows as selected frame |
| `client.players.usage` | `PlayerUsageRequest` | `PlayerUsage` rows as selected frame |
| `client.players.season_overview` | `PlayerSeasonOverviewRequest` | one `PlayerSeasonOverview` row as selected frame |
| `client.players.returning_production` | `ReturningProductionRequest` | `ReturningProduction` rows as selected frame |
| `client.players.transfer_portal` | `TransferPortalRequest` | `PlayerTransfer` rows as selected frame |

Request models and shared `StrEnum` values are exported from `cfb_data` and
their supported domain namespaces. Enum fields also accept their documented
string values.

Raw JSON and general validated-model return modes are intentionally excluded.
Advanced box score and live plays return models because their nested sections
do not form one natural table. The upstream live-plays route requires Patreon
Tier 2 access.

Team matchup and player season overview are one-row frames containing nested
columns. pandas represents nested values as `object`; Polars represents them
as native `Struct` and `List[Struct]` values.

## DataFrame contract

Response model field order defines exact snake-case column order. API row order
and row count are preserved. Conversion never flattens, explodes, indexes by
ID, or drops rows, and an empty response produces a correctly typed empty
frame.

pandas uses:

- `int64`, `float64`, and `bool` for required scalars;
- `Int64`, `Float64`, and `boolean` for nullable scalars;
- pandas `string` and `datetime64[ns, UTC]` dtypes;
- `object` columns for nested structs and lists;
- `object` for the explicitly heterogeneous Stats `stat_value` scalar;
- a normal `RangeIndex`.

Polars uses strict `Int64`, `Float64`, `Boolean`, `String`, UTC `Datetime`,
`Struct`, `List`, and the explicit heterogeneous `Object` Stats scalar. This
means nested values have the same logical content while remaining Python
mappings/lists in pandas and native nested columns in Polars. The
`client.stats.team_season` `stat_value` column preserves each upstream string,
integer, or float without coercion and is `object`/`Object` in both backends.

All response timestamps must include a timezone. Validation normalizes them to
UTC before conversion.

## Retries and errors

The default immutable `RetryPolicy` makes at most three total safe GET
attempts. It retries connection failures, timeouts, truncated payloads, and
HTTP `408`, `429`, `500`, `502`, `503`, and `504` with capped exponential
full-jitter backoff. Set `RetryPolicy(max_attempts=1)` to disable retries.

Valid numeric and HTTP-date `Retry-After` values are honored up to 30 seconds.
A longer requested delay fails immediately and remains available as
`retry_after_seconds` on the HTTP error. Redirects are disabled, TLS
verification remains enabled, every attempt has a finite timeout, and
cancellation is preserved.

```python
from cfb_data import CFBDClient, RetryPolicy

policy = RetryPolicy(
    max_attempts=4,
    base_delay_seconds=0.25,
    max_backoff_seconds=4.0,
    max_retry_after_seconds=20.0,
)

async with CFBDClient(retry_policy=policy) as client:
    scoreboard = await client.games.scoreboard()
```

All library exceptions derive from `CFBDError`. Public subclasses distinguish
configuration, optional dependencies, client state, request validation,
timeouts and transport, HTTP/authentication/authorization/rate-limit/server
responses, response decoding and validation, and DataFrame conversion. Error
text and debug retry events include only safe endpoint/status/attempt metadata,
never credentials, query parameters, response payloads, or secrets.

## Migrating from 0.1.x

The inherited raw, validation, and pandas client families were removed rather
than retained as compatibility wrappers.

Raw client calls:

```python
# Before: CFBDGamesAPI(...).make_request("/games", {"year": 2024})
async with CFBDClient() as client:
    games = await client.games.list(year=2024)
```

Validated-model client calls:

```python
# Before: CFBDGamesValidationAPI(...).make_request("/calendar", {"year": 2024})
async with CFBDClient() as client:
    calendar_frame = await client.games.calendar(year=2024)
```

pandas client calls:

```python
# Before: CFBDDrivesPandasAPI(...).make_request("/drives", {"year": 2024})
async with CFBDClient() as client:
    drives_frame = await client.drives.list(year=2024)
```

There is no public generic path router or `make_request(path, params)` method.
Use the typed namespace method and either its request model or keyword filters.

## Datasets and workflows

Version 0.2.0 does not expose `client.datasets` or `client.workflows`. The
accepted architecture reserves two higher layers:

- datasets compose validated endpoint results and validated subdatasets
  through joins into one validated tabular row model, converting only the
  final table;
- workflows orchestrate endpoints, datasets, and broader control flow and may
  return multiple artifacts.

See
[`docs/architecture/0001-validated-models-before-dataframes.md`](docs/architecture/0001-validated-models-before-dataframes.md)
for the decision and extension boundaries.

## Development

```sh
git clone https://github.com/ryanpaulanderson/cfb-data.git
cd cfb-data
make install
make hooks
make format
make check
```

`make install` creates `.venv` and installs `.[dev,polars]`, giving
contributors the complete two-backend test contract. `make check` runs Ruff,
strict mypy, and pytest under the same contract as CI. Package metadata and all
dependency groups live only in `pyproject.toml`.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`docs/project-status.md`](docs/project-status.md) for repository and release
status.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

This project is not affiliated with CollegeFootballData.com.
