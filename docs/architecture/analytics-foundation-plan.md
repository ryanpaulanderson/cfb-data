# Modular analytics foundation implementation plan

- Architecture: [ADR 0006](0006-modular-analytics-recipes.md)
- Plan status: Approved
- Implementation status: In progress
- Last updated: 2026-08-19

## Goal

Build the reusable bones of an embedded college-football analytics platform:
callable recipe authoring, automatic discovery, static planning, async source
coordination, portable transformation tools, Dask compute, durable recovery,
and end-to-end observation. Package twelve datasets and three workflows as
independent modules authored through exactly that public surface.

The implementation is complete only when all offered options have runtime
parity:

| Options | Required parity |
| --- | --- |
| pandas / Polars | Canonical schema, logical values, nulls, nesting, row and column order, quality outcomes, and errors. |
| local / Dask | Compilation, sources, fingerprints, validation, artifacts, recovery, lineage, event meanings, and logical outputs. |
| Python / YAML | Canonical graph, fingerprint, planning, execution, persistence, and errors for equivalent finite definitions. |
| first-party / user | Authoring, automatic discovery, composition, planning, execution, persistence, observation, and documentation-level features. |

Performance, task placement, native DataFrame dtypes, timing, and concurrent
event interleaving may differ where their meaning is not part of the analytical
contract.

This is not a general distributed orchestrator. This foundation has no daemon,
deployment system, cron service, remote queue, multi-host workers, remote
artifact store, arbitrary side-effect nodes, PyTorch layer, or visualization
renderer.

## Public authoring contract

### Recipe definitions

The core public authoring surface is:

- ``@source`` for coordinator-owned async I/O with declared output, freshness,
  access, limit, and cost evidence.
- ``@step`` for pure synchronous or explicitly async transformation code.
- ``@dataset`` for one validated tabular output with declared semantics.
- ``@workflow`` for ordered named-output composition.

Authors declare semantics beside the recipe rather than constructing public
definition or contract objects:

```python
from collections.abc import Mapping

from pydantic import BaseModel, Field

from cfb_data.analytics import (
    RecipeRef,
    SourceContext,
    dataset,
    source,
    step,
    workflow,
)


class GameSummary(BaseModel):
    game_id: int = Field(description="CFBD game identifier")
    season: int
    week: int
    result_state: str


@source(operation=GAMES_LIST)
async def games(
    context: SourceContext[Game],
    *,
    year: int,
    team: str | None = None,
) -> list[Game]:
    return await context.retrieve(year=year, team=team)


@step(
    id="example.normalize_games",
    revision=1,
    output=GameSummary,
    deterministic=True,
)
def normalize_games(rows: list[Game]) -> list[GameSummary]:
    ...


@dataset(
    id="example.game_summaries",
    revision=1,
    row=GameSummary,
    grain="one selected game",
    keys=("game_id",),
    order_by=("season", "week", "game_id"),
    partition_by=("season",),
)
def game_summaries(
    year: int,
    team: str | None = None,
) -> RecipeRef[list[GameSummary]]:
    return normalize_games(games(year=year, team=team))


@workflow(id="example.season_analysis", revision=1)
def season_analysis(
    year: int,
    team: str,
) -> Mapping[str, RecipeRef[object]]:
    games_output = game_summaries(year=year, team=team)
    return {"game_summaries": games_output}
```

Dataset and workflow builder functions are synchronous and contain analytical
parameters only. The recipe wrapper exposes two typed call modes:

- At the top level, ``await recipe(client, **parameters)`` executes and returns
  the selected eager backend value.
- While the engine is building another recipe, ``recipe(**parameters)`` returns
  a typed graph reference and performs no source or transform work.

``GAMES_LIST`` is an endpoint-owned descriptor. Binding it in the decorator
derives the source ID, revision, output validation, access tier, limits, and
cost before the async body can run; duplicate overrides are rejected.
``SourceContext[RowT]`` is a consumed-only public protocol injected only while
a compiled source executes. ``RecipeRef[OutputT]`` is a covariant public
protocol that authors annotate but never instantiate. Steps, datasets, and
workflows never receive a client or network handle. A source is a leaf and
cannot call another recipe while executing.

First-party recipe modules import reusable public endpoint source callables,
not private descriptors. A trusted fully custom source uses the explicit
``@source`` form with one namespaced ID, one semantic revision, output
validation, bounded cost, and freshness semantics. Endpoint-backed sources
cannot redeclare descriptor-owned metadata.

The wrapper preserves an inspectable signature containing the explicit client
and original analytical parameters. Strict Pydantic validation preserves
defaults and distinguishes omitted, null, false, and zero values in canonical
fingerprints. Non-finite configuration values are rejected.

### Composition

Recipes compose through direct calls inside a builder:

```python
@workflow(id="example.program", revision=1)
def program(year: int, team: str) -> Mapping[str, RecipeRef[object]]:
    games = game_summaries(year=year, team=team)
    season = team_seasons(year=year, team=team)
    return {"games": games, "team_seasons": season}
```

The complete composition matrix is:

- Dataset to dataset: supported.
- Workflow to dataset: supported.
- Workflow to workflow: supported.
- Dataset to one explicit named workflow output: supported.
- Source or step to a recipe at execution time: prohibited.

Repeated child invocation requires a stable alias:

