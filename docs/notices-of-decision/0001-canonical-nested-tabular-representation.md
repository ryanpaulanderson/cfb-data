# NOD 0001: Standardize nested tabular responses on Arrow and Parquet

- Status: Decided
- Date: 2026-08-13
- Decision: Preserve nested endpoint data and use canonical Arrow tables with
  versioned Parquet for library-owned persistence.
- Technical record:
  [ADR 0003](../architecture/0003-canonical-arrow-parquet.md)

## Question presented

How should cfb-data represent nested response values consistently when pandas
stores them as Python mappings and lists in `object` columns while Polars uses
native `Struct` and `List` columns, especially once the library needs reliable
Parquet persistence, caching, analytics, and machine-learning inputs?

The immediate behavior was acceptable for interactive endpoint use, but it did
not define which backend owned the durable schema. Allowing each DataFrame to
write itself would make persistence depend on backend inference, populated
values, and optional dependencies. Flattening at the endpoint boundary would
avoid nested storage but would also change row grain and discard the original
shape before downstream consumers had chosen an analytical question.

## Constraints agreed before choosing

The decision had to satisfy these constraints:

- Preserve existing public endpoint columns, row order, logical values, and
  pandas and Polars dtypes.
- Preserve nested source fidelity without automatic flattening or exploding.
- Retain an explicit schema for zero-row responses, all-null nested columns,
  empty lists, nullable structs, and nested lists of structs.
- Preserve the concrete type of the Stats `str | int | float` value, including
  the distinction between `1`, `1.0`, and `"1"`, while continuing to reject
  booleans.
- Give future library caches one portable, versioned persistence contract
  independent of the selected DataFrame backend.
- Keep Pydantic validation authoritative at untrusted file boundaries.
- Leave dataset row-grain decisions and model-ready feature construction to
  explicit future dataset and feature layers.
- Avoid committing to public cache configuration, save/load methods, remote
  filesystems, partitioning, or eviction before those product requirements
  exist.

## Evaluation criteria

The alternatives were compared on:

1. **Source fidelity:** Can nested values and scalar types round-trip exactly?
2. **Backend neutrality:** Can pandas and Polars consume the same declared
   table without becoming the persistence authority?
3. **Schema determinism:** Does the representation retain field order, types,
   and recursive nullability when data is empty or all null?
4. **Persistence fitness:** Does it map naturally to a portable, interoperable
   file format suitable for future caches?
5. **Validation:** Can files be checked against the expected row model and
   current domain rules before presentation?
6. **Public compatibility:** Can the change leave current endpoint return
   types, values, and dtypes intact?
7. **Extension path:** Can later datasets and ML features choose their own row
   grain without undoing an irreversible endpoint transformation?
8. **Complexity and cost:** Is the additional dependency and codec complexity
   justified by removing divergent schema and persistence paths?

## Alternatives considered

### Keep backend-native frames as the only contract

This was the lowest-effort option, but it did not meet the persistence or
determinism criteria. pandas must infer nested Parquet types from `object`
values and cannot infer a populated nested type from an empty column. Polars
has native nested columns but cannot portably persist the Python `Object` Stats
scalar. Files written by the two backends would therefore not constitute one
cfb-data compatibility contract.

### Flatten or explode nested values automatically

This would simplify some analyses and storage operations, but there is no
single correct flat row grain for every endpoint. Exploding lists can multiply
rows, require parent-key repetition, and create ambiguous behavior when more
than one list is present. Automatic flattening would make an analytical choice
at the source boundary and make the original response harder to reconstruct.
The project instead reserved these transformations for declared datasets and
feature definitions.

### Encode nested values as JSON strings

JSON text would be writable by both backends, but it would erase typed child
fields, recursive nullability, and predicate-friendly Parquet structure. Every
consumer would need to parse and validate the values again. It also would not
solve the need for a deterministic physical schema.

### Make pandas `ArrowDtype` the public representation

This would bring pandas presentation closer to Arrow storage, but it would
change established public pandas dtypes and nested Python values. pandas still
documents `ArrowDtype` as experimental, so making it the public compatibility
surface would place cfb-data's contract on a less stable API than necessary.
Arrow can be canonical internally without imposing that presentation choice on
users.

### Normalize nested sections into multiple related tables

