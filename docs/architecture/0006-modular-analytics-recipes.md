# ADR 0006: Build analytics from modular callable recipes

- Status: Proposed
- Date: 2026-08-18
- Applies from: Acceptance of the modular analytics foundation

## Context

The endpoint client deliberately returns source-shaped validated responses.
Analysts also need durable analytical products that combine those sources,
normalize nested data, make cleaning policy explicit, and preserve enough
evidence to recover after a failure. Those products belong above endpoint
retrieval and below future modeling and visualization layers.

The first implementation put curated datasets, workflow resources, parameter
models, table contracts, and a definition catalog inside the core package. It
made first-party products part of the engine rather than examples of its public
authoring surface. That structure contradicted the intended extension model:
an analyst's dataset should be able to use the same tools, composition rules,
planning, durability, and observation as a packaged dataset without editing a
central index or receiving a less capable execution path.

The corrected architecture therefore needs two deliberately different kinds of
code:

- Generic authoring, planning, execution, persistence, transformation, and
  observation tooling owned by ``cfb_data.analytics``.
- Independent dataset and workflow recipes, including the project's own,
  authored as ordinary modules outside the core package.

Dependency size is not a deciding constraint. This is intended to become a
substantial analytics platform. Dependencies and frameworks are selected by
whether they preserve the product's correctness, extensibility, and parity
contracts rather than by whether they are small.

This record replaces the rejected ADR 0006 design. While its status is
``Proposed``, the recipe API, first-party modules, Dask executor, and durable
analytics runtime described below are planned contracts, not current supported
behavior.

## Decision

### Callable recipes are the public abstraction

The authoring surface will consist of ``@dataset``, ``@workflow``, ``@source``,
and ``@step`` decorators. Each decorator returns an immutable callable recipe
object. Authors do not construct graph, catalog, definition, or table-contract
objects. The four boundaries have different responsibilities:

- A source is an async-capable coordinator-only I/O operation with declared
  output validation, freshness, access, and bounded cost evidence.
- A step is a pure transformation. It is the only Dask-eligible recipe unit.
- A dataset has exactly one final validated tabular output and declares its
  analytical grain and ordering.
- A workflow performs composition and returns an ordered mapping of named
  outputs; it does not hide arbitrary imperative work.

For example, author functions do not receive a client. The endpoint-owned
``GAMES_LIST`` descriptor is bound in decorator metadata, so the source's
identity, revision, response model, access tier, limits, and cost cannot drift
from the endpoint resource:

```python
@source(operation=GAMES_LIST)
async def games(
    context: SourceContext[Game],
    *,
    year: int,
    team: str | None = None,
) -> list[Game]:
    return await context.retrieve(year=year, team=team)


@step(id="example.normalize_games", revision=1, output=GameSummary)
def normalize_games(rows: list[Game]) -> list[GameSummary]:
    ...


@dataset(
    id="example.game_summaries",
    revision=1,
    row=GameSummary,
    grain="one game",
    keys=("game_id",),
    order_by=("season", "week", "game_id"),
)
def game_summaries(
    year: int,
    team: str | None = None,
) -> RecipeRef[list[GameSummary]]:
    return normalize_games(games(year=year, team=team))


@workflow(id="example.season_analysis", revision=1)
def season_analysis(
    year: int,
    team: str | None = None,
) -> dict[str, RecipeRef[list[GameSummary]]]:
    summary = game_summaries(year=year, team=team)
    return {"game_summary": summary}
```

``SourceContext[RowT]`` is an engine-owned, consumed-only public protocol
injected only when the compiled source executes in the coordinator. It is not a
graph-builder argument and is not available to steps, datasets, or workflows.
``RecipeRef[OutputT]`` is a public covariant protocol returned by calls made in
the build context; authors annotate but never instantiate it. First-party
recipe modules import the public ``games`` source callable rather than the
private descriptor. A fully custom source instead declares one namespaced ID,
one semantic revision, output validation, bounded cost, and freshness policy
on ``@source``; it cannot redeclare metadata when an endpoint operation is
bound.

The synchronous Python function given to ``@dataset`` or ``@workflow`` is a
pure graph builder. Its signature contains analytical parameters only; it does
not contain a client. That builder signature is the parameter contract and is
validated strictly through Pydantic. The immutable recipe wrapper has typed
dual call behavior:

