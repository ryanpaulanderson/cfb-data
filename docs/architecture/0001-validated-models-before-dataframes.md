# ADR 0001: Validate models before DataFrame conversion

- Status: Accepted
- Date: 2026-08-12
- Applies from: `cfb-data` 0.2.0

## Context

The 0.1.x implementation coupled three inherited client layers to route
metadata: raw JSON, Pydantic models, and Pandera-validated pandas DataFrames.
That design duplicated response constraints, created a public generic path
router, opened a new HTTP session for individual calls, and made adding another
DataFrame implementation an inheritance problem.

The library needs one stable endpoint interface whose concrete table backend
can vary. It also needs a trustworthy foundation for richer user-defined data
products: an ID from one endpoint may select another endpoint, multiple results
may be joined, and a composed dataset may itself become an input to a larger
orchestration.

## Decision

`CFBDClient` uses composition and the following dependency direction:

```text
GamesResource / DrivesResource / PlaysResource
                    │
                    ▼
      endpoint executor
             │
             ▼
 async HTTP transport ──► decoded JSON
             │
             ▼
 Pydantic TypeAdapter validation
             │
             ▼
     validated row models
             │
             ▼
 annotation-derived logical schema
             │
       ┌─────┴─────┐
       ▼           ▼
    pandas       Polars
```

Pydantic response models are the sole authoritative external-data contract.
The executor validates list responses with typed `TypeAdapter` instances and
validates advanced box score as one model. DataFrame adapters never receive raw
JSON.

The logical table schema is derived recursively from each row model's declared
field order and annotations. Supported values are integers, floats, booleans,
strings and `StrEnum` values, timezone-aware UTC datetimes, nullable `T | None`,
nested `BaseModel` structs, and recursive lists. An unsupported annotation is
an explicit conversion failure; it never degrades to an unspecified object or
`Any` column.

Models are dumped in Python mode by field name. API row order, snake-case
column order, nulls, and nesting are preserved. Conversion does not flatten,
explode, add an ID index, or drop records. pandas represents structs/lists as
objects; Polars represents them as native `Struct`/`List` values.

The transport owns authentication, one reusable session, finite per-attempt
timeouts, HTTP handling, and bounded safe-GET retries. The client is a one-shot
async context manager so session ownership and cleanup are deterministic.

## Public return modes

Tabular endpoint responses return the selected eager DataFrame type. Raw JSON
and general validated-model modes are excluded. Advanced box score and live
plays are the exceptions because their nested sections lack one natural table.
Team matchup remains tabular as one summary row with nested games.

The former client hierarchy, route decorator, generic
`make_request(path, params)` entry point, Pandera schemas, and Pandera runtime
dependency are removed without compatibility wrappers.

## Dataset and workflow extension hierarchy

Higher layers must preserve validation before presentation:

```text
workflow
├── endpoint call
├── dataset
│   ├── endpoint result
│   ├── endpoint result
│   └── subdataset
└── broader control flow / multiple artifacts
```

A **dataset** composes validated endpoint models or validated subdataset row
models. It may gather IDs, issue dependent endpoint queries, and perform joins,
but it defines and validates an authoritative final tabular row model before
converting that final result through the selected adapter. Intermediate joins
are not exposed as partially validated public DataFrames.

A **workflow** orchestrates endpoints, datasets, and subdatasets above that
layer. It may branch, repeat, coordinate multiple validation scenarios, and
return multiple artifacts rather than one table.

Version 0.2.0 reserves these boundaries but does not expose
`client.datasets` or `client.workflows`. Concrete abstractions will be added
only with real dataset and orchestration requirements.

## Consequences

- One endpoint surface supports pandas and Polars without backend-specific
  clients.
- Response constraints and enum membership have one owner.
- Invalid external values fail before analytical objects exist.
- Dataset builders can consume an internal validated-model interface without
  converting and re-validating intermediate DataFrames.
- Adding a logical type requires deliberate support in both adapters.
- Backend-native nested representation differs, while logical values and
  table shape remain invariant.
- Supporting another backend requires an adapter, not another client
  inheritance branch.
