# Results and DataFrames

Most endpoint methods validate their rows into one canonical PyArrow table and
then return an eager DataFrame in the backend selected when the client is
constructed. A small number return Pydantic models because their nested result
does not have one natural table.

## Stable table contract

For DataFrame-returning endpoints, response model field order defines the
exact recursive Arrow schema and snake-case column order. API row order and row
count are preserved. Conversion does not flatten or explode nested values,
create an ID index, or drop rows. Empty and all-null responses retain the
complete typed schema.

The two backends preserve the same logical values:

| Logical value | pandas | Polars |
| --- | --- | --- |
| Required integer, float, Boolean | `int64`, `float64`, `bool` | `Int64`, `Float64`, `Boolean` |
| Nullable integer, float, Boolean | `Int64`, `Float64`, `boolean` | `Int64`, `Float64`, `Boolean` |
| Text | pandas `string` | `String` |
| UTC timestamp | `datetime64[ns, UTC]` | UTC `Datetime` |
| Nested object or object list | Python mapping/list in `object` | `Struct` / `List[Struct]` |

All response timestamps must identify a timezone and are normalized to UTC
before conversion. The Stats `stat_value` field is explicitly heterogeneous:
strings, integers, and floats are preserved without coercion and use pandas
`object` or Polars `Object`.

## Model-returning endpoints

These endpoints intentionally return validated models:

| Method | Result | Reason |
| --- | --- | --- |
| `client.games.advanced_box_score` | {class}`~cfb_data.games.models.pydantic.responses.AdvancedBoxScore` | Game, team, and player sections have different grains |
| `client.plays.live` | {class}`~cfb_data.plays.models.pydantic.responses.LiveGame` | Current game state contains nested drives and plays |
| `client.playoffs.cfp` | {class}`~cfb_data.playoffs.models.pydantic.responses.CfpPlayoff` | A complete playoff bracket is nested |
| `client.info.account` | {class}`~cfb_data.info.models.pydantic.responses.UserInfo` | Operational account metadata |
| `client.info.usage` | {class}`~cfb_data.info.models.pydantic.responses.UserUsage` | Operational usage metadata |

Other nested results can still be one-row frames. Team matchup, player season
overview, and coach profile preserve their nested columns without flattening.
Rankings retain polls and ranks, betting retains provider lines, and coach
summaries retain seasons.

## Discover columns

The [response model reference](../reference/responses.rst) documents the
validated row models and their field signatures. At runtime, inspect the
selected frame normally:

```python
async with CFBDClient() as client:
    games = await client.games.list(year=2024, team="Michigan")

print(games.columns.tolist())
print(games.dtypes)
print(games.head())
```

Raw JSON and a general response-model return mode are intentionally not public
API. Use a typed namespace method so request validation, response validation,
and schema preservation remain in force.

## Parquet persistence

Version 0.3.0 includes a private, versioned Parquet codec for future
library-owned caches. It uses the canonical Arrow schema, atomic file
replacement, compatibility metadata, and full Pydantic validation by default.
Public save/load methods, cache policy, and remote or partitioned storage are
not yet part of the supported API. Direct pandas and Polars Parquet methods do
not define cfb-data's persistence compatibility contract.