```python
home = game_summaries.as_("home")(year=year, team=home_team)
away = game_summaries.as_("away")(year=year, team=away_team)
```

Nested identity is the parent invocation path plus child stable identity and
alias. Call order is not identity. Workflow outputs are selected by exact name,
for example ``child_workflow(...)["plays"]``. A parent explicitly re-exports
the outputs it wants; there is no implicit flattening.

Dataset selection of one workflow output narrowly amends ADR 0001's default
workflow-above-dataset ordering. Compilation slices the child workflow to that
output's transitive dependency closure first. Unselected outputs are not
compiled, budgeted, fingerprinted, executed, or checkpointed; the dataset
cannot consume the workflow mapping or depend on workflow side effects. The
selected output keeps its ordinary recipe/artifact identity in the parent
namespace. A generally reusable analytical product should still be extracted
as a dataset.

Graph shape may depend on validated plan-time parameters only. Source rows and
DataFrame contents cannot create new graph nodes. A fixed source node may bind
request values from a validated scalar output of an already-declared upstream
node; its node count and worst-case request cost remain static, while inspection
reports its exact cache disposition as deferred. Trusted Python may use one
engine-owned bounded map/gather primitive over a validated plan-parameter
sequence with stable unique keys. It expands completely during compilation;
source-derived keys are prohibited. Every use declares a local expansion limit
and remains subject to the run-wide limit. YAML remains a finite
static graph.

### Direct and advanced execution

```python
frame = await game_summaries(client, year=2024, team="Penn State")

plan = await game_summaries.plan(
    client,
    year=2024,
    team="Penn State",
)

inspection = await game_summaries.inspect(
    client,
    year=2024,
    team="Penn State",
    plan=plan,
)

run = await game_summaries.run(
    client,
    year=2024,
    team="Penn State",
    policy=ExecutionPolicy(executor="dask"),
)

frame = run.value
run.artifact.export_parquet(destination)
```

``RecipePlan`` is immutable, pure, and state-independent. It contains safe
definition identity, compiled nodes and dependencies, source request shapes,
deduplication, node placement, declared access/completeness requirements,
worst-case cold attempt reservations, and compile diagnostics. It reads no
cache, checkpoint database, filesystem, environment, or Dask state and contains
no raw selectors, credentials, cache keys, paths, rows, or exceptions.

``await recipe.inspect(client, **parameters, plan=plan)`` revalidates the
parameters and requires their canonical fingerprint to match the optional
plan. It returns an immutable ``RecipeInspection`` with read-only response-cache
and checkpoint dispositions and a refined execution preflight. The redacted
plan does not retain selectors or cache keys. Inspection performs no HTTP
request, transform execution, artifact write, or store creation. ``run()``
performs the same inspection internally before it creates run state.

``RecipeRun[OutputT]`` contains run and parent IDs, the typed value, named
artifacts, source coverage, quality outcomes, lineage, placement, and reuse
statistics. ``ArtifactRef`` validates loading and explicit export without
exposing the internal object-store path and remains usable after the HTTP
client closes.

The minimal public analytics types are:

- Decorator-produced callable recipe protocols and graph references.
- ``SourceContext[RowT]`` and ``RecipeRef[OutputT]`` consumed-only protocols.
- ``AnalyticsConfig`` and ``ExecutionPolicy``.
- ``RecipePlan``, ``RecipeInspection``, ``RecipeRun[OutputT]``, and
  ``WorkflowOutputs[FrameT]``.
- The opaque immutable ``RecipeSnapshot`` and ``discover_recipes(...)``.
- ``ArtifactRef`` and safe artifact descriptors.
- Analytics event, observer, and bounded statistics types.
- ``CFBDRunError`` and specific configuration, discovery, compilation,
  contract, artifact, and optional-dependency errors.

Authors do not construct or subclass public catalog, definition, graph-node,
provider, source-specification, or table-contract types. There is no
``client.datasets``, ``client.workflows``, ``DatasetCatalog``, ``_catalog.py``,
or generic raw-path source API.

``CFBDRunError`` is chained from the original cause and exposes only safe run
ID, failed node ID, and failure category. Exception messages and objects are not
persisted or emitted.

## Automatic discovery and package boundaries

### Transactional discovery

Decorators create immutable module-scope recipe objects and invoke a private
runtime-owned automatic-registration hook. A directly imported object is
immediately callable. The private candidate index is discovery bookkeeping,
not a mutable execution catalog. Stable-ID resolution uses an opaque immutable
``RecipeSnapshot`` returned by ``discover_recipes(...)``.

Registration and snapshot creation share one process-wide reentrant lock.
Ordinary-import candidates enter a snapshot only after their defining module
finishes initialization and the object remains bound at its declared qualified
name. Failed or still-initializing imports are excluded, and discovery never
walks ``sys.modules`` looking for recipes.

Each provider entry point targets one ordinary package root owned by one
distribution. Namespace packages and roots with multiple locations are
rejected. Provider identities are the normalized distribution name,
entry-point name, and target module, optionally constrained by distribution
version. Entry-point name alone is never recipe identity.

Selected providers and at most 1,000 modules within each package are ordered
deterministically and imported lexically while the discovery lock and a
context-local staging transaction are active. Registrations from the claimed
provider root enter only that transaction; already loaded provider modules are
explicitly restaged there. Candidates are validated, deduplicated, and
conflict-checked before one snapshot is published.

