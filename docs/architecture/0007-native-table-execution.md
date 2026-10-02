# ADR 0007: Execute recipes as native partitioned tables

- Status: Accepted; implemented on the testing branch
- Date: October 2, 2026
- Replaces: ADR 0006's whole-list transform execution contract

## Decision

The analytical step contract is `Table` in and `Table` out. A table carries a
typed native dataframe graph and deferred global contract checks. Its public
`frame` exposes the existing Narwhals dataframe interface; Dask execution
lowers that interface to native Dask DataFrame operations over pandas
partitions. Small structural/domain partition kernels remain explicit. The
engine supplies reusable joins, key checks, grouping, ordered nested records,
explosion, projection, concatenation, and coverage/context checks. Recipes
compose these operations instead of implementing Python collection engines.

External HTTP responses still validate through their endpoint Pydantic models
in the coordinator. That bounded boundary immediately persists canonical
parts and exposes table references downstream. Model lists do not circulate
between native analytical steps. Scalar control steps can select a bounded
validated row or derive a scalar without turning the whole table into models.

Dask's lazy collection graph owns partition scheduling, shuffles, grouping,
and joins. The recipe coordinator still owns HTTP resources, caching, attempts,
lineage, semantic revisions, failure policy, and authoritative publication.
Checks reduce to bounded diagnostics; invalid data cannot publish a successful
artifact. Schema metadata comes from the declared contracts, including empty
and nullable results, rather than executing a transform for inference.

Partitions validate and encode at the artifact boundary. The coordinator
writes bounded parts and atomically publishes their canonical manifest only
after global quality checks pass. It does not gather a complete model list.
Checkpoint replay and `ArtifactRef.scan()` read validated parts lazily;
`ArtifactRef.batches()` provides bounded pandas batches. Standalone Parquet
export writes validated parts through one owned writer.

Direct calls retain an explicit eager convenience boundary. Durable runs can
choose lazy table results without eager collection; workflow outputs remain
explicitly named. Source relationships, IDs, nulls, uncertainty, and ordinals
are retained. Beta interfaces and physical schemas may change, with documented
contracts, revisions, and explicit rejection of incompatible artifacts.

## Acceptance

Current evidence and measurement limits are recorded in
[migration verification](native-table-verification.md).

All first-party runtime table transforms use this engine. The original audit
is the migration inventory. Tests exercise real multipartition computation,
cross-partition duplicates and conflicts, join coverage, nested ordering,
empty/all-null results, cancellation, atomic publication, and checkpoint
recovery. Benchmark fixtures compare the old list processing, local tables,
and native distributed execution at small, large, and skewed volumes. Timing,
memory, transfer, and partition evidence must support performance claims.

Live verification uses the repository Redis response cache and cumulative
attempt ledger. Cached replays spend no API attempts. No runtime resources or
credentials are stored in the durable dataframe graph or manifest.