- Outside a build context, its first argument is an explicit ``CFBDClient`` and
  calling it returns an awaitable execution result.
- Inside the engine-owned build context, it accepts only the validated builder
  parameters and returns a typed recipe or named-output reference without
  executing work.

The wrapper preserves an inspectable execution signature with the explicit
client plus the original parameter names, defaults, and annotations. The
original builder signature remains the validation authority. Dataset and
workflow builders are never async; asynchronous behavior belongs to source or
explicit async-step execution after compilation.

A dataset combines a colocated Pydantic row model with decorator metadata for
stable identity and revision, grain, keys, ordering, partitions, optional event
time, and semantic field information. The runtime derives a private table
contract from those declarations. Analytics durable compatibility uses a
distinct analytics table codec v2 keyed by stable recipe/output contract ID,
semantic revision, and ordered logical schema digest. For analytics-v2
artifacts, module-qualified Pydantic-model identity is diagnostic provenance
rather than a compatibility key, so moving a recipe module does not by itself
redefine durable compatibility. This narrowly amends ADR 0003 for
analytics-v2 artifacts; the existing Parquet-v1 format, reader, and enforced
module-qualified identity remain unchanged. Public authoring does not require a
parallel parameter model or author-constructed definition, catalog, node,
provider, or table-contract hierarchy. Small immutable framework-owned control
and result
types such as ``ExecutionPolicy``, ``RecipePlan``, ``RecipeInspection``,
``RecipeRun``, ``WorkflowOutputs``, ``RecipeSnapshot``, and ``ArtifactRef``
remain public.