Import failure, recursion, invalid metadata, or identity collision discards the
complete provider stage. Modules left in ``sys.modules`` remain quarantined
from ordinary registration and future snapshots until a new transaction
successfully restages and commits the whole provider. Concurrent snapshot and
provider discovery cannot observe a partial transaction.

Registry keys are exact ``(kind, namespaced ID, revision)`` tuples. There is no
implicit latest version. Re-exports of the same object are deduplicated. A
module reload is idempotent only when its origin, normalized declaration, and
diagnostic source digest are unchanged; otherwise the author increments the
revision. The source digest guards reloads and diagnostics but is never durable
compatibility identity.

An unversioned notebook recipe remains directly callable and composable. It is
not addressable from YAML or the stable snapshot and cannot reuse work across
runs. It may reuse already committed nodes only while recovering its originating
run.

``AnalyticsConfig`` can disable installed providers or allow-list exact
provider identities. YAML's explicit handoff is
``load_recipe_yaml(text, recipes=discover_recipes(config))``. It receives that
already frozen snapshot and never starts discovery, imports a package, resolves
a dotted path, or loads code. The snapshot is reusable but not mutable or a
user-maintained definition index.

### First-party package

The same wheel will contain a separate top-level ``cfb_data_recipes`` package.
Its ``__init__.py`` contains documentation only—no recipe imports or index.
One official ``cfb_data.recipes`` entry point targets that package root. Core
``cfb_data.analytics`` must not import it.

Each official recipe is a self-contained module directly under that root. It
uses only the same public authoring, source, step, composition, discovery,
and execution interfaces available to an external provider. Tests install a
small external provider distribution and compare its behavior with the
official provider to prevent a privileged path.

Reusable endpoint sources live with the endpoint domains that own their
request/response contracts and are exposed through narrow analytics source
callables. Existing endpoint methods and source callables share the same typed
operation descriptor. No analytics module duplicates routes, request models,
response adapters, limits, or access-tier facts.

``@source(operation=...)`` binds that descriptor into the graph and derives
source identity, revision, request/response validation, access tier, limits,
and cost. The compiler can inspect it without executing the source body and
rejects any duplicate override. Custom sources use the explicit declaration
form and own one semantic revision themselves.

## Compiler and transformation semantics

### Static compiler

Discovery, compilation, planning, inspection, and execution are separate
phases:

1. Discovery imports explicitly trusted provider code and freezes a snapshot.
2. Compilation validates parameters and executes only pure builder functions
   to construct an immutable graph.
3. Async ``plan()`` derives a deterministic state-independent plan. It reads no
   cache, checkpoint database, filesystem, environment, or Dask state.
4. Explicit ``recipe.inspect(client, **parameters, plan=plan)`` may read
   existing response-cache coverage and analytical checkpoint metadata after
   parameter revalidation. It performs no HTTP request, Dask submission,
   transform execution, artifact write, or default-store creation.
5. Execution repeats the inspection preflight, creates the run, and performs
   the approved work.

Compilation rejects before operational I/O:

- Invalid parameters, identities, revisions, aliases, and output names.
- Duplicate node identities, recursive recipes, cycles, and unknown inputs.
- Data-dependent graph expansion or maps whose keys are not a validated finite
  plan-parameter sequence.
- Schema, grain, key, ordering, partition, backend, or codec incompatibility.
- An unbounded or unknown source cost.
- A source/access/completeness plan that cannot satisfy the requested policy.
- Worst-case HTTP attempts or expanded nodes above hard limits.
- Dask-required placement for a node that is not Dask eligible.

Plans distinguish logical source requests, identical deduplicated requests, and
worst-case cold actual attempts including retries. Inspection adds cache and
checkpoint dispositions without changing the plan. The transport reserves and
records each actual attempt immediately before dispatch; cache hits consume
zero.

### Table and output validation

Every persisted table has a private derived contract containing:

- Stable output ID and semantic revision.
- Ordered Pydantic row adapter and logical Arrow schema digest.
- Declared grain, candidate keys, deterministic ordering, partitions, and
  optional event-time field.
- Nullability plus semantic field descriptions, units, and roles derived from
  Pydantic metadata.
- Cross-row uniqueness, range, completeness, cardinality, and domain checks.

External source data validates through endpoint Pydantic models before a
source artifact exists. Dataset final rows validate through the declared model
and table-level checks before Arrow persistence or pandas/Polars presentation.
Intermediate public unvalidated DataFrames are prohibited.

Analytics tables use a distinct codec/storage v2 whose compatibility identity
is stable output ID, semantic revision, and ordered schema digest. Pydantic
module and qualified name are provenance, not an analytics-v2 compatibility
key. This narrowly amends ADR 0003 for analytics-v2 artifacts. The checked-in
Parquet-v1 format and reader remain unchanged, continue enforcing their
module-qualified model identity, and retain full regression coverage.

### Reusable operation vocabulary

Core operations are generic building blocks, never football-specific dataset
definitions:

- Select, rename, strict cast, and explicit-format parsing.
- Separate null/missing and NaN handling.
- Explicit sentinel replacement, coalescing, and recorded imputation policy.
- Text normalization without implicit identity resolution.
- Structured nested paths using path tokens rather than dot parsing.
- Collision-failing struct flattening.
- Inner/outer single-list explosion with explicit null-list, empty-list,
  element-null, ordinal, and grain-change behavior. Multiple lists require
  explicit zip or Cartesian semantics.
