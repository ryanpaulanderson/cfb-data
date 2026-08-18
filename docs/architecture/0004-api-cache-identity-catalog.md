# ADR 0004: Cache validated API responses and maintain a durable identity catalog

- Status: Accepted
- Date: 2026-08-13
- Applies from: API-cache and identity-catalog implementation

## Context

The project has two persistence concerns that are both commonly described as
"caching" but have different correctness and lifecycle requirements.

Workflow checkpoints preserve completed step outputs so an orchestrator can
recover after an error, release memory between steps, and avoid repeating
completed work. They are durable, manifest-driven artifacts. They are not
governed by freshness TTLs or ordinary cache eviction. The canonical Arrow and
versioned Parquet contract in
[ADR 0003](0003-canonical-arrow-parquet.md) is the storage primitive for future
tabular workflow checkpoints, but orchestration, manifests, partitioning, and
recovery remain separate work.

API caching reduces duplicate CollegeFootballData requests, latency, payload
transfer, and quota consumption. It is read-through persistence with
endpoint-specific freshness, bounded stale use, eviction, and request
coalescing. It must work with the existing asynchronous `aiohttp` transport,
preserve the request and response validation boundary from
[ADR 0001](0001-validated-models-before-dataframes.md), and remain independent
of pandas or Polars presentation.

An exact API response cache is not sufficient for identity-driven work. A
broad response such as `/games?year=2025` does not exact-key-match a later
request for one game, and downloading or materializing a complete endpoint
payload merely to obtain an ID or canonical name wastes work. Workflows and
applications need durable, locally queryable facts such as team, conference,
venue, game, athlete, recruit, coach, drive, and play identifiers.

These identity facts have a different lifecycle from their source response.
When the source response's TTL expires, the coverage is due for refresh; the
known identity must not disappear. A team ID, game ID, or athlete ID remains
useful while the library determines whether its source partition needs to be
refreshed.