Outside graph construction, a dataset recipe is the analyst interface:

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
```

The caller always supplies the ``CFBDClient`` explicitly; there is no implicit
process-global current client. Backend selection is inherited from that client.
Direct invocation and the advanced ``plan()`` and ``run()`` methods are async.
The direct path returns the client's eager pandas or Polars frame. ``plan()``
is pure and state-independent: it returns a read-only ``RecipePlan`` containing
the compiled nodes, deterministic placement, deduplicated source shapes,
worst-case attempt budget, and validation diagnostics without reading a cache,
checkpoint database, filesystem, environment, or Dask state. An explicit
``recipe.inspect(client, **parameters, plan=plan)`` revalidates the parameters,
requires their fingerprint to match the optional plan, and returns a
``RecipeInspection`` with read-only cache and checkpoint dispositions. The
redacted plan never stores selectors or cache keys merely to enable later
inspection. Execution performs the same preflight internally. Inspection makes
no HTTP request, transform call, artifact write, or store creation. ``run()``
returns a typed recipe run with values, opaque artifact references, lineage,
coverage, quality, and reuse evidence. A workflow returns an immutable mapping
of explicitly named outputs; it never invents a main table.

``CFBDClient`` may accept a lazy ``AnalyticsConfig`` for execution and artifact
policy. It does not gain ``datasets`` or ``workflows`` manager resources.
Constructing or using the endpoint-only client creates no analytics files.

### Recipe calls compose one graph

When a recipe is called while another recipe is being built, the call adds a
namespaced subgraph instead of executing work. Datasets and workflows therefore
compose by ordinary calls:

- A dataset can call another dataset.
- A workflow can call datasets and workflows.
- A dataset can explicitly select a named workflow output when that dependency
  is semantically appropriate.
- A parent workflow explicitly selects or re-exports child outputs; outputs are
  never flattened implicitly.

Nested calls receive deterministic namespaces derived from the parent
invocation path, child recipe identity, and explicit alias. Reusing the same
child more than once uses ``child_recipe.as_("alias")(...)``; call ordinals are
not stable identity. A named workflow output is selected explicitly with
``child_workflow(...)["output_name"]``.
Graph shape may depend on validated plan-time parameters but never on source
results or DataFrame contents. The bounded map/gather primitive accepts only a
validated plan-time parameter sequence, requires stable unique keys, and fully
expands during compilation. Compilation rejects duplicate aliases, recursive
expansion, cycles, ambiguous output bindings, incompatible schemas, unsupported
backends, and expansion or attempt plans above their configured limits before
operational I/O.

Explicit dataset-to-workflow-output selection narrowly amends ADR 0001's
default workflow-above-dataset layering. The compiler slices the child workflow
to the selected output's transitive dependency closure before validation and
planning. Unselected outputs are not compiled, budgeted, fingerprinted,
executed, or checkpointed, and the dataset cannot consume the workflow mapping
or rely on workflow side effects. The selected output retains its ordinary
recipe and artifact identity inside the parent namespace. Authors should still
extract a generally reusable analytical product as a dataset rather than using
a workflow as an indirect definition container.

Every decorated source, step, and final recipe boundary is independently
observable and checkpointable. A nested recipe output may bind to the same
content-addressed artifact as its final step rather than copying data.

Recipe-building functions are trusted declarative Python and are required to
be pure graph builders. They receive parameters and recipe references, not an
open client or artifact store. Discovery may import explicitly trusted provider
code, so it is a distinct phase from planning. Compilation and async ``plan()``
do not invoke or inspect a declared source, transform, cache, checkpoint
database, artifact store, filesystem, environment, Dask operation, or
transport. State inspection is an explicit phase after the immutable plan
exists. The runtime cannot sandbox arbitrary Python imported by a trusted user
module. Safe YAML is the stronger non-executable authoring boundary.

### Registration is automatic and discovery is opt-in

There is no public ``DatasetCatalog``, central recipe list, definition file, or
hand-maintained ``__init__`` re-export index.

Decorating a function creates an immutable recipe object at module scope and
invokes a private runtime-owned automatic-registration hook. The hook records
an immutable candidate; it does not create a mutable execution catalog, and a
directly imported Python or notebook recipe is immediately callable without a
registration call. Stable-ID resolution uses only an immutable
``RecipeSnapshot`` returned by ``discover_recipes(...)``. The private candidate
index is discovery bookkeeping, never the lookup authority for a plan already
in progress.

Snapshot creation and registration share one process-wide reentrant discovery
lock. An ordinary-import candidate is eligible only after its defining module
has finished initialization and the object remains bound at its declared
qualified name. A failed or still-initializing ordinary import is therefore
absent from a snapshot. The snapshot builder consumes registered candidates;
it never discovers recipes by walking ``sys.modules``.

Installed providers opt into the ``cfb_data.recipes`` entry-point group. Each
entry point resolves to exactly one ordinary provider package root owned by
that distribution. Namespace packages or roots spanning multiple locations
are rejected. On first discovery, providers are ordered by normalized
distribution name, entry-point name, and target module. At most 1,000
submodules strictly within that provider package are imported in lexical order
and their module-scope recipe objects are staged. This executes trusted
provider package code; it does not scan arbitrary filesystem locations or
import non-provider packages.

Provider discovery is transactional. Before importing a selected provider, the
runtime claims its package root and installs a context-local staging sink while
holding the discovery lock. Decorator calls from that root enter only the
transaction, never the ordinary candidate index. Candidates from already
loaded provider submodules are explicitly restaged under the same transaction.
All candidates are structurally validated, deduplicated, and conflict-checked
before one immutable snapshot is published.

An import failure, cycle, invalid recipe, or conflict discards the complete
provider stage. Provider modules that Python leaves in ``sys.modules`` remain
quarantined from ordinary registration and every later snapshot unless a new
transaction successfully restages and commits the entire provider. Python
cannot undo unrelated side effects performed by trusted failing code, but no
recipe from the failed provider becomes addressable. Concurrent snapshot
creation and provider discovery serialize on the same lock and cannot observe
mid-import candidates.

The durable registry key is ``(recipe kind, namespaced ID, semantic revision)``.
Re-exporting the same recipe object is deduplicated. Reloading a module may
replace its earlier candidate only when the key, defining module and qualified
name, normalized declaration, and inspectable diagnostic source digest match.
That source digest protects reload behavior but is not durable compatibility
identity. A changed definition at the same revision is a conflict and requires
an explicit revision change. There is no implicit latest revision and import
order never resolves a collision. A plan or run freezes one snapshot, and
later imports cannot mutate that execution.

``AnalyticsConfig`` may disable installed-provider discovery or allow-list
exact provider identities comprising normalized distribution name,
entry-point name, and target module, with an optional distribution-version
constraint. An entry-point name is never recipe identity. Explicitly imported
recipes remain directly callable even when provider discovery is disabled.

Cross-run reuse and stable-ID lookup require an explicit namespaced recipe
boundary ID and integer semantic revision. An unversioned notebook recipe is
directly callable and composable and may reuse committed work only while
recovering its originating run; it is not published to the durable lookup
snapshot, addressable from YAML, or eligible for cross-run reuse.

YAML resolves an exact kind, namespaced ID, and revision only against a caller-
supplied ``RecipeSnapshot``. The explicit handoff is
``load_recipe_yaml(text, recipes=discover_recipes(config))``; callers may reuse
the opaque immutable snapshot, but cannot mutate it or use it as a definition
index. YAML loading never initiates provider discovery or a Python import and
never selects an implicit latest revision.

### First-party recipes use the user extension path

The distribution will include a separate top-level ``cfb_data_recipes``
package. Core ``cfb_data.analytics`` will never import that package. The
official package will be loaded through the same ``cfb_data.recipes`` entry
point used by external providers.

Each first-party dataset or workflow will be one self-contained module directly
under ``cfb_data_recipes``. A module will own its parameter signature, Pydantic
row model, semantic metadata, source composition, local transformations,
recipe, documentation, and black-box tests. It may use only the public
authoring, source, step, and composition interfaces available to an
external provider; the official namespace receives no allow-list or private
endpoint bypass.

The initial modules will be:

- ``game_summaries.py``
- ``team_games.py``
- ``player_game_stats.py``
- ``drives.py``
- ``plays.py``
- ``rosters.py``
- ``team_seasons.py``
- ``player_seasons.py``
- ``poll_rankings.py``
- ``betting_lines.py``
- ``recruiting_classes.py``
- ``coach_seasons.py``
- ``team_season_analysis.py``
- ``single_game_analysis.py``
- ``program_history.py``

The namespace will have no ``datasets`` or ``workflows`` subpackage,
centralized domain-model module, or re-export list. Built-in recipes will have
no privileged compiler, registry, executor, persistence, or observer access.

### Sources share endpoint-owned contracts

Analytics source callables reference stable typed endpoint-operation
descriptors owned by the relevant endpoint domain. An operation descriptor
owns its stable ID and revision, fixed route, request validation, response
adapter, source row model, result shape, access tier, documented limits, and
cost evidence. Existing endpoint resources and analytics sources consume the
same descriptor so they cannot drift.

An endpoint-backed ``@source(operation=...)`` derives identity, revision,
request and response validation, access, limits, and cost from that descriptor;
the decorator rejects duplicate overrides. The bound descriptor is visible to
the compiler without executing the async source body. First-party recipe
modules consume the resulting public source callable. Fully custom sources use
the explicit declaration form and own exactly one corresponding semantic
revision.

There is no public generic path router. YAML and recipes reference registered
source callables. Trusted user source adapters must
declare identity, revision, output, bounded cost behavior, and freshness
semantics; an unknown or unbounded source cost fails planning. Plans distinguish
logical source calls, identical calls deduplicated within the graph, and
worst-case actual HTTP attempts including retries. Cache hits consume zero
actual attempts, and only the transport records and reserves a dispatched
attempt. Arbitrary side-effect nodes remain outside this decision.

### One narrow coordinator owns correctness

The embedded coordinator compiles a finite graph, schedules deterministic ready
work, deduplicates identical source requests, reserves actual HTTP attempts,
validates canonical outputs, commits durable artifacts, and emits redacted
events. It is deliberately not a general orchestration platform: it has no
daemon, deployments, cron, queue, remote worker control plane, arbitrary
side-effect contract, data-dependent dynamic DAG, or scheduler service.

Independent source nodes always execute in the coordinator through one open
``CFBDClient``, its pooled HTTP session, response cache, source single-flight,
attempt ledger, and run-wide semaphore. Retrieval concurrency defaults to four.
The coordinator cancels and awaits siblings on failure, preserves
``CancelledError``, and records terminal state durably.

Synchronous local compute and artifact I/O run off the event loop. Local
compute concurrency defaults to one. Async steps are supported when they are
genuinely non-blocking and preserve the pure transformation boundary.

Analytics run, step, placement, validation, and artifact events form a separate
family from ADR 0005 retrieval events. Context-local run and step IDs correlate
the two families. Observer delivery remains bounded, ordered at each dispatcher,
synchronous, redacted, and failure-isolated. Plans, manifests, events, and safe
run errors do not contain selector values, credentials, cache keys, response
bodies, DataFrame rows, filesystem paths, exception messages, or worker
exception objects.

### Dask is a first-class compute executor

Dask will be an optional execution dependency and a fully supported compute
option, not the owner of source retrieval or analytical persistence. Version
one will use a coordinator-owned temporary ``distributed.LocalCluster`` with at
most four worker processes, bounded by available CPUs, and one thread per
worker by default. The coordinator opens the cluster for one run, cancels and
awaits outstanding futures during failure or cancellation, and closes the
client and cluster deterministically.

Both local and Dask modes invoke the same transform-worker contract. Dask
receives only trusted operation or callable identity, explicit revision, finite
validated parameters, canonical Arrow inputs, and bounded metadata. Workers
return canonical Arrow and bounded JSON diagnostics. The coordinator
revalidates the result, emits authoritative events, and alone may commit SQLite
state or Parquet/JSON artifacts.

Sources, credentials, response-cache backends, artifact-store ownership, and
HTTP-attempt reservations are never serialized to Dask workers. Static
capability inspection places a transform that is not Dask-eligible on the
coordinator, and that placement is visible in the plan. Selecting Dask
therefore never removes a valid recipe capability merely because one node is
coordinator-bound.

A Dask-eligible node selected for Dask is not silently rerun locally after a
user-code exception, timeout, worker loss, or partial execution. Dask task
retries default to zero; an expert may enable a finite retry policy only for
declared pure steps, with each retry observable. A separately typed policy may
permit coordinator fallback for a pre-execution cluster-startup or
serialization-capability failure. That fallback emits an explicit placement
event. Another strict policy may require all transform nodes to be Dask-placed
and fail planning otherwise. In-flight tasks and Arrow payloads are bounded by
execution policy so worker submission cannot create unbounded memory pressure.

Dask may use transient trusted-code serialization while dispatching work. That
transport is not a durable format. No checkpoint, manifest, artifact, or
artifact loader may persist or load pickle. A worker or coordinator failure
before coordinator validation and commit cannot publish a successful node.

Existing multi-host schedulers and remote clusters are deferred until the
platform defines remote artifact ownership, worker-environment verification,
transfer limits, distributed cancellation, and representative acceptance
infrastructure. The executor interface must not prevent that later addition.

### Every offered option has runtime parity

Parity is a release gate, not a documentation aspiration:

- **pandas and Polars:** equal canonical Arrow schema, logical values, nulls,
  nested values, column order, row order, quality outcomes, and failure
  behavior. Native dtypes need not be identical.
- **local and Dask:** the same compiled graph, source behavior, fingerprints,
  validation, artifacts, recovery, lineage, event meanings, and logical
  outputs. Only eligible compute placement, timing, concurrency, and event
  interleaving may differ.
- **Python and YAML:** equivalent finite definitions compile to the same
  canonical recipe representation and fingerprint and use the same planner,
  runtime, persistence, and errors. Python may author trusted executable code;
  YAML safely composes registered capabilities.
- **first-party and user recipes:** the same decorators, discovery, compiler,
  executor, contracts, persistence, and documented features.

First-party recipes must pass every pandas/Polars by local/Dask combination.
Custom steps may declare an intentionally narrower backend set, but an
unsupported selection fails during planning and is not advertised as a parity
option. Executor choice is audit metadata rather than part of portable content
identity. Backend identity is included only when a step's semantics are
explicitly backend-specific.

Narwhals stable v2 supplies its supported portable flat-table subset. It is not
treated as proof of parity. Nested extraction, struct flattening, and explicit
list explosion remain library-owned Arrow or logical-record operations, and
every built-in operation requires independent backend and executor tests.

### Durable artifacts remain separate from the response cache

Redis and the existing SQLite cache remain exact API-response caches with
freshness, stale fallback, and eviction policy. Analytical recovery is a third
component:

- SQLite transactionally stores immutable runs, node outcomes, parent/child
  recovery lineage, cross-process leases, and retention pins.
- The filesystem stores immutable content-addressed objects.
- Canonical analytics table artifacts use codec v2, ordered Parquet parts, and
  a versioned manifest. Endpoint Parquet-v1 remains readable and unchanged.
- Bounded modeled control artifacts use canonical Pydantic/JSON with non-finite
  values rejected.
- Pickle and arbitrary Python-object artifacts are permanently excluded.

Every descriptor records codec and media identity, content and part digests,
byte and row counts, stable output/schema identity, grain, keys, ordering,
partitions, semantic fields, producer and upstream identities, availability
evidence, coverage, quality, and bounded dependency-version evidence.

Writers stage content, close and validate it, compute digests, flush files and
directories, atomically publish the immutable object, and commit node success
in SQLite last. Corrupt, missing, truncated, schema-incompatible, or
digest-incompatible content fails closed.

Checkpoint identity is Merkle-style per decorated boundary. It includes engine
and IR version, that boundary's one authoritative identity and semantic
revision, normalized parameters and semantic policies that affect values,
ordered upstream content digests, output schema and codec, and backend only
where required. An endpoint-backed source derives that one revision from its
operation descriptor; a custom source or step owns it on its decorator. There
is no second code or implementation revision. Operational policy such as
executor, concurrency, retry, or pre-execution fallback is audit evidence and
is not portable content identity. The key does not include an entire parent
recipe definition, allowing a downstream edit to preserve compatible
ancestors.

Recovery always creates an immutable child run. It may preserve the validated
source snapshot of the selected incomplete run. A genuinely new run always
executes source nodes through current response-cache freshness; an analytical
checkpoint cannot freeze an old API snapshot. Failed and cancelled nodes never
publish successful artifacts.

### YAML uses the same recipes without becoming executable configuration

The optional YAML loader constructs the same immutable recipe and node
representation as Python authoring. It supports finite composition of the four
registered kinds—sources, steps, datasets, and workflows—plus parameters,
literals, and named outputs. There is no separate operation registry: every
YAML-addressable transform is a versioned ``@step`` and every endpoint access
is a versioned ``@source``. Every reference includes exact kind, namespaced ID,
and revision and resolves through the supplied ``RecipeSnapshot``; bindings
validate against the same callable signature and Pydantic models as Python.

A YAML-defined dataset declares its ordered output through a bounded,
versioned structural schema grammar for supported JSON-compatible scalar,
list, and struct types, with explicit nullability and semantic field metadata.
Python paths and model imports are not schema syntax. The loader derives the
private Pydantic adapter and Arrow schema from that declaration before any
rows exist. Python row models and YAML schemas canonicalize to the same logical
schema representation, so equivalent Python and YAML definitions have
byte-identical canonical graph representations and fingerprints. Only after a
complete document validates does the resulting immutable recipe enter the same
automatic-registration hook as a Python recipe.

The loader accepts one UTF-8 document of at most 1 MiB and rejects duplicate or
non-string keys, aliases, anchors, merge keys, explicit tags, multiple
documents, non-finite or non-JSON values, excessive depth or node counts,
imports, expressions, templates, environment interpolation, shell commands,
loops, and unbounded fan-out. Strict Pydantic validation forbids unknown
fields. Calling it without the optional dependency raises
``CFBDOptionalDependencyError`` with installation guidance.

### Artifacts are the future modeling and visualization seam

Stable schemas, grain, keys, ordering, partitions, null policy, semantic field
metadata, availability evidence, lineage, and immutable batch-readable content
are the no-refactor integration boundary for later modeling and visualization.

This decision adds no PyTorch, plotting, chart, feature, target, split, tensor,
GPU, or model abstraction. Future artifact kinds must add an explicit versioned
validating codec without changing recipe composition, scheduling, lineage, or
observation. Generic pickle remains excluded.

## Consequences

- A first-party recipe demonstrates the public extension surface instead of
  defining a private product tier.
- Analysts can import one module and call one object while advanced users can
  inspect the exact same plan, artifacts, lineage, and recovery state.
- Core analytics code becomes more generic, while recipe-specific semantics
  remain visible and reviewable beside each recipe.
- Automatic registration introduces a trusted import boundary that must be
  deterministic, collision-safe, reload-safe, and tested independently of
  import order.
- Supporting Dask as a parity option requires a real executor matrix and
  worker-failure tests, even though sources and persistence remain local.
- Durable analytics persistence has explicit retention and operational
  responsibility; it is not silently evicted like a cache.
- The proposed decision is accepted only after a vertical slice proves direct
  and nested recipe authoring, no-I/O planning, async pooled sources, local/Dask
  parity, safe artifacts, and first-party/user discovery through black-box
  tests.

## Alternatives considered

### Public dataset/workflow manager resources and a central catalog

Rejected. A manager and catalog make built-in definitions part of the engine,
force additions through a central index, and invite a privileged path that
external recipes cannot reproduce. A recipe must be independently importable,
callable, composable, and automatically discoverable.

### Use Dagster as the execution engine

Rejected for this embedded layer. Dagster supplies strong graph composition,
assets, checks, lineage, and module discovery. Its Dask execution model requires
a persistent Dagster instance, reconstructable jobs, and worker-visible I/O,
while dispatching execution steps away from the coordinator. Preserving one
pooled client, coordinator-owned attempts, local/Dask event parity, and the
project's Arrow/JSON recovery contract would require a custom executor, I/O
manager, event bridge, source stage, and lifecycle wrapper. Those are the
cfb-data coordinator's actual responsibilities rather than incidental adapters.

See [Dagster Dask execution](https://docs.dagster.io/deployment/execution/dask).

### Use Apache Hamilton as the execution engine

Rejected despite its attractive function-module model and static graph
inspection. Its asynchronous driver, durable caching/materialization, and Dask
adapter do not form one supported path: the async builder does not support all
materializer and dynamic features, documented cache support is not async, its
default cache uses pickle, and its Dask adapter is experimental. Replacing
those portions would leave Hamilton naming rules around a cfb-owned runtime.

See [Hamilton AsyncDriver](https://hamilton.apache.org/reference/drivers/AsyncDriver/),
[caching limitations](https://hamilton.apache.org/reference/caching/caching-logic/),
and the [Dask adapter](https://hamilton.apache.org/reference/graph-adapters/DaskGraphAdapter/).

### Use Prefect as the execution engine

Rejected for the static-plan contract. Prefect's ordinary Python flows and
Dask task runner are useful, but a flow discovers consequential work while it
runs. Placing a static cfb-data representation above Prefect would make the
cfb-data compiler the real engine while also requiring replacement of Prefect
result persistence and source ownership.

See [Prefect flows](https://docs.prefect.io/v3/concepts/flows),
[result persistence](https://docs.prefect.io/v3/advanced/results), and
[task runners](https://docs.prefect.io/v3/concepts/task-runners).

### Use Dask as the entire workflow engine

Rejected. Dask is the selected compute executor, but it does not own API-cache
freshness, quota reservation, stable source snapshots, fail-closed analytical
artifacts, child-run recovery, or cfb-data event semantics. Keeping those
policies in the coordinator allows Dask to provide parallel computation without
creating a second product.

See [Dask Delayed](https://docs.dask.org/en/stable/delayed.html) and
[Dask Futures](https://docs.dask.org/en/stable/futures.html).

### Extend the API response cache with workflow checkpoints

Rejected. Response-cache TTLs, stale fallback, credential scoping, fail-open
behavior, and eviction are incompatible with durable analytical lineage and
fail-closed artifact validation. ADR 0004 already requires a separate
component.

### Persist native DataFrames or arbitrary Python objects

Rejected. Native backend types would make pandas/Polars and local/Dask
compatibility unstable. Pickle is unsafe as a durable generic boundary and
cannot provide an inspectable cross-version contract. Arrow/Parquet and bounded
validated JSON remain canonical.

### Allow executable YAML or filesystem-wide plugin discovery

Rejected. Arbitrary imports, evaluation, templating, and scanning turn a data
definition into an uncontrolled code-loading and I/O boundary. YAML composes
allowlisted registered capabilities; installed Python providers opt in through
entry points, and local Python recipes are imported explicitly.
