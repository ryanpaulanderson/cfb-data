# ADR 0002: Preserve heterogeneous team-stat scalar values

- Status: Accepted
- Date: 2026-08-12
- Applies from: Stats namespace implementation

## Context

`GET /stats/season` declares `TeamStat.statValue` as `string | number`.
Representative live responses currently contain integers, while the official
contract and database-driver boundary permit strings or floating-point values.
Coercing every value to one primitive type would change the upstream value;
returning a model would make one otherwise tabular Stats route inconsistent.

The existing logical schema supports concrete scalars, nullable values, nested
models, and lists. It deliberately rejects arbitrary unions because neither
backend can infer one strict, backend-neutral dtype for them.

## Decision

Add one explicit heterogeneous scalar for exactly `str | int | float`.
Validation rejects booleans and all other values. Conversion preserves each
validated Python value without coercion and maps the column to pandas `object`
and Polars `Object`, including empty frames.

The canonical Arrow and Parquet representation from
[ADR 0003](0003-canonical-arrow-parquet.md) stores this logical scalar as a
tagged struct containing a kind plus nullable string, integer, and float slots.
Exactly one slot must match the kind. DataFrame adapters decode that
storage-only struct back to the original scalar.

This is not a general union fallback. Other unions remain conversion errors and
new heterogeneous contracts require a deliberate schema decision.

## Consequences

- Team season statistics preserve the official response semantics.
- Both backends expose the same logical values and an explicit object dtype.
- Versioned Parquet preserves the exact scalar type without using an
  unsupported Arrow union or coercing all values to text.
- Consumers must narrow individual `stat_value` values before numeric work.
- Unsupported unions cannot silently degrade to object columns.