The API's current terms explicitly permit private caching, normalization, and
retention and encourage caching or polling strategies that reduce traffic.
They prohibit redistribution of raw data and do not guarantee that provider
identifiers remain stable. The cache and catalog must therefore be private,
versioned, observable, and rebuildable. See the
[CollegeFootballData Terms of Use](https://collegefootballdata.com/terms).

## Decision

Add one project-owned asynchronous persistence capability with two logical
components:

1. an **exact validated-response cache** with freshness and retention
   deadlines; and
2. a **durable identity catalog with a coverage ledger** whose facts do not
   expire when response freshness expires.

The components may use the same configured SQLite or Redis deployment, but
they use separate schemas or key namespaces and retain their distinct
semantics. A future workflow-checkpoint store remains a third, independent
component.

```text
public endpoint method
        │
        ▼
request validation and serialization
        │
        ▼
endpoint executor ──► active-client check
        │
        ▼
cache coordinator
        ├──► exact validated-response cache
        │       ├── fresh hit ───────────────────────────────┐
        │       └── stale or miss                            │
        │                                                    │
        ├──► process-local single-flight                     │
        │       └──► SQLite or Redis cross-process lease     │
        │                       │                            │
        │                       ▼                            │
        │              async HTTP transport                  │
        │                       │                            │
        │                       ▼                            │
        └────────────── Pydantic response validation ◄───────┘
                                │
                                ▼
                  source-owned typed declarations
                    or colocated contextual hook
                                │
                                ▼
                    canonical observation batch
                      ┌─────────┴─────────┐
                      ▼                   ▼
          response-cache write   transient / SQLite / Redis
                                          │
                                          ▼
                             domain-owned identity view

typed identity query
        │
        ▼
identity planner
        ├──► catalog and coverage
        ├──► retained response entry
        └──► minimum-cost hydration request
                    │
                    ▼
            compact domain identity model
```

### Authority boundary and singular projection path

The upstream response contract and the library's normalized catalog contract
have different owners. Each source-domain Pydantic model is the single owner
of every upstream field expectation and of the declaration that maps those
validated attributes to catalog meaning. Simple mappings use typed
`Annotated` declarations. Contextual mappings use a pure typed hook colocated
with the source model and receive validated request and ancestor context.
Roster season, player stints, dynamic game roles, nested game/drive/play
relationships, and derived status are contextual rather than inferred from
field names.

The neutral catalog layer owns only library-defined semantics: entity and
relationship grains, three-state observations, authority and merge rules,
indexes, coverage, provenance, codecs, and compact read views. It never owns
a copied upstream response schema. Central projection therefore has no domain
class-name registry, dumped-dictionary lookup, field-name guessing, or domain
branch. Actual model classes and validated attributes connect declarations to
the generic compiler.

There is one data path for every configuration:

```text
validated Pydantic response
    -> source-owned declaration or typed hook
    -> canonical observation batch
    -> transient, SQLite, or Redis catalog
    -> domain-owned compact identity
```

Disabling response persistence selects the transient in-memory catalog; it
does not select a second response-to-identity converter. A configured backend
is mirrored to the transient catalog after validation so a successful network
response can still answer identity intent if persistence fails. The transient
catalog is client-scoped and disappears when the client closes. Explicit
hydration still requires durable SQLite or Redis because a resumable hydration
run must preserve progress.

The five public normalized read views live with their owning domains:
`TeamIdentity`, `ConferenceIdentity`, `VenueIdentity`, `GameIdentity`, and
`AthleteIdentity`. `client.identities` remains the intent-oriented resolver and
hydration facade, but it is not a parallel schema namespace. Normalized views
reuse domain enums such as `ConferenceClassification`, `SeasonType`, and
`GameStatus` instead of widening them to arbitrary strings.

Every projected field has one of three presence states: unobserved, observed
null, or observed value. Zero or invalid provider placeholders never create an
entity or relationship. Sparse observations preserve richer values;
authoritative nulls and empty collections may clear them. Higher authority
wins conflicts. Equal authority uses observation time followed by a stable
source tie-break, making ingestion-order permutations deterministic.

### Placement and validation

The response-cache coordinator sits at the endpoint-executor boundary around
transport I/O. The executor has the validated request, canonical serialized
parameters, response contract, and backend-neutral validated result needed to
apply policy consistently to list, scalar-list, and model responses.

The transport continues to own authentication, HTTP, retry behavior, and its
pooled session. It returns a bounded response envelope containing the raw JSON
body and the safe metadata needed by caching, including status, content type,
ETag, Last-Modified, and quota headers when present.

A response is written only after its JSON shape and endpoint-specific Pydantic
contract validate. Cache records contain non-executable JSON bytes and
explicit metadata, never pickle. Every hit is decoded and validated through
the current response contract before it reaches identity projection or
presentation. A corrupt, incompatible, or oversized record is evicted and
treated as a miss.

The executor checks that the one-shot `CFBDClient` is inside its active
`async with` context before any cache or catalog lookup. A cache hit must not
bypass the client's existing lifecycle contract.

Only successful validated responses are cached. A valid empty response is a
successful response. Authentication failures, authorization failures, request
errors, redirects, rate limits, server errors, transport failures, JSON decode
failures, and response-validation failures are not cached as responses.

Existing endpoint methods continue to return their complete upstream-shaped
results in upstream row order. The cache does not satisfy an arbitrary narrow
endpoint call by locally filtering a broader response because doing so could
change row ordering or other observable endpoint semantics.

### Backend contract and ownership

The library supplies three implementations behind small async protocols:

- a transient in-memory identity catalog for disabled or failed persistence;
- SQLite through `aiosqlite`, recommended for local and single-host use; and
- Redis through `redis.asyncio`, recommended for multiple workers, containers,
  or hosts.

The protocols separately express lifecycle, response-record, catalog-write,
coverage, identity-read, and refresh-lease operations. They do not expose
backend-specific handles to endpoint or domain code. The configured backend is
opened and closed with the client and owns its connection or pool.

SQLite uses a platform-appropriate per-user cache location by default, with an
explicit path override. It enables WAL, uses a finite busy timeout and
`synchronous=NORMAL`, and is limited to local storage; SQLite WAL is not a
multi-host or network-filesystem coordination mechanism. `aiosqlite` becomes a
normal runtime dependency so the recommended lightweight backend requires no
feature extra.

SQLite DDL and statements are installed as dedicated `.sql` resources rather
than embedded in Python modules. One strict Jinja handler owns package-relative
loading and rendering. Jinja substitutions are limited to validated structural
values that SQLite cannot bind, such as a repeated predicate count or a pragma
integer; response, identity, and filter data always use SQLite bound
parameters. The explicit SQL files therefore remain the reviewable source of
truth for schema and query behavior without weakening injection boundaries.

Redis accepts an explicit `redis://` or `rediss://` location and uses one
pooled async client. The `redis` Python package remains an optional `redis`
extra. Response records use one Redis key per entry and native expiry at their
retention deadline. Catalog facts and coverage records have no TTL. A Redis
deployment intended to preserve the catalog uses persistence and an eviction
policy such as `volatile-lfu` that selects expiring response records rather
than non-expiring catalog keys. A dedicated Redis deployment is recommended
when hosted-service policy cannot provide that invariant.

SQLite response cleanup deletes only expired response records. Redis expiry
also applies only to response records and temporary leases. Neither backend
automatically deletes catalog facts or coverage records merely because source
coverage became stale. Catalog pruning is an explicit, separately configured
maintenance operation.

The implementation includes example Redis Docker and Compose configurations,
health checks, a volume-backed persistence example, and hosted `rediss://`
configuration guidance. It does not silently fall back from a configured Redis
backend to SQLite.

### Cache configuration

Caching remains optional but is strongly recommended. `cache=None` preserves
network-only response behavior while validated responses enrich a client-local
transient identity catalog. `SQLiteCacheConfig()` selects the no-service local option;
`RedisCacheConfig(url=...)` selects Redis. Backend selection and cache policy
are independent so changing the backend does not change freshness behavior.

Built-in policy applies when the user supplies no TTL configuration. Users may
provide immutable, typed overrides by cache profile without configuring every
endpoint. A policy value has two deadlines:

- `fresh_for`: return the response without network I/O; and
- `retain_for`: retain the response from its original fetch time for
  conditional revalidation and permitted stale-if-error behavior.

`retain_for` must be greater than or equal to `fresh_for`. Durations must be
finite and non-negative. The configuration uses `datetime.timedelta`, not raw
unitless numbers.

Conceptually, configuration has this shape:

```python
CachePolicyConfig(
    ttl_overrides={
        CacheProfile.STABLE_REFERENCE: CacheTTL(
            fresh_for=timedelta(days=365),
            retain_for=timedelta(days=1095),
        ),
        CacheProfile.ROSTER: CacheTTL(
            fresh_for=timedelta(days=14),
            retain_for=timedelta(days=60),
        ),
    }
)
```

Policy precedence is:

1. an explicit per-call refresh, bypass, or local-only mode;
2. a user cache-profile override;
3. a built-in response-state refinement; and
4. the built-in profile default.

User TTL overrides do not weaken structural rules: operational account data
remains non-cacheable, invalid responses remain non-cacheable, cache hits
remain validated, and secret values remain excluded from cache data and logs.

### Built-in TTL policy

The built-in policy reflects college-football data cadence rather than generic
web-cache conservatism.

| Profile | Fresh for | Retain for | Representative data |
| --- | ---: | ---: | --- |
| Stable reference | 180 days | 730 days | Teams, conferences, venues, conference affiliations |
| Reference vocabulary | 365 days | 1,825 days | Play types, play-stat types, stat categories, draft teams and positions |
| Current or future roster | 7 days | 30 days | Season roster snapshots |
| Current or future schedule | 3 days | 14 days | Broad season and week game schedules |
| Imminent-game schedule | 24 hours | 7 days | Game-specific schedule data within 48 hours of kickoff |
| Active-season aggregate | 24 hours | 14 days | Rankings, ratings, records, talent, and season statistics |
| Active recruiting cycle | 3 days | 30 days | Recruits and transfer-portal data for an open cycle |
| Recently completed game | 24 hours | 30 days | Results within the 72-hour correction window |
| Closed historical data | 365 days | 1,825 days | Completed seasons outside the correction window |
| Betting | 15 minutes | 6 hours | Lines and market data |
| Weather | 1 hour | 12 hours | Forecasts and conditions |
| Live scoreboard | 15 seconds | 2 minutes | In-progress scoreboard data |
| Live plays | 5 seconds | 30 seconds | Play-by-play for an active game |
| Operational account | not cached | not cached | Account, usage, quota, and authorization-sensitive responses |

A mixed response uses the shortest applicable policy. A broad schedule
containing an imminent game therefore cannot remain fresh for three days.
Current or future empty schedules, rosters, recruiting data, and similar
"not published yet" results have at most 24 hours of freshness. Empty closed
historical partitions use the historical policy.

Historical status requires completed data outside the correction window; a
year number alone is insufficient. Explicit refresh remains available for all
cacheable data. When a retained entry has a validator, refresh sends
`If-None-Match` or `If-Modified-Since`; a valid `304 Not Modified` response
extends the entry's deadlines without replacing its body. Conditional requests
may reduce transferred bytes after freshness expires, but they are not treated
as quota avoidance because they still contact the API.

### Cache identity and isolation

One authoritative key builder constructs versioned, type-preserving canonical
material from:

- cache-key format version;
- normalized API origin;
- HTTP method and fixed endpoint path;
- sorted validated query parameters, preserving omitted values distinctly
  from `false`, zero, and empty strings;
- representation-affecting request metadata;
- response-contract identity and version; and
- a non-secret credential/account-scope digest.

The stored key is a SHA-256 digest in a versioned namespace. It excludes the
pandas or Polars backend because cached responses are presentation-neutral. It
never contains an API token, and operational keys, logs, metrics, and errors do
not expose raw query values. Changing the key or response-storage contract
uses a new namespace rather than interpreting incompatible records.

### Request coalescing and cross-process leases

The first implementation includes both process-local single-flight and real
cross-process refresh leases for SQLite and Redis.

Within one process, the coordinator owns one shared future per response-key
digest. The leader performs the refresh; followers await the same result or
exception. Follower cancellation is shielded and cannot cancel the leader.
Leader cancellation performs cancellation-safe cleanup, and completed or
failed entries are removed from the in-process map.

The local leader must then acquire the configured backend's lease before
calling the API. It rechecks the response cache after becoming local leader
and again after acquiring the distributed lease, because another worker may
have populated the entry in either interval.

Redis acquires a lease with atomic `SET lease-key owner-token NX PX 60000`.
The leader renews it every 20 seconds while a refresh remains active. Renewal
and release use token-comparing server-side operations so a former owner
cannot extend or delete a successor's lease.

SQLite stores the response-key digest, unique owner token, acquisition time,
and expiry in a lease table. It uses a short `BEGIN IMMEDIATE` transaction to
insert a missing lease or conditionally replace an expired lease. Renewal and
release require the current token.

Waiters poll the response entry with bounded jitter and preserve coroutine
cancellation. They may become the next refresher only after acquiring an
expired or released lease. The follower wait budget is derived from the
client's per-attempt timeout and retry policy rather than being an unbounded
wait. The renewable 60-second lease accommodates multi-attempt requests and
server-directed retry delays while ensuring an abandoned lease expires.

These leases prevent quota-wasting cache stampedes; they are not a general
distributed correctness lock and do not require quorum or Redlock semantics.

### Failure and stale behavior

Response-cache I/O has its own finite timeout. For normal endpoint calls, an
unavailable optional cache fails open to the API after emitting bounded,
redacted observability events. Process-local single-flight remains active, but
cross-process duplication is possible until the backend recovers. The
implementation does not report a backend failure as a cache miss without also
recording the failure category.

Ordinary response and identity operations use the configured two-second cache
deadline. An atomic response-plus-catalog commit may contain tens of thousands
of validated observations, so its deadline scales with batch size and remains
bounded at 30 seconds. This separates an expected bulk-commit cost from the
latency contract for ordinary reads without making either operation unbounded.

A retained response may be served after the normal HTTP retry policy is
exhausted only for retryable transport failures or HTTP `408`, `429`, and
`5xx` responses and only before `retain_for` expires. Stale data never masks
authentication, authorization, invalid-request, redirect, decode, or response-
validation failures.

Identity `ENSURE_FRESH` queries may project and return a validated transient
identity if the API succeeds while catalog persistence is unavailable.
`LOCAL_ONLY` identity queries use only facts already present in the configured
or client-local transient catalog and never contact the API. Backend failure
behavior remains observable; it does not activate a second conversion path.

### Identity catalog

The identity catalog uses explicit typed entity and relationship schemas, not
an entity-attribute-value table and not persistence generated from response
models. It preserves provider identifiers as
opaque source identifiers and records enough provenance to rebuild or
reconcile them. Athlete identifiers remain strings internally even where an
upstream request happens to accept an integer.

The initial implementation audits every supported response model and supplies
projectors for every stable or reusable identifier it exposes, including:

- team ID, canonical school, abbreviation, alternate names, and aliases;
- team-season conference and home-venue relationships;
- conference ID, name, abbreviation, and classification;
- historical team-conference affiliation intervals;
- venue ID and canonical name;
- game ID, season, week, season type, start time, status, home and away team
  IDs, and venue ID;
- athlete ID and name, team-season membership, position, and recruit links;
- recruit IDs and athlete links;
- coach IDs and team-season or tenure relationships;
- drive IDs and game, offense-team, and defense-team relationships;
- play IDs and game, drive, and play-type relationships;
- play-type and play-stat-type IDs and names;
- draft-team and draft-position IDs; and
- playoff-matchup and linked game IDs.

Adding an identifier-bearing endpoint requires source-owned declarations or a
typed hook plus its typed identity-source endpoint specification in the same
change. Endpoint specs own response capability, completeness, known caps, and
hydration meaning; unrelated routes do not enter a universal registry. Normal
endpoint responses enrich the catalog opportunistically after validation;
hydration is not the only ingestion path.

The projection compiler rejects missing fact targets, conflicting
declarations, and invalid non-catalog explanations. Contract tests enforce
source ownership and prevent class-name or dumped-field dispatch from
returning. A deterministic contract digest covers endpoint capabilities,
declarations, hooks, target grains, placeholder rules, authority, presence,
and merge meaning. Coverage is valid only for the current digest. A retained
response that still validates is reprojected locally when projection metadata
changes, without spending another API call.

Entity records retain source provenance plus `first_seen_at` and
`last_seen_at`. Time-varying relationships are represented by seasons or
validity intervals instead of overwriting history. A source refresh may add or
supersede observed facts, but response expiration alone never deletes them.
Catalog facts are removed only by an explicit prune operation, user deletion,
or complete backend loss. SQLite DDL in the packaged SQL resources and Redis
keys define the version-1 layout. Future format changes may use a new namespace
or deliberate rebuild contract.

### Coverage ledger

The catalog is accompanied by a coverage ledger. Each canonical partition
records:

- entity namespace and canonical filters;
- the fact capabilities established by the response;
- complete, partial, or possibly-truncated status;
- response-cache key and source endpoint;
- fetched, validated, fresh-until, and retained-until timestamps;
- row count and any known endpoint cap;
- API, cache-key, response-contract, projector, and catalog-schema versions;
  and
- interruption or failure metadata needed for resumable hydration.

Capabilities state what a partition proves rather than merely that an endpoint
was called. Representative capabilities include `team.core_identity`,
`team.aliases`, `team.conference_history`, `game.identity`, `game.schedule`,
`game.team_relationships`, `athlete.identity`, and
`athlete.team_season`.

A partition becomes complete only after the response validates and its
response record, projected catalog facts, and coverage update commit
atomically. A capped endpoint returning exactly its maximum number of records
is marked possibly truncated unless a narrower partition proves completeness.
An interrupted or failed partition is never presented as complete.

Coverage deadlines may expire, but ledger and catalog rows remain. Expiration
means that an `ENSURE_FRESH` query should refresh the smallest partition that
provides its missing or stale capabilities; it does not mean the known
identities are forgotten.

### Identity-shaped public intent

The client adds a typed `client.identities` namespace for callers that want a
compact identity rather than an entire endpoint result. Identity methods
return validated compact models rather than pandas or Polars DataFrames and do
not construct a canonical Arrow table.

Representative operations are:

```python
team = await client.identities.teams.resolve("Michigan")
team_id = await client.identities.teams.resolve_id("Michigan")
school = await client.identities.teams.resolve_name(130)

conference = await client.identities.conferences.resolve("B1G")
venue = await client.identities.venues.resolve("Michigan Stadium")
game = await client.identities.games.resolve(game_id=401628347)

games = await client.identities.games.find(
    season=2025,
    week=1,
    team="Michigan",
)

athlete = await client.identities.athletes.resolve(
    name="Example Player",
    team="Michigan",
    season=2025,
)
```

Compact models contain only identity and relationship fields appropriate to
their declared grain. For example, `TeamIdentity` contains ID, canonical
school, abbreviation, and alternate names. Conference and home venue belong
to `TeamSeasonIdentity` when historical meaning matters. `GameIdentity`
contains the game partition and related team and venue IDs, not scores,
statistics, weather, or betting payloads.

Intent must be explicit before I/O. Python cannot infer that a caller only
wanted `frame[["id", "school"]]` until after the full endpoint result has
already been fetched and materialized. Existing endpoint methods therefore do
not acquire a dynamic `fields=` option and retain their complete-result
contract. Internal datasets and workflows express identity requirements as
typed entity, projection, selector, and coverage-capability queries and use the
same identity planner.

The planner evaluates sources in this order:

1. fresh catalog facts with sufficient coverage capabilities;
2. retained catalog facts when the requested freshness mode permits them;
3. a compatible validated exact response already retained locally;
4. the minimum-cost hydration partition capable of establishing coverage; and
5. a complete endpoint response only when the requested fields require it.

Identity reads support three freshness modes:

- `ENSURE_FRESH`, the default, refreshes missing or expired coverage and may
  fall back to retained facts under the stale policy;
- `ALLOW_STALE` returns known catalog facts without a quota-consuming refresh;
  and
- `LOCAL_ONLY` forbids network I/O and fails if local facts and coverage cannot
  answer the query.

Resolution never silently guesses. It matches, in order, an exact provider
ID, a normalized exact canonical name, an exact abbreviation, or an exact
registered alternate name. Normalization is limited to Unicode normalization,
case folding, trimming, and whitespace normalization. Multiple matches raise
an explicit ambiguity error with safe candidate summaries. Fuzzy matching is
a separate suggestion operation and never chooses a result automatically.
Entities with commonly duplicated names, especially athletes, require
disambiguating team, season, or other scope.

### Minimal-call hydration

Hydration is explicit and dependency-aware; constructing or entering a client
does not automatically spend API quota. A caller chooses seasons,
classification scope, and required identity domains. The planner inspects
coverage first and can report a dry-run call count before performing I/O.

For `S` requested seasons, the canonical identity bootstrap is:

| Identity data | Request | Calls |
| --- | --- | ---: |
| Teams | `/teams` | 1 total |
| Venues | `/venues` | 1 total |
| Conferences | `/conferences` | 1 total |
| Historical affiliations | `/conferences/affiliations` without filters | 1 total |
| Games | `/games?year=Y` | 1 per season |
| Athletes and recruit links | `/roster?year=Y` | 1 per season |
| Play types | `/plays/types` | 1 total when requested |
| Play-stat types | `/plays/stats/types` | 1 total when requested |
| Team-stat categories | `/stats/categories` | 1 total when requested |

The identity core therefore costs `4 + 2S` calls. Including the three analysis
vocabularies costs `7 + 2S`; twenty seasons cost 47 calls. The roster year is
always explicit. Player search is not an enumeration primitive because its
current upstream implementation is capped at 100 results; the broad roster is
the player-ID bootstrap source. See the versioned upstream
[players service](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/players/service.ts#L328)
and
[teams service](https://github.com/CFBD/cfb-api-v2/blob/v5.24.0/src/app/teams/service.ts#L505).

Hydration uses bounded concurrency and the same single-flight and lease path as
ordinary cache refresh. It commits each canonical partition independently so
an interrupted run is resumable. It avoids team-by-team, player-by-player, or
game-by-game fan-out when a complete season-wide source exists.

Supporting every catalog entity does not mean eagerly downloading every drive
or play for every season. Those projectors ship in the initial implementation,
but their partitions are hydrated only when requested by a workflow or learned
opportunistically from ordinary endpoint calls. This distinction provides full
catalog capability without spending quota on unused fact universes.

### Security and observability

Cache and catalog data are treated as untrusted local or remote input. Records
use explicit columns and constrained JSON, have bounded sizes, carry schema
versions, and are validated on read. SQLite files receive restrictive
permissions. Hosted Redis guidance requires TLS, scoped ACL credentials,
finite connect and socket timeouts, and redaction of URL passwords.

Instrumentation distinguishes response hits, misses, stale hits,
revalidations, refreshes, bypasses, local followers, distributed-lease waits,
backend failures, identity hits, stale identity results, hydration calls,
possibly-truncated coverage, and ambiguity. It never records tokens, response
bodies, or raw sensitive query values.

[ADR 0005](0005-client-retrieval-observability.md) defines the optional public
observer, aggregate statistics, correlation, and failure-isolation contract for
these cache decisions and the transport attempts they cause.

## Alternatives considered

### Cache complete DataFrames or Parquet as the API cache

Rejected. It would couple cache entries to pandas or Polars, exclude
model-returning endpoints, and perform unnecessary Arrow and DataFrame work for
identity queries. Parquet remains appropriate for durable workflow artifacts,
not exact HTTP response semantics or distributed refresh leases.

### Use only an exact HTTP response cache

Rejected. Exact keys cannot reuse a broad response for an identity-shaped
query and cannot answer historical relationships without redownloading and
materializing payloads. The normalized catalog and capability-aware coverage
ledger are necessary complements.

### Transparently filter broad cached responses for existing endpoints

Rejected. Several upstream queries do not promise a deterministic local sort,
and transparent superset substitution could change public row-order or filter
semantics. Explicit identity queries may use normalized catalog indexes because
their compact contract is defined by this library.

### Infer requested columns after returning a DataFrame

Rejected as impossible before the expensive work has happened. An explicit
identity-shaped query is required to select a cheaper route before network and
presentation work.

### Adopt an existing cache library directly

Rejected as the foundation after comparing the current options:

- [`requests-cache`](https://requests-cache.readthedocs.io/en/stable/) is a
  mature Requests-specific synchronous cache and does not fit the async
  `aiohttp` transport.
- [`aiohttp-client-cache`](https://aiohttp-client-cache.readthedocs.io/en/stable/)
  fits `aiohttp`, but its current beta status, pickle-oriented defaults,
  simplified HTTP semantics, and Redis hash storage do not provide the desired
  security and per-entry expiry foundation.
- [`Hishel`](https://hishel.com/overview/) has strong RFC-oriented policy and
  safe serialization, but its current integrations target HTTPX and Requests,
  not `aiohttp`; Hishel was classified as alpha when this decision was
  recorded.
- [`DiskCache`](https://grantjenks.com/docs/diskcache/) is synchronous, uses
  pickle for non-native values by default, lacks Redis, and would still require
  project-owned HTTP and async coordination policy.

A project-owned policy with `aiosqlite` and `redis.asyncio` adds implementation
responsibility, but it preserves the existing transport and gives both
backends identical validation, identity, coverage, TTL, and coordination
semantics.

### Implement only process-local coalescing initially

Rejected. Multiple processes and containers are credible initial Redis and
SQLite deployments, and duplicate misses consume the scarce resource the
cache is intended to protect. Both backends therefore ship with their real
cross-process lease implementation.

### Delete catalog facts when their source TTL expires

Rejected. Freshness answers whether coverage should be refreshed; it does not
invalidate the utility of an observed identifier. Facts and coverage remain
queryable and explicitly stale until refreshed, superseded, pruned, migrated,
or deleted.

## Completeness requirement

The caching and identity capability is not considered complete until the same
release includes:

- the exact validated-response cache and policy coordinator;
- the null, SQLite, and Redis backends;
- process-local single-flight;
- renewable SQLite and Redis cross-process leases;
- versioned safe serialization, key construction, expiry, and cleanup;
- the identity catalog and capability-aware coverage ledger;
- projectors for every identifier-bearing supported response model;
- typed identity resolution, ambiguity handling, and freshness modes;
- dry-run, resumable minimal-call hydration;
- Redis Docker, Compose, hosted-service, security, and persistence examples;
- black-box endpoint and identity tests;
- real multiprocess SQLite coordination tests and real Redis integration tests;
- corruption, cancellation, lease-expiry, stale-if-error, backend-failure,
  redaction, migration, and quota-call-count tests; and
- public documentation for configuration, defaults, identity lookup, cache
  maintenance, and operational tradeoffs.

Implementation may be split into dependency-ordered commits, but knowingly
partial backend coordination or identifier coverage is not the accepted public
capability.

## Consequences

- Most repeated endpoint requests can avoid API calls without changing public
  endpoint result semantics.
- Identity-shaped work can avoid fetching and materializing analytical payloads.
- Catalog facts remain useful after coverage freshness expires and can support
  offline or quota-sensitive resolution.
- SQLite provides a lightweight, serverless local experience; Redis provides
  shared multi-worker and multi-host behavior.
- Built-in TTLs require no routine configuration while typed overrides support
  unusual freshness requirements.
- Local and distributed single-flight prevent concurrent misses from
  multiplying quota consumption.
- Every cache hit and catalog projection remains downstream of the Pydantic
  external-data boundary.
- Response records, catalog facts, coverage, and workflow checkpoints duplicate
  some source information intentionally because their keys, lifetimes, and
  correctness responsibilities differ.
- `aiosqlite` becomes a core dependency, while Redis remains an optional extra
  with an external service requirement.
- Redis deployments that retain catalog data require deliberate persistence and
  eviction configuration; SQLite remains the simpler default on one host.
- The library owns cache schemas, migrations, leases, policy, projectors, and
  observability instead of delegating them to a third-party HTTP cache.
- Upstream ID changes, schema changes, and catalog corruption require versioned
  rebuild and reconciliation paths.
- API caching remains an optimization rather than the source of workflow
  recovery; eviction of response records cannot invalidate completed workflow
  checkpoints.