- Filters that record excluded-row counts and null-predicate behavior.
- ID-first joins with declared keys, cardinality, unmatched-row policy,
  collision policy, output ordering, and row-count diagnostics. Undeclared
  many-to-many joins fail.
- Deterministic deduplication with keys and winner ordering; duplicates fail by
  default.
- Concatenation, grouping, aggregation, and pivoting with explicit output
  schema, categories, empty-group rules, and grain.
- Stable sorting and quality assertions for uniqueness, row counts, ranges,
  completeness, and cross-row invariants.

No operation silently drops rows, treats missing as zero, chooses an identity,
performs lossy coercion, or creates an undeclared Cartesian product.

``narwhals>=2.24,<3`` is a core dependency and production imports use only
``narwhals.stable.v2``. It supplies its supported flat-table portability
subset; it is not evidence of parity. Nested operations use canonical Arrow or
logical records. Every operation is tested independently through pandas and
Polars, including null/NaN and inference differences.

Custom steps declare stable ID, revision, determinism, output model/contract,
and supported backend set. Unversioned code is not reusable across runs. A
single-backend user step is allowed, but the unsupported backend fails during
planning and is not advertised as a parity option.

## Execution, Dask, and observability

### Locked defaults

``ExecutionPolicy`` has typed fields with these defaults:

| Policy | Default |
| --- | --- |
| Executor | ``local`` |
| Retrieval concurrency | 4 |
| Local compute concurrency | 1 |
| Hard actual HTTP-attempt budget | 100, including retries |
| Expanded engine-node limit | 10,000 |
| Checkpoint mode | Every validated decorated boundary |
| Completeness | Required/requested sources must be complete |
| Enrichment failures | Fail when requested |
| New-run source behavior | Normal response-cache freshness |
| Recovery source behavior | Preserve exact parent snapshot |
| Dask workers | Up to 4 processes, bounded by CPUs |
| Dask worker threads | 1 |
| Dask task retries | 0 |
| Dask in-flight tasks | 4 |
| Per-task Arrow transfer limit | 512 MiB |
| Runtime fallback after Dask user-code/worker failure | Never |

Experts may lower or explicitly raise finite concurrency, attempt, expansion,
and transfer limits; choose output-only or disabled checkpointing; request
partial output; choose refresh/recompute nodes; enable a finite pure-step Dask
retry count; require every transform to be Dask placed; or permit
coordinator fallback only for a pre-execution cluster-startup or serialization-
capability failure. Fallback and placement are always planned or emitted.

Semantic policies that affect values participate in checkpoint identity.
Operational policies—executor, concurrency, retries, and pre-execution
fallback—are recorded for audit but do not change portable content identity.

### Coordinator execution

The coordinator:

- Runs independent async source nodes under one run-wide semaphore using the
  open client's pooled session, response cache, source single-flight, and
  transport attempt accounting.
- Deduplicates identical validated source requests across nested recipes.
- Schedules ready nodes deterministically while allowing independent retrieval
  overlap.
- Runs synchronous local transforms and artifact I/O off the event loop.
- Cancels and awaits siblings on failure, preserves cancellation, and records
  every terminal run and node state.
- Never publishes a successful artifact for a failed, cancelled, corrupt, or
  incompletely validated node.

Custom source adapters must provide bounded cost and freshness semantics. The
planner prohibits automatic per-player profile, per-coach profile, per-game
win-probability, and broad ``/plays/stats`` fan-out.

### Dask executor

The optional ``dask`` extra installs a supported ``dask[distributed]`` release.
The coordinator targets a topology-neutral executor-provider contract. The
shipped managed-local provider starts an asynchronous temporary
``LocalCluster`` only after checkpoint inspection proves at least one ready
step will run there. A zero-work replay does not start Dask. The coordinator
does not assume scheduler construction, shared worker filesystems, or local
transport; provider sessions own capability negotiation, bounded Arrow
transport, cancellation, and resource closure.

Only pure ``@step`` nodes are eligible. Sources, planning, validation authority,
leases, events, and artifact commits stay in the coordinator. Workers receive
bounded JSON control data and canonical Arrow inputs and return canonical Arrow
plus bounded diagnostics. The coordinator validates through the output model
again before commit.

Static coordinator placement for an ineligible step is not failure fallback
and is visible in the plan. A Dask-selected user-code exception, timeout,
worker loss, or partial execution is never silently rerun locally. Optional
pre-execution fallback emits an explicit event. Dask/cloudpickle may transport
trusted callable code transiently, but no persistent file or loader uses
pickle.

The coordinator owns the Dask client and cluster for one run. On failure or
cancellation it cancels and awaits futures, closes the client and cluster, and
then records terminal state. Coordinator or worker loss before artifact commit
may leave reclaimable staging data but cannot create a successful checkpoint.

This change does not accept an external scheduler address. An adopted-client
or remote provider can implement the same session contract later without
changing recipe, graph, artifact, lineage, recovery, or event contracts.

### Analytics observability

Analytics events are immutable and separate from retrieval events:

- Run planned, started, completed, failed, and cancelled.
- Step ready, placed, started, reused, completed, failed, and cancelled.
- Compile-time expansion and resource wait.
- Checkpoint lookup, reuse, rejection, corruption, and write.
- Contract and quality validation.
- Artifact stage, commit, load, and failure.
- Source budget reservation and consumption.
- Dask cluster lifecycle, retry, and permitted pre-execution fallback.

Context-local run and step IDs correlate source retrieval attempts. Dispatch is
bounded, ordered within each dispatcher, synchronous at the observer boundary,
redacted, and failure-isolated. ``AnalyticsStats`` is bounded, thread-safe, and
process-local.

Plans, events, manifests, and safe errors do not contain raw parameters,
selectors, credentials, cache keys, DataFrame rows, response bodies, internal
paths, exception messages, exception objects, or worker tracebacks.

## Durable artifacts, recovery, and freshness

### Ownership and codecs

Analytics persistence remains independent from the response cache and identity
catalog:

- SQLite owns transactional run, node, lease, lineage, recovery, pin, and
  garbage-collection state.
- The filesystem owns immutable content-addressed objects. Content manifests
  exclude run-specific timestamps, placement, and correlation evidence; those
  belong to SQLite run/node bindings so volatile audit data cannot defeat
  content deduplication.
- The default root is the operating system's application-data directory,
  resolved through ``platformdirs``, and is created only by execution that
  needs to write. ``AnalyticsConfig`` can override it.

Analytics table artifacts use codec/storage v2 with an ordered manifest and one
or more deterministic canonical Parquet parts. The existing endpoint
Parquet-v1 codec remains unchanged and readable. A bounded modeled-JSON codec
uses sorted keys, compact encoding, explicit Pydantic validation, rejected
non-finite values, and a 32-MiB encoded-size default. There is no pickle or
arbitrary Python-object codec.

Unknown future artifact kinds remain inspectable in manifests and fail with a
typed missing-codec error when loaded. Codec registration remains private in
the first release; future modeling and visualization codecs extend that
boundary rather than the scheduler.

### Manifest and commit contract

Every artifact descriptor records:

- Artifact kind, format, codec ID/version, media type, content digest, and
  bytes.
- Stable output identity/revision, ordered schema digest, grain, keys,
  ordering, and partition policy.
- Ordered part names and digests, row count, and safe quality outcomes.
- Producer recipe/node identity and revision plus ordered upstream digests.
- Source operation/request/response-contract fingerprints.
- Source fetched and validated timestamps, materialization timestamp, event
  time, and availability evidence.
- Semantic field descriptions, units, and roles.
- Coverage state: ``not_requested``, ``unavailable_access``, ``empty``,
  ``partial``, ``present``, or ``failed``.
- Safe correlation and relevant dependency versions.

Writes stage in a sibling temporary location, close and validate content,
compute every digest, flush files and directories, atomically publish the
immutable object, and commit successful node state in SQLite last. Missing,
truncated, corrupt, schema-incompatible, row-count-incompatible, or digest-
incompatible objects fail closed. Crashes may leave reclaimable orphans but not
a knowingly incomplete successful manifest.

### Fingerprints and recovery

Per-boundary compatibility keys contain:

- Engine and canonical-IR version.
- The decorated boundary's one authoritative ID and semantic revision.
- Canonical validated parameters and semantic policies.
- Ordered upstream artifact content digests.
- Stable output identity, schema digest, and codec.
- Backend only for a declared backend-specific operation.

An endpoint-backed source derives that revision from its operation descriptor;
a custom source or step owns the revision on its decorator. There is no second
implementation or code revision field.

The complete parent recipe definition and operational executor policy are not
in every node key. Editing one downstream cleaning step invalidates that step
and descendants while preserving compatible ancestors.

Run records are immutable. Recovery creates a child run with ``parent_run_id``.
The simple path may select the newest compatible incomplete run for the same
recipe, parameters, and credential scope and preserve its validated source
snapshot. The advanced path exposes ``resume_from`` and source behavior
``preserve_snapshot``, ``normal_freshness``, or ``refresh``.

A genuinely new run always executes source nodes through current response-
cache freshness. A durable analytical checkpoint cannot become a permanent API
cache. Nondeterministic nodes may reuse committed output only while recovering
their originating snapshot, never as cross-run memoization.

Artifacts have no TTL and are never silently evicted. Inspection, pinning,
explicit export, dry-run prune, prune, and orphan cleanup are supported.
Referenced or pinned artifacts cannot be removed.

## Safe YAML authoring

Python is the authoritative surface for creating new executable steps and
sources. YAML composes the four registered kinds—sources, steps, datasets, and
workflows—plus parameters, literals, and named outputs into the exact same
canonical graph. There is no fifth operation registry: reusable transforms are
versioned ``@step`` objects and endpoint access is a versioned ``@source``.

Every reference includes exact kind, namespaced ID, and revision; there is no
implicit latest. References resolve only through the explicitly supplied
``RecipeSnapshot``. Bindings validate against the same callable signatures and
Pydantic models as Python.

A YAML dataset declares ordered output fields through a bounded versioned
structural schema grammar for supported JSON-compatible scalar, list, and
struct types, including explicit nullability and semantic field metadata. It
cannot name or import a Python model. The loader derives a private Pydantic
adapter and Arrow schema before any rows exist; Python row models and YAML
schemas canonicalize to the same logical representation. Equivalent
Python/YAML fixtures must therefore produce byte-identical canonical graphs and
fingerprints. A completely validated YAML definition becomes an ordinary
recipe object through the same automatic-registration hook.

