# ADR 0006: Add durable analytical datasets and local workflows

- Status: Accepted
- Date: 2026-08-18
- Applies from: Analytics dataset and workflow implementation

## Context

The endpoint client deliberately returns source-shaped validated responses. That
boundary is reliable, but analysts repeatedly need a second layer that declares
row grain, composes several sources, normalizes nested records, applies explicit
cleaning policy, and preserves enough evidence to resume work after a failure.
Doing this independently in notebooks makes joins, null handling, output schema,
and API cost difficult to review or reproduce.

The response cache cannot serve as workflow persistence. It owns exact HTTP
responses, freshness, stale fallback, and identity facts, and it may expire or
evict response records. Analytical checkpoints instead need immutable content,
lineage, contract validation, and explicit retention. ADR 0004 already reserves
that separate persistence boundary.

The package also needs a stable handoff for later modeling and visualization
without importing PyTorch or a plotting stack now. That handoff must describe
validated data rather than arbitrary Python objects.

## Decision

### Layer and public experience

`CFBDClient` exposes `datasets` and `workflows` resources with the same inferred
pandas or Polars frame type as endpoint resources. Curated methods return eager
frames. Advanced `plan()` and `run()` methods expose execution cost, run IDs,
quality and coverage evidence, immutable artifact references, and checkpoint
reuse. Planning validates the complete definition without opening the artifact
store or performing HTTP.

Analytics configuration and persistence are lazy. Endpoint-only client use does
not create analytics files. The default artifact root follows the operating
system's user-data convention and an explicit `path` is supported for projects,
tests, and isolated notebook environments.

### Contracts and registered sources

An immutable `TableContract` is authoritative for every persisted table. It
binds a stable namespaced identity and semantic revision to an ordered Pydantic
row model, grain, candidate keys, deterministic ordering, physical partitions,
optional event time, and semantic column metadata. Candidate keys and table
ordering are validated before presentation.

Analytics sources reference registered operation IDs, never arbitrary paths.
Each operation owns its route, request model, response adapter, source row model,
contract revision, access metadata, and documented response limit. The endpoint
resource methods used by the initial catalog consume these same descriptors, so
the normal and analytical paths cannot drift in request or response contracts.

Definitions are immutable finite graphs of registered source and transform
nodes. The compiler rejects invalid parameters, duplicate IDs, unknown inputs or
operations, cycles, incompatible revisions, unsupported backends, excessive
expansion, and execution plans above the attempt budget before I/O.

### Transformation and backend parity

Arrow remains the canonical analytical table. Final rows are validated through
the declared Pydantic row model before a pandas or Polars adapter runs. Narwhals
stable v2 is the core portability layer for its supported flat-table subset.
Library-owned logical-record operations handle nested-path extraction, collision-
failing struct flattening, explicit list explosion, cardinality-checked joins,
deduplication, sentinel policy, text normalization, and finite-number checks.

Parity means the same canonical schema, logical values, nulls, column order, row
order, nested values, quality outcomes, and errors. It does not require identical
native backend dtypes. Only built-in portable transforms and explicitly
registered backend implementations make a parity promise. Backend-specific
custom work includes the backend in its checkpoint identity.

No operation silently drops a row, converts missing data to zero, chooses an
identity, permits an undeclared many-to-many join, or infers a populated output
schema.

### Artifact and run persistence

Analytics persistence is a third component, independent from the response cache
and identity catalog:

- SQLite transactionally stores immutable run state, successful node bindings,
  child-run lineage, cross-process leases, and retention pins.
- The filesystem stores immutable content-addressed objects.
- Table objects contain an ordered manifest and deterministic canonical Parquet
  parts. Partition fields must lead the declared ordering, so concatenating part
  order preserves table order.
- A bounded canonical JSON codec stores explicitly modeled control values.
- Pickle and arbitrary Python-object artifacts are not supported.

An artifact descriptor records codec and media identities, content and part
digests, byte and row counts, table contract and schema fingerprints, grain,
keys, ordering, partitions, semantic columns, producer and upstream digests,
source and validation timestamps, coverage and quality outcomes, and bounded
dependency-version evidence.

Writers stage into a sibling directory, validate and close every file, compute
digests, flush files and directories, atomically publish the immutable object,
and commit the successful node in SQLite last. A crash may leave reclaimable
staging data, but it cannot create a successful database node that points to a
knowingly incomplete object. Loads verify every part, schema, digest, row count,
and Pydantic contract and fail closed on corruption.

### Checkpoints, recovery, and freshness

Every validated node is checkpointed by default. Node compatibility is a Merkle-
style fingerprint of engine version, registered operation and revision,
normalized parameters and node policy, ordered upstream content digests, output
contract and codec, and backend only when required. It deliberately excludes the
whole workflow definition, so a downstream edit preserves compatible ancestors.