Relational child tables are appropriate for some curated datasets, feature
stores, and warehouse layouts. They are not a universal endpoint return shape:
they require generated keys, ownership rules, and a selected analytical grain,
and often return multiple artifacts instead of one table. The option remains
available above the endpoint layer rather than becoming the source contract.

### Use Arrow as the canonical table and Parquet as its versioned file form

Arrow directly represents ordered structs, typed variable-length lists,
nullability, scalar primitives, and UTC timestamps. Both DataFrame libraries
interoperate with it, and its schema maps directly into Parquet. It therefore
met the fidelity, neutrality, determinism, persistence, and extension criteria
while adapters could continue restoring the existing backend-native public
representations.

The accepted tradeoff was making PyArrow a core dependency and owning a small,
strict codec. That cost was considered preferable to maintaining separate
pandas and Polars persistence behavior or allowing data-dependent inference.

## How the decision was reached

The discussion followed this sequence:

1. **Identify the mismatch.** Existing validated Pydantic models produced the
   same logical nested values, but pandas and Polars represented them
   differently. This established that a DataFrame backend could be a
   presentation layer, but neither should implicitly define storage.
2. **Work backward from credible future uses.** Parquet caches, analytical
   workflows, and ML features all need stable types, yet model-ready flat data
   needs a use-case-specific row grain. This separated source fidelity from
   later feature engineering.
3. **Define invariants before selecting technology.** Field order, recursive
   nullability, typed empties, UTC normalization, mixed-scalar identity, strict
   validation, and unchanged public frames became acceptance criteria.
4. **Evaluate representations against the edge cases.** Backend-native writes,
   automatic flattening, JSON text, public pandas Arrow dtypes, and relational
   normalization each failed at least one core invariant or forced a premature
   public design choice.
5. **Select one internal authority.** Arrow was chosen as the canonical table
   because it expresses the logical schema directly and feeds both DataFrame
   adapters and Parquet without asking either backend to infer storage types.
6. **Define the exceptional mixed scalar explicitly.** Because Parquet has no
   suitable portable heterogeneous primitive for this contract, the Stats
   scalar received a tagged struct with exactly one populated typed value slot.
7. **Bound persistence compatibility.** The file contract was versioned and
   tied to the row-model identity, deterministic logical-schema fingerprint,
   and exact physical Arrow schema. Package version remains informational.
8. **Choose safety defaults.** Local writes use atomic replacement. Reads use
   full Pydantic validation by default; `trusted_schema` remains an internal,
   opt-in optimization for integrity-controlled caches.
9. **Limit the scope.** The decision deliberately excluded public save/load
   APIs, cache policy, remote storage, datasets, automatic flattening, and ML
   feature generation so those concerns can be decided from concrete use cases.

## Evidence used to confirm the decision

The implementation was accepted only after demonstrating:

- model-to-Arrow-to-Parquet-to-Arrow-to-model round trips for scalars, UTC
  timestamps, nullable structs, lists, nullable list elements, lists of
  structs, empty lists, all-null nested columns, and zero-row tables;
- identical declared nested schemas for populated and empty files;
- exact tagged-scalar preservation and rejection of malformed tags and
  booleans;
- materialization of the same Arrow table into established pandas dtypes and
  Python nested values and Polars native `Struct` and `List` values;
- strict rejection of incompatible metadata, row models, schema fingerprints,
  field order, physical types, truncated files, and domain-invalid values;
- atomic replacement and cleanup after write and replacement failures;
- continued loading of a checked-in Parquet v1 compatibility fixture; and
- unchanged behavior across every public API endpoint using the canonical
  Arrow-to-pandas presentation path, with deterministic cross-backend tests for
  pandas and Polars.

## Outcome and follow-up boundaries

The resulting pipeline is:

```text
HTTP → Pydantic models → logical schema → canonical Arrow table
                                           ├── pandas DataFrame
                                           ├── Polars DataFrame
                                           └── versioned Parquet
```

Direct pandas and Polars Parquet methods are not the cfb-data persistence
contract. A future public persistence or cache API must wrap the library-owned
codec or introduce a new decision that supersedes this notice.

Nested endpoint results remain source-faithful. Future analytical datasets and
ML feature layers may flatten, explode, normalize, or aggregate them, but must
do so explicitly at a documented row grain and validate their resulting row
models.
