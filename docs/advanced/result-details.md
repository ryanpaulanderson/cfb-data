# Advanced result details

This page describes exact result representation. For examples of inspecting,
filtering, and flattening results, start with [Work with
results](../guides/results.md).

## DataFrame invariants

For DataFrame-returning endpoints, response model field order defines the
recursive Arrow schema and snake-case column order. API row order and row count
are preserved. Conversion does not flatten nested values, create an ID index,
or drop rows. Empty and all-null responses keep the complete typed schema.

## pandas and Polars dtypes

| Logical value | pandas | Polars |
| --- | --- | --- |
| Required integer | `int64` | `Int64` |
| Required float | `float64` | `Float64` |
| Required Boolean | `bool` | `Boolean` |
| Nullable integer | `Int64` | `Int64` |
| Nullable float | `Float64` | `Float64` |
| Nullable Boolean | `boolean` | `Boolean` |
| Text | pandas `string` | `String` |
| UTC timestamp | `datetime64[ns, UTC]` | UTC `Datetime` |
| Nested object | Python mapping in `object` | `Struct` |
| List of nested objects | Python list in `object` | `List[Struct]` |

All response timestamps identify a timezone and are normalized to UTC before
conversion.

The Stats `stat_value` field is intentionally heterogeneous. Strings, integers,
and floats are preserved without coercion and use pandas `object` or Polars
`Object`.

## Arrow representation

Every tabular response becomes one explicit Arrow table before pandas or
Polars materialization. The schema is derived from the same Pydantic
annotations used for response validation, including:

- declared field order;
- scalar and nullable types;
- UTC timestamps;
- ordered nested structs; and
- typed lists of nested structs.

This shared representation is why backend selection does not change logical
values or column order.

## Model-returning endpoints

These endpoints return validated Pydantic models:

| Method | Result type |
| --- | --- |
| `client.games.advanced_box_score` | {class}`~cfb_data.games.models.pydantic.responses.AdvancedBoxScore` |
| `client.plays.live` | {class}`~cfb_data.plays.models.pydantic.responses.LiveGame` |
| `client.playoffs.cfp` | {class}`~cfb_data.playoffs.models.pydantic.responses.CfpPlayoff` |
| `client.info.account` | {class}`~cfb_data.info.models.pydantic.responses.UserInfo` |
| `client.info.usage` | {class}`~cfb_data.info.models.pydantic.responses.UserUsage` |

Team matchup, player season overview, and coach profile remain one-row frames
with nested columns. Rankings retain polls and ranks, betting retains provider
lines, and coach summaries retain seasons.

## Parquet details

The package contains a private versioned Parquet codec intended for future
library-owned persistence. It uses the canonical Arrow schema, atomic file
replacement, format metadata, and Pydantic validation when reading.

There are no public save/load methods for this codec yet. Ordinary pandas and
Polars Parquet methods remain available, but their type inference may represent
empty, all-null, nested, or heterogeneous values differently. The internal
codec stores the heterogeneous Stats scalar as a tagged struct so its original
string, integer, or float type can be restored.

See [ADR 0003](../architecture/0003-canonical-arrow-parquet.md) for the storage
design and compatibility rules.
