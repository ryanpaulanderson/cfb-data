# Work with results

Most endpoint methods return an eager DataFrame. Use pandas by default or
select Polars when constructing the client.

```python
from cfb_data import CFBDClient

async with CFBDClient() as client:
    pandas_games = await client.games.list(year=2024)

async with CFBDClient(dataframe_backend="polars") as client:
    polars_games = await client.games.list(year=2024)
```

The same endpoint has the same columns, row order, nulls, and logical values in
both backends. The concrete dtypes differ in the normal pandas and Polars ways.

## Inspect a result

Treat results like ordinary DataFrames. A quick inspection is often more useful
than reading a long schema page:

```python
async with CFBDClient() as client:
    games = await client.games.list(year=2024, team="Michigan")

print(games.shape)
print(games.columns.tolist())
print(games.dtypes)
print(games.head())
```

For field descriptions before running a call, use the [response model
reference](../reference/responses.rst).

## Example: find high-scoring games

With pandas:

```python
completed = games.dropna(subset=["home_points", "away_points"])
high_scoring = completed.assign(
    total_points=completed["home_points"] + completed["away_points"]
).sort_values("total_points", ascending=False)

print(high_scoring[["week", "home_team", "away_team", "total_points"]].head())
```

With Polars:

```python
import polars as pl

high_scoring = (
    games.drop_nulls(["home_points", "away_points"])
    .with_columns(
        (pl.col("home_points") + pl.col("away_points")).alias("total_points")
    )
    .sort("total_points", descending=True)
)

columns = ["week", "home_team", "away_team", "total_points"]
print(high_scoring.select(columns).head())
```

## Nested columns

Some rows contain a nested object or list that belongs together, such as a
scoreboard clock, betting-provider lines, poll rankings, or a coach's seasons.
The client keeps that structure instead of guessing how your analysis should
flatten it.

- pandas stores nested values as Python dictionaries and lists in `object`
  columns.
- Polars stores them as native `Struct` and `List[Struct]` columns.

Inspect one pandas value before deciding how to normalize it:

```python
async with CFBDClient() as client:
    scoreboard = await client.games.scoreboard()

value = scoreboard.loc[0, "venue"]
print(type(value), value)
```

For pandas, `pandas.json_normalize()` and `DataFrame.explode()` are useful when
you choose to flatten or expand nested data. In Polars, use struct and list
expressions such as `.struct.field()` and `.explode()`.

## Results that are models

A few responses contain several different row grains and are clearer as nested
Pydantic models:

| Method | Why it stays nested |
| --- | --- |
| `client.games.advanced_box_score` | Game, team, and player sections describe different grains. |
| `client.plays.live` | Current game state contains drives and plays. |
| `client.playoffs.cfp` | The complete bracket contains rounds, slots, and linked games. |
| `client.info.account` | Account details are not an analytical table. |
| `client.info.usage` | API usage details are not an analytical table. |

Pydantic models can be inspected directly or converted to Python dictionaries:

```python
async with CFBDClient() as client:
    bracket = await client.playoffs.cfp(year=2024)

print(bracket.champion)
bracket_data = bracket.model_dump()
```

## Empty results

An empty response still returns a DataFrame with the expected columns and
dtypes. This makes it safe to concatenate results across seasons or weeks
without special-casing a missing partition.

```python
import pandas as pd

frames = []
async with CFBDClient() as client:
    for week in range(1, 16):
        frames.append(
            await client.games.list(year=2024, week=week, team="Michigan")
        )

season = pd.concat(frames, ignore_index=True)
```

## Troubleshooting

| What you see | What it means or what to try |
| --- | --- |
| A pandas nested column has dtype `object` | Inspect an individual value; it may be a dictionary or list preserved from the API. |
| A nullable integer is not plain `int64` | pandas uses nullable `Int64` so missing values remain missing instead of becoming floats. |
| A timestamp is UTC | API timestamps are normalized so seasons and endpoints can be compared consistently. |
| An endpoint returned a model instead of a frame | The result has multiple natural grains; use attributes or `.model_dump()`. |
| `CFBDDataFrameConversionError` | Report the endpoint, backend, and package version; the response passed validation but could not be represented. |

## Go deeper

[Advanced result details](../advanced/result-details.md) lists exact pandas,
Polars, Arrow, nested-value, and internal Parquet behavior.