The optional ``yaml`` extra uses ``PyYAML>=6.0.3,<7``. Calling the loader
without it raises ``CFBDOptionalDependencyError`` with installation guidance.
The project-owned safe loader:

- Accepts one UTF-8 document no larger than 1 MiB.
- Rejects duplicate or non-string mapping keys.
- Rejects anchors, aliases, merge keys, explicit/custom tags, and multiple
  documents.
- Rejects non-finite and non-JSON-compatible values.
- Limits depth to 32, static nodes to 1,000, and expanded nodes to 10,000.
- Uses strict Pydantic models with unknown fields forbidden.
- Produces safe line/column diagnostics without echoing the document.
- Rejects Python paths, imports, dotted lookup, expressions, templates,
  environment interpolation, ``eval``, ``exec``, pickle, shell commands,
  loops, branches, and arbitrary row-driven fan-out.
- Never initiates provider discovery, imports code, or infers an output schema
  from populated rows.

## Initial recipe modules

Every module is versioned even when its transformation is source-faithful.
Changing grain, row universe, null semantics, formula, join policy, or cleaning
policy requires a semantic revision.

Optional enrichments left-join onto the base universe and cannot add or remove
base rows. Coverage distinguishes not requested, unavailable, empty, partial,
present, and failed.

### Datasets

| Module | Grain and key | Required behavior |
| --- | --- | --- |
| ``game_summaries.py`` | One game; ``game_id`` | Normalize ``/games`` while retaining future, incomplete, and completed games. Missing scores never become zero. Result, winner, margin, and total remain null unless status and both scores support them. Media and weather remain explicit enrichments. |
| ``team_games.py`` | One team perspective per game; ``(game_id, team_id)`` | Derive exactly two deterministic base rows from ``game_summaries``. Conventional team stats, advanced box score, havoc, and PPA are enrichments and cannot remove either row. Dynamic statistics remain ordered typed records unless explicitly projected. |
| ``player_game_stats.py`` | One athlete/stat observation; ``(game_id, team_id, athlete_id, category, stat_type)`` | Flatten ``/games/players`` nesting. Preserve source ``stat`` as a string, including compound values such as ``7/9``. Duplicate candidate keys fail. Athlete-game metrics are not repeated onto each stat row. |
| ``drives.py`` | One game-scoped drive; ``(game_id, drive_id)`` | Normalize ``/drives`` with nullable drive number and clock parts. Add only direct clock/score arithmetic and never infer a silent definition of drive success. |
| ``plays.py`` | One game-scoped play; ``(game_id, play_id)`` | Normalize ``/plays`` while preserving nullable source PPA and clocks. Win probability is explicit game-scoped enrichment. ``/plays/stats`` is not merged into this grain. |
| ``rosters.py`` | One athlete/team/season membership; ``(season, source_team, athlete_id)`` | Normalize ``/roster``, preserve nested recruiting IDs, and record temporal identity evidence. Unresolved or ambiguous team identity remains explicit and never drops a row. |
| ``team_seasons.py`` | One team-season; ``(season, team_id)`` | Use ``/records`` to establish the universe. Common and advanced statistics remain typed ordered records or explicit projections. PPA, ratings, talent, returning production, ATS, and paid adjusted metrics are enrichments only. |
| ``player_seasons.py`` | One athlete/team/season; ``(season, team_id, athlete_id)`` | Union roster and season-stat membership so roster-only and stats-only athletes survive. Usage, PPA, success, and adjusted metrics are enrichments. Never auto-fan-out through per-athlete overview calls. |
| ``poll_rankings.py`` | One team/poll snapshot; ``(season, season_type, week, poll, team_id)`` | Flatten ``/rankings`` while preserving source poll/rank order, nullable rank, final-state evidence, votes, and points. |
| ``betting_lines.py`` | One provider quote per game; ``(game_id, provider, source_ordinal)`` | Flatten ``/lines`` and preserve open/current values and nulls. Never relabel a historical value as closing or choose a provider. ATS/total outcomes require an explicit versioned quote-selection recipe. |
| ``recruiting_classes.py`` | One team/class year; ``(class_year, source_team)`` | Compose team rankings and player commitments, union ranked teams with teams having commitments, and account for uncommitted recruits separately. Do not treat ``/recruiting/groups`` as class-year data because its response lacks that grain. |
| ``coach_seasons.py`` | One coach/team/year; ``(coach_id, team_id, year)`` | Use coach-season records directly, preserving ``attribution_complete`` and nullable record/scoring/poll context. Tenure is optional context. Never auto-fan-out through coach profiles. |

``play_player_stats`` is the next direct recipe and remains separate because
``/plays/stats`` is athlete/stat-association grain, one-to-many with plays, and
capped at 2,000 rows. It will be game-partitioned and must prove completeness.
``transfer_events`` is the following independent recipe candidate.

### Workflows

Workflows compose the public dataset callables and expose stable independently
checkpointed named outputs.

``team_season_analysis.py`` returns:

- ``game_summaries``
- ``team_games``
- ``player_game_stats``
- ``rosters``
- ``team_seasons``
- ``player_seasons``
- ``coach_seasons``

