# Verify calculated football metrics

Verification date: October 3, 2026. Package 0.9.0; Python 3.13.15 on macOS
Apple Silicon. This report covers Success Rate, College ALY, their shared play
features, and the reusable centered-model steps. It does not establish predictive
superiority or national-season performance.

## Correctness and execution evidence

The full `make format` and `make check` contract passed: **725 passed, 24 skipped**
in **165.81 seconds** for pytest. Hooks include strict mypy and Ruff; the strict
Sphinx build passed. CI timing data was refreshed. The skipped checks require
explicit Redis or live-API enablement; Redis was then tested separately.
The serial Redis suite passed **21 tests** in **72.97 seconds**, including both
new calculated recipes. Ruff also checked the untracked new modules and example
directly, and hooks passed again after timing-data normalization.
Python 3.12 was not executed in this worktree. New code uses the supported
3.12 language/API contract; the existing CI matrix remains authoritative for
cross-version execution.

Black-box tests enter through installed public recipes and a deterministic HTTP
boundary. They verify:

- 50/70/100 threshold arithmetic, interceptions and confirmed lost fumbles,
  unknown own recoveries, safety/uncategorized-touchdown origins, exclusions,
  and pooled season denominators.
- Global duplicate, participant and field-state failures before publication;
  absent populations retain null rates and explicit coverage.
- Joint ALY coefficients, normalization, and game-cluster sandwich standard
  errors against an independently assembled constrained matrix, with both
  uniform weights and a 28-day half-life.
- Forward-week candidate MSE against independently fitted earlier-week models;
  the output-only team selector retains the full fitting population.
- No validation evidence selects no model; excluded/absent rushing populations
  retain observed evidence and null adjusted ratings.
- Fresh local and Dask dataset execution at the same semantic revision, with
  pandas/Polars presentation parity. Play/design rows cross partition boundaries.
- Reusable model steps reject cross-partition response conflicts, duplicate or
  missing design blocks, and coefficient-bound overruns.
- Owned pandas tables copy input relations, compose natively, enforce global
  checks and explicit collection bounds, and preserve nested records during
  concurrent construction.

Native acceptance exposed two engine issues. Named Dask reductions retained
intermediate MultiIndex shuffle metadata, breaking downstream joins; the shared
aggregation boundary now invalidates that stale metadata without gathering
rows. Separately lowered disk-shuffle graphs reused expression keys with fresh
resource dependencies; native lowering now chooses deterministic task shuffles.
Overlapping Dask configuration scopes also allowed nested object records to
become strings. A shared lock protects brief construction/lowering scopes and
restores caller settings, while computation stays partitioned and parallel.
The fresh Dask parity test checks that task-key collision warnings do not recur.

## Persistent Redis acceptance

A repository-owned Redis server listened on `127.0.0.1:6382`, with AOF and RDB
files under `.cache/redis`. Tests used isolated namespaces and removed only
their own keys. Both recipes reran with `checkpoint_mode="off"`; the warm run
required `local_only` source-cache mode.

On the 24-play independent-math fixture, the initial sequence made three local
HTTP calls (games and two play weeks); warm reexecution made zero calls. Both
sequences reused zero analytics nodes. ALY artifact digests matched exactly.
The measured combined times were 33.19 seconds cold and 31.07 seconds warm;
these overlap another acceptance run and are cache-correctness evidence rather
than an isolated performance comparison.

No live CFBD requests were made: `CFBD_API_KEY` was unavailable in this worktree.
The HTTP payloads were fixtures; Redis, persistence, Dask workers, and public
recipe execution were real. Live source profiling remains unverified.

## Larger native profile

An isolated synthetic sample contained eight games over two weeks, **960 raw
plays** and **640 evaluated rushes**, with regulation clocks, rushing/dropback
splits, multiple downs and distances, both venue perspectives, and four teams.
The public workflows ran with two Dask worker processes, one thread each,
256-row initial partitions, and checkpoints disabled. ALY used explicit
penalties `(16, 64)` and a 28-day half-life. This is a representative kernel
exercise, not a full-season or automatic-search benchmark.

The profiler wrapped only the external distributed-client construction to
enable its real TaskStream diagnostics and read worker RSS high-water marks
before shutdown. Its task buffer retained up to 100,000 events. HTTP, Redis,
sources, transformations, validation and publication used their normal paths.

| Sequence | Recipe | Seconds | HTTP attempts | Native encoded partition tasks | Recorded Dask tasks | Shuffle tasks | Worker peak RSS (MiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial | Success Rate | 14.79 | 3 | 10 | 7,514 | 319 | 232.58 |
| Initial | ALY | 30.12 | 0 | 70 | 22,021 | 4,934 | 256.98 |
| Warm | Success Rate | 13.70 | 0 | 9 | 6,603 | 160 | 220.16 |
| Warm | ALY | 31.76 | 0 | 70 | 22,026 | 4,934 | 249.91 |

ALY in the initial sequence already reused the responses warmed by Success
Rate. Both warm workflows required cached responses, recomputed every node,
and made zero HTTP calls. Across all four runs, only three fixture calls occurred.
Warm and initial final tables agreed at `rtol=atol=1e-10`, with exact identity,
population, exclusion and null semantics.

| Sequence / recipe | Encoded rows across native step publications | Arrow result bytes | Validation + Arrow encoding time | TaskStream transfer time | Shuffle result bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial / Success Rate | 2,088 | 586,862 | 0.101 s | 1.008 s | 27,241,058 |
| Initial / ALY | 15,517 | 1,788,546 | 0.479 s | 2.898 s | 112,779,917 |
| Warm / Success Rate | 2,088 | 586,862 | 0.093 s | 1.074 s | 9,817,180 |
| Warm / ALY | 15,517 | 1,788,544 | 0.375 s | 3.100 s | 112,736,164 |

Encoded-row totals include intermediate publications; they are not unique source
rows. Encoding time includes partition validation and Arrow conversion, not
only network serialization. Shuffle result bytes sum the TaskStream-reported
in-memory sizes of shuffle task results; they are a workload proxy, not wire
bytes. Transfer times sum task intervals and may overlap. Arrow byte totals
can vary with physical partition/null-bitmap boundaries while table meaning
remains identical. Coordinator cumulative peak RSS rose from 330.48 MiB after
the first run to 496.59 MiB after the last; this includes retained diagnostic
events and is not a per-recipe incremental memory estimate.

The final products had 960 play rows, 96 Success Rate team/game/split rows,
24 Success Rate season rows, 27 ALY coefficients, and eight ALY team/unit
ratings. Native intermediate and encoding tasks ran on worker processes;
coefficient fitting collected only bounded reduced equations on the
coordinator. Startup, repeated validation, publication, and graph scheduling
dominate this sample. These measurements support actual partitioned execution
and response-cache reuse; they do not support a speedup or season-scale memory
claim.
