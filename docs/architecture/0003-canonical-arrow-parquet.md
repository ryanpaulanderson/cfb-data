# ADR 0003: Use canonical Arrow tables and versioned Parquet storage

- Status: Accepted
- Date: 2026-08-13
- Applies from: canonical tabular persistence implementation
- Decision narrative:
  [NOD 0001](../notices-of-decision/0001-canonical-nested-tabular-representation.md)

## Context

ADR 0001 established one annotation-derived logical schema with pandas and
Polars presentation adapters. pandas necessarily represents nested structs and
lists as Python objects, while Polars has native `Struct` and `List` columns.
Those values are logically equivalent, but the backend frames are not a safe
storage authority: pandas must infer Parquet types from populated object
values, loses nested type information for empty object columns, and cannot
serialize the heterogeneous Stats scalar. Polars can persist native nesting but
cannot write its Python `Object` scalar.

Future caches, datasets, analytical tools, and feature builders need one typed
representation that is independent of the selected DataFrame backend. Empty
responses, nullable nested values, field order, and concrete mixed-scalar types
must round-trip without inference.

## Decision

PyArrow is a core dependency and every tabular response follows this path:

```text
HTTP → Pydantic models → logical schema → canonical Arrow table
                                           ├── pandas DataFrame
                                           ├── Polars DataFrame
                                           └── versioned Parquet
```

The existing logical schema remains the authoritative table contract. It maps
recursively to Arrow `int64`, `float64`, `bool`, UTF-8 string, microsecond UTC
timestamp, `struct`, and compliant variable-length `list` types with declared
field and element nullability. The Arrow schema is explicit even when there
are no rows or every nullable value is null.

pandas continues to expose its explicit scalar and nullable dtypes with Python
mappings and lists in nested `object` columns. Polars consumes the same Arrow
table and exposes native `Struct` and `List` columns. pandas `ArrowDtype` is not
the public contract because its nested support remains experimental. Selecting
a backend changes presentation, not the canonical values or storage schema.

The heterogeneous `str | int | float` Stats scalar uses this storage-only
encoding:

```text
struct<
  kind: string not null,
  string_value: string,
  integer_value: binary,
  float_value: double
> not null
```

Exactly one value slot is populated and it must match `kind`. Adapters decode
the struct back to the original Python scalar, preserving `1`, `1.0`, and
`"1"` distinctly. The integer slot uses the minimal signed big-endian two's
complement representation, preserving arbitrary Python integers and rejecting
non-canonical byte sequences during validation.

The internal local-file codec writes Parquet format 1.0 with Snappy
compression, statistics, compliant nested-list encoding, and the stored Arrow
schema. It writes a temporary file in the destination directory and atomically
replaces the target only after a successful close. Parent-directory creation,
partitioning, remote filesystems, cache policy, and public save/load methods are
outside this decision.

Every canonical table carries:

- `cfb_data.storage_version`
- the module-qualified row-model identity
- a SHA-256 digest of the ordered recursive logical schema and scalar encoding
- the informational writer package version

Readers require a supported storage version, the expected row model and
logical digest, and an exact physical Arrow schema. Package-version differences
alone do not invalidate a compatible file. Unknown or incompatible contracts
fail explicitly.

Full reads decode rows, validate them through the current Pydantic list adapter,
and rebuild the canonical table. An explicit internal `trusted_schema` mode may
skip Pydantic domain validation only for integrity-controlled library caches;
it still verifies metadata, physical types, field order, nullability, and the
tagged-scalar invariant. Full validation is always the default.

## Consequences

- pandas, Polars, Parquet, and future caches exercise one recursive schema.
- Empty and all-null nested data retain the same storage types as populated
  responses.
- Backend-native Parquet methods are not the cfb-data compatibility contract;
  a future public API will wrap the internal codec.
- Files remain loadable across package versions while their storage version,
  row-model identity, logical digest, and physical schema remain supported.
- Cached files cannot bypass Pydantic constraints by default.
- Endpoint data remains nested and source-faithful. Future datasets and ML
  feature builders must flatten or explode explicitly at a declared row grain.
- PyArrow's installation and conversion cost becomes part of every base
  installation in exchange for eliminating divergent persistence paths.