Drives, plays, polls, betting, recruiting, and paid metrics are explicit
expansions.

``single_game_analysis.py`` returns:

- ``game_summary``
- ``team_games``
- ``player_game_stats``
- ``drives``
- ``plays``
- ``betting_lines``

Advanced box score, play win probability, future ``play_player_stats``, media,
and paid weather are explicit expansions. Because drives lack a direct game-ID
selector and plays require year/week, planning first validates game context,
requests the smallest complete containing partition, and filters by validated
game ID.

``program_history.py`` returns:

- ``game_summaries``
- ``team_games``
- ``team_seasons``
- ``recruiting_classes``
- ``coach_seasons``
- ``poll_rankings``

It excludes rosters, player-game data, drives, and plays by default and always
shows preflight cost before execution.

Across all modules, name-only teams resolve in game context first and then
through temporal identity evidence. Bare global name joins are prohibited.
Athlete IDs remain canonical strings where source contracts use strings.
Full-season records, ratings, recruiting summaries, and historical betting
quotes are not point-in-time pregame features without explicit availability
evidence.

## Delivery and commit sequence

The approved architecture review authorizes a vertical-slice implementation
while ADR 0006 remains Proposed. The ADR becomes Accepted only after its stated
authoring, discovery, pooled-source, artifact, and local/Dask parity evidence
passes. Each stage is a coherent reviewable change with its own relevant
checks; implementation must not be reassembled into one large commit.

1. **Authoring and discovery**
   - Add decorators, typed wrappers, graph references, transactional discovery,
     entry-point support, composition, and compilation validation.
   - Add packaging tests with a separately built external provider.
   - Suggested commit: ``feat(analytics): add modular recipe authoring``.
2. **Durable coordinator vertical slice**
   - Add source/step graph IR, planning, async coordination, artifacts, SQLite
     run state, recovery, and analytics events.
   - Extract endpoint-owned operation descriptors as each source is introduced.
   - Prove ``team_games`` and ``player_game_stats`` as independent modules.
   - Split authoring, artifact, scheduler, and recipe work into separate
     dependency-ordered commits.
3. **Portable operations and Dask**
   - Add the generic operation vocabulary and Narwhals/Arrow adapters.
   - Add local and Dask transform executors over one worker contract.
   - Establish the full pandas/Polars by local/Dask gate before adding the
     remaining recipe modules.
4. **Remaining dataset modules**
   - Add the other ten recipes in small domain-focused commits, each with its
     semantic documentation and complete parity evidence.
5. **Workflows and safe YAML**
   - Add the three workflow modules through direct recipe calls.
   - Add YAML compilation, direct/advanced APIs, export, recovery inspection,
     retention operations, and copyable notebook-style examples.
6. **Hardening and release evidence**
   - Complete failure injection, packaging matrices, Redis integration, bounded
     live acceptance, README/status documentation, and operational guidance.

After the architecture-only PR is accepted, implementation should proceed in
dependency-ordered PRs so authoring/discovery, durability, Dask parity, recipe
semantics, and public documentation can be reviewed independently.

## Deterministic acceptance

### Authoring, discovery, and compilation

- Decorated signature/default/type preservation and no leaked ``Any``.
- Direct import without registration calls.
- Transactional provider success/failure, concurrent discovery, package-module
  bound, namespace-package rejection, exact allow-list identity, spoofed entry-
  point name, deterministic ordering, and no partial snapshot.
- Provider partial failure followed by a second snapshot, quarantined
  ``sys.modules`` entries, mid-import concurrency, and successful full retry.
- Re-export deduplication, reload idempotence, conflicting same-revision reload,
  collision order independence, no implicit latest, and immutable snapshot
  isolation.
- Unversioned notebook execution/composition plus durable/YAML lookup rejection.
- First-party and separately installed user-provider equivalence.
- Direct call versus ``.run()`` logical equivalence.
- Nested composition, aliases, named outputs, recursion, cycles, unknown output,
  impossible bindings, and bounded expansion.
- Dataset-to-workflow named-output dependency slicing, including proof that
  unselected outputs are not compiled, budgeted, fingerprinted, executed, or
  checkpointed.
- Map/gather expansion only from validated plan-parameter sequences, with exact
  compile-time node and attempt counts and source-derived keys rejected.
- Endpoint-backed source metadata derived only from its bound descriptor, with
  duplicate overrides rejected before the source body executes.
- Planning with exact zero HTTP attempts, cache/checkpoint/filesystem/environment
  reads, Dask submissions, transforms, artifact writes, and default-store
  creation. Inspection is separately proven read-only and state-sensitive;
  parameter/plan fingerprint mismatches fail before store lookup.

### Transformation and recipe correctness

- Empty, all-null, nested, and mixed tagged-scalar tables.
- Null versus NaN, null/empty lists, null elements, collisions, strict casts,
  explicit parsing, filters, imputation, joins, duplicates, aggregation, pivot,
  UTC timestamps, and deterministic ordering.
- Exact final schemas, grains, candidate-key uniqueness, conservative metrics,
  identity ambiguity, coverage states, enrichment isolation, endpoint caps, and
  all twelve recipe-specific invariants.