A failed or cancelled node never publishes a successful artifact. Recovery
creates an immutable child run. The default simple path selects the newest
compatible failed run and preserves its validated source snapshot; an explicit
`resume_from` is available on advanced dataset and workflow runs. A genuinely
new run executes source nodes through normal response-cache freshness. Source
checkpoints are not general cross-run memoization and cannot freeze old API data.

Process-local single flight and SQLite leases coordinate transform computation.
Redis refresh leases remain response-cache coordination and are not reused as
workflow locks. Artifacts have no TTL or silent eviction. Public inspection,
pinning, export, dry-run prune, explicit prune, and orphan cleanup operations own
retention.

### Scheduling, budgets, and observation

The embedded executor schedules ready graph layers deterministically, performs
independent retrievals with one run-wide bounded concurrency control,
deduplicates exact source requests across child datasets, keeps synchronous
compute and artifact I/O off the event loop, cancels and awaits siblings on
failure, and durably records every terminal run. The default limit is 100 actual HTTP attempts including retries;
the transport reserves each attempt immediately before dispatch and cache hits
consume zero.

Analytics has a separate immutable event family for run, step, artifact, and
contract transitions plus a bounded process-local `AnalyticsStats` collector.
Context-local run and step IDs correlate endpoint retrieval events. Observers are
ordered, synchronous, redacted, and failure-isolated. Events and run errors do
not retain selectors, rows, paths, credentials, bodies, exception messages, or
exception objects.

### Extensions and future layers

Trusted Python definitions and transforms are the authoritative extension
surface. Registries are explicit, immutable, and scoped to a client; there is no
mutable global registry or plugin discovery. A custom transform declares a
stable ID, mandatory implementation revision, deterministic status, backend,
and output contract. It receives validated frames or records and parameters, not
a client or network handle.

The optional YAML extra parses one UTF-8 document into the same frozen graph
contracts. The project loader rejects duplicate and non-string keys, aliases,
anchors, merge keys, explicit tags, multiple documents, non-finite or non-JSON
values, oversized/deep/node-heavy inputs, arbitrary imports, expressions,
templates, environment interpolation, and executable constructs. Strict
Pydantic models forbid unknown fields. YAML references registered sources and
transforms only and never infers output schemas.

The artifact descriptor and table contract are the integration seam for future
modeling and visualization. They already provide stable schemas, ordering,
partitions, semantic metadata, lineage, and availability evidence. PyTorch,
plotting libraries, feature/target roles, split policy, GPU scheduling, and model
or figure codecs are not added by this decision. Future codecs must be explicit,
versioned, validating, and safe; generic pickle remains excluded.

## Initial catalog

The first catalog contains `game_summaries`, `team_games`,
`player_game_stats`, `drives`, `plays`, `rosters`, `team_seasons`,
`player_seasons`, `poll_rankings`, `betting_lines`, `recruiting_classes`, and
`coach_seasons`. The first workflows are `team_season_analysis`,
`single_game_analysis`, and `program_history`; every workflow exposes named
outputs and records its child dataset runs.

`play_player_stats` remains separate from `plays` because `/plays/stats` has a
different athlete/stat-association grain and documented cap. Broad automatic
per-athlete, per-coach, per-game win-probability, and play-stat fan-out are not
part of this decision.

## Consequences

- Analysts get a short curated path and experts use the same engine with explicit
  policy, plans, lineage, and retention controls.
- pandas and Polars share validated logical behavior while remaining native eager
  frames at the public boundary.
- Failed downstream work can be corrected without repeating compatible source
  retrievals.
- Persistence has more operational responsibility than a cache: users must
  inspect and explicitly prune it when retention is no longer needed.
- Local execution is intentionally not a distributed orchestrator. There is no
  daemon, remote worker, queue, cron service, or external side-effect node.

## Alternatives considered

### Extend the Redis or SQLite response cache with checkpoints

Rejected. Cache freshness, credential scoping, TTLs, fail-open behavior, and
eviction are incompatible with durable analytical lineage and fail-closed
artifact validation.

### Make DataFrames the stored contract

Rejected. Backend-specific dtypes and nested behavior would make pandas/Polars
parity, durable compatibility, and later batch readers unstable. Arrow and
validated row contracts remain canonical.

### Hash notebook source to infer custom implementation identity

Rejected. Source inspection cannot reliably capture closures, globals,
dependencies, or notebook state. The extension author owns an explicit semantic
implementation revision.

### Support arbitrary YAML or automatic plugin discovery

Rejected. Imports, evaluation, templating, and mutable global registries make
definitions non-deterministic and turn a data document into an execution or
code-loading boundary.

### Add placeholder modeling and visualization APIs now

Rejected. Their durable integration needs are satisfied by typed artifacts and
table contracts; speculative namespaces would freeze the wrong feature, split,
model, and rendering semantics.