- Every first-party step, dataset, and workflow runs independently through
  pandas/local, Polars/local, pandas/Dask, and Polars/Dask. Checkpoint reuse is
  disabled so parity cannot mask an implementation.
- Compare canonical tables, manifests, quality evidence, errors, nulls, nested
  values, ordering, and checkpoint identity—not row counts alone.

### Scheduler, Dask, and observation

- Deterministic readiness, exact retrieval/compute concurrency, source request
  deduplication, retry-inclusive attempt reservations, bounded fan-out, and no
  event-loop blocking.
- Source nodes never execute on workers; Dask ineligible placement is visible.
- Actual Dask execution, worker loss, timeout, cancellation, zero retries by
  default, finite expert retries, strict all-Dask planning, and allowed pre-
  execution fallback only.
- Cluster not started on zero-work replay and deterministically closed on every
  terminal path.
- Run/step/retrieval correlation, event semantics, bounded statistics,
  redaction, observer failure isolation, and no raw data or secrets.

### Artifacts and recovery

- Populated, empty, all-null, nested, single/multipart, and partitioned table
  round trips plus bounded modeled JSON.
- Analytics table codec v2 stable-contract compatibility plus unchanged
  Parquet-v1 module-identity enforcement and fixture compatibility.
- Corrupt, truncated, missing, wrong-codec, wrong-contract, wrong-schema, wrong-
  digest, path-traversal, restrictive-permission, disk-full, and interrupted-
  write behavior.
- Crash injection around every file and SQLite commit boundary.
- Child-run lineage, unchanged ancestor reuse, failed-step revision change,
  downstream insertion, targeted recompute, corrupt checkpoint rejection, and
  recovery versus new-run freshness.
- Artifact references load and export after client close.
- Audit all durable files and loaders to prove no pickle-backed result exists.

### Python/YAML and packaging

- Golden equivalent Python/YAML definitions with byte-identical canonical graph
  and fingerprint, plus equal outputs and errors.
- Explicit ``RecipeSnapshot`` handoff, exact four-kind resolution, no implicit
  discovery/import, and no separate operation registry.
- YAML structural schemas canonicalize identically to equivalent Python row
  models and reject unsupported or dotted Python types before any write.
- YAML attacks: duplicate keys, tags, object constructors, anchors, aliases,
  merge keys, multiple documents, excessive bytes/depth/nodes, non-string keys,
  implicit timestamps where strings are required, non-finite values, imports,
  dotted lookup, interpolation, and expressions.
- Prove YAML failure performs no import, discovery, network call, or filesystem
  write.
- Python 3.12 and 3.13.
- Base install without Dask, Polars, or PyYAML; each optional extra separately
  and all extras together.
- No Torch, plotting, model, chart, or visualization dependency/import.

## Redis and bounded live acceptance

The live ledger is cumulative and currently records **651 of 1,000** absolute
attempts, leaving 349 absolute attempts and 149 before the repository's
operational stop at 800. Documentation and architecture review make zero live
calls.

The implementation harness must read the current value immediately before
planning and refuse a reservation unless at least 25 attempts remain below 800
after the worst case. The initial matrix is capped at:

- At most 30 unique cold or revalidation candidates.
- At most 90 reserved attempts including retries.

At the current ledger, a 90-attempt reservation would end at 741 and retain a
59-attempt operational cushion. If the ledger advances, the matrix shrinks
before dispatch.

Acceptance will:

1. Compile and plan all twelve datasets and three workflows with zero HTTP
   attempts and zero artifact writes.
2. Use the existing Redis container and persistent
   ``cfb-data:penn-state-atlas`` selectors where exact contracts and credential
   scope match. It must not reset the ledger or delete the namespace.
3. Warm or revalidate a narrow Penn State team season, one single game, and a
   short program-history range once.
4. Run pandas/local, Polars/local, pandas/Dask, and Polars/Dask in
   ``local_only`` mode with isolated artifact roots and forced independent
   transforms. All replays must add zero HTTP attempts.
5. Run with checkpoints and prove zero source transport and zero transform
   execution where compatible.
6. Inject a downstream failure, revise or insert that cleaning node, recover as
   a child, and prove compatible source and ancestor reuse with zero API calls.
7. Start a genuinely new run and prove it consults normal response-cache
   freshness rather than substituting a prior analytical checkpoint.
8. Record exact attempt deltas, cache outcomes, Dask placement, checkpoint
   reuse, quality results, warnings, skips, and redacted retrieval/analytics
   statistics in the ignored live-report area.

Paid enrichments are not required by the base live matrix. Unavailable or
skipped enrichments remain explicit in coverage evidence.

Final release evidence runs ``make format``, ``make check``, deterministic
Redis integration, the separately gated bounded live harness, distribution
build/metadata validation, and ``git diff --check``. Every failure, skip,
warning, and environment limitation is reported.

## Future integration boundary

Validated immutable artifact descriptors and table semantics are the only
future seam promised here. They provide stable schema, keys, ordering,
partitions, null policy, semantic fields, lineage, and availability evidence
for visualization and batch-readable inputs for future model training.

Future modeling owns feature order/types, targets, encodings, time and leakage
boundaries, splits, seeds, environment, tensors, devices, and safe model
persistence. Future visualization owns chart semantics and rendered output
codecs. Neither concern adds placeholder types or dependencies to this
foundation, and generic pickle remains permanently excluded.
