# Native table migration verification

The testing branch `refactor/native-dask-recipes` starts at fresh main
`9af6f12493aca6caeb6dbe8dfaaf55927e8691f2`. The proposed beta version is
0.9.0. The engine, recipe migration, and documentation are organized as related
review commits; no package release has been made.

All thirteen dataset transforms and three workflows use `Table` references and
native dataframe operations. HTTP validation and the capped play-stat source's
bounded request-control loops remain coordinator responsibilities. The original
[audit](recipe-dask-reengineering-audit.md) is a historical inventory;
[ADR 0007](0007-native-table-execution.md) describes the implemented contract.

## Correctness and execution

The acceptance suite covers source/final validation, cross-partition duplicate
keys, coverage and conflicts, source ordinals, group ordinals across partitions,
empty and nullable frames, backend/executor parity, immutable scans and batches,
late-partition failure without dataset publication, recovery, and cancellation.
Partition events verify work on two separate worker processes. Native computation
uses bounded future windows and global count summaries. Checks are deduplicated
when branches reconverge; coverage reductions use original base-key relations
instead of previously enriched payloads. Empty sources retain physical/schema
validation while avoiding joins proven to have no observations.

Native global reductions and output partitions lower directly to Dask tasks.
This avoids pathological repeated dataframe fusion in overlapping validation
graphs; it preserves the complete joins, groups, checks, and global ordering.
Source scans use declared empty metadata and canonical artifact parts rather
than sampling data or sending whole dataframe inputs to workers.

Final `make format` and `make check` passed: 684 tests passed and 23 opt-in
Redis/live tests were skipped by default. Linting, strict typing, and the
warning-free documentation build passed. A further native cancellation
regression passed in 2.34 seconds after real partition execution, proving
cleanup and no dataset publication. The previous package-version test failure
was corrected by deriving its expected version from `pyproject.toml`.
Twenty separately enabled Redis integration tests passed. Python 3.13.15,
Dask/distributed 2026.8.0, pandas 3.0.6, and Polars 1.44.2 were
used locally. Python 3.12 was unavailable on this host and remains part of
the unchanged CI matrix. The wheel and source distribution built successfully
and passed `twine check --strict`. An isolated base-wheel installation passed
imports and native two-partition collection with neither distributed nor
Polars installed. CI now accounts for PyYAML being a core Dask dependency.

## CI correction and default-suite runtime

The initial Python 3.12 and 3.13 CI suites failed with `node_lease_lost` after
969.02 and 1009.66 seconds of pytest execution. Each deferred validation check
lowered its overlapping dataframe graph separately. Native distributed graph
preparation and submission also ran synchronously on the coordinator loop,
preventing timely checkpoint-lease renewal.

Validation now lowers one shared graph and reuses equivalent physical
summaries, retaining each contract's declaration order and failure message.
Native graph preparation and submission run off the event loop. Cancellation
drains owned preparation and cancels any futures created during submission.
A small sorting fixture reproduces lease loss against the original engine
and passes with the correction, using real distributed workers and a short
publication lease.

Default tests use two isolated pytest workers. Dataset parity retains fresh
local and Dask computation in separate stores and replays their compatible
checkpoints for Polars presentation. Workflow parity verifies portability
without repeating already-covered dataset computation. HTTP and worker
cancellation fixtures use explicit release handshakes instead of long sleeps.
The external-provider fixture clones its installed environment offline before
installing a plugin, so parallel tests cannot modify a shared installation.
Quota-ledgered live targets remain serial; no additional live API calls were
needed for this repair.

On the same Python 3.13 host, an intermediate sequential suite passed 689 tests
with 23 opt-in skips in 178.19 seconds. After the engine and fixture changes,
the bounded parallel suite passed all 689 tests with the same 23 skips in
74.82 seconds. The complete `make check`, including lint, strict typing, and
warning-free documentation, took 81.77 seconds. These are measured local
durations; supported-version CI results are verified separately on the PR.

The repaired unsplit CI suites passed on Python 3.12 in 266.95 seconds and
Python 3.13 in 251.09 seconds. Those remote durations remain above the
one-to-two-minute target despite the faster local result.

CI now runs three duration-balanced groups per supported Python version with
the same two-worker runner. Measured setup, execution, and teardown timings
are checked in for all 721 collected cases; unknown tests receive an average
duration and remain included. Collection verification proves the groups are
disjoint and their union equals the complete suite. Both existing required
Python-version checks fail if any supported-version group fails or is cancelled.
The full local suite with the splitter installed passed 698 tests with 23
opt-in skips in 74.32 seconds. Remote group timings must be measured separately.

The first grouped remote run took 63.00, 97.46, and 116.90 seconds on Python
3.12 and 59.85, 55.37, and 104.72 seconds on Python 3.13. One Python 3.13 group
exposed an existing cancellation fixture that assumed its worker had started
after a 10-millisecond sleep. The fixture now waits for an explicit worker-start
handshake and releases the worker during cleanup. Both required version checks
correctly failed when that group failed; a complete rerun verifies the correction.

## Review regressions

Source recovery now retains coverage warnings while validating reused snapshots
in bounded batches. A reusable source carrying a warning preserves that
warning in the public result after recovery. Explicitly partial sources remain
ineligible for checkpoint reuse, including those whose reason is unknown;
their public coverage remains partial even without a warning. HTTP-boundary
regressions fail against the original engine and pass with the correction.

Nested record ordering accepts native integral values, including signed and
unsigned NumPy integers. pandas and multipartition Dask regressions reproduce
the previous rejection and verify deterministic ordering. Booleans, floats,
strings, and missing ordinals remain invalid. The full corrected local suite
passed 698 tests with 23 opt-in skips in 75.26 seconds.

## Redis-backed live evidence

The bounded live recipe acceptance test passed in 103.98 seconds. Its persistent
Redis namespace is `cfb-data:penn-state-atlas`; no cache flush was performed.
The cumulative ledger increased from 655 to 668: thirteen HTTP attempts.
All four cached pandas/Polars by local/Dask replays used zero HTTP attempts.
The test reported no warnings or skips and checked checkpoint reuse, recovery,
and explicit freshness behavior.

This live matrix covers team seasons, single-game analysis, and one-year program
history, together covering ten dataset products. Rosters, player seasons, and
capped play-player statistics have deterministic acceptance coverage; they were
not part of this live matrix. Paid optional enrichments are covered by fixture
validation and parity rather than this live request set.

## Measured grouping overhead

The generated fixture measures identical grouped count/sum results with a Python
dictionary-loop reference, the local native scheduler, and two distributed
workers. Each native graph has eight partitions. Timings exclude input creation,
HTTP, artifact IO, Pydantic validation/encoding, and worker startup. Memory is
profiled in a separate repetition to avoid biasing Python-loop timings. These
single-run numbers characterize this shared operation, not complete recipes.

| Input rows | Python loop (ms) | Local native (ms) | Distributed native (ms) |
| --- | ---: | ---: | ---: |
| 128 | 0.03 | 11.95 | 60.14 |
| 100,000 | 4.30 | 11.06 | 52.09 |
| 1,000,000 | 50.71 | 27.75 | 65.89 |
| 1,000,000 (95% in one group) | 41.23 | 24.82 | 66.41 |

Worker startup took 0.69 seconds. Local native
grouping improved this million-row fixture; distributed scheduling/transfer
added overhead and did not outperform the reference at these volumes. No
blanket recipe speedup or distributed scaling claim is made.

The million-row input occupies approximately 15.3 MiB. Coordinator traced
incremental peaks were about 40 MiB for native processing versus less than
0.3 MiB for the reference dictionary, excluding their prebuilt inputs. Worker
RSS snapshots totaled approximately 376–377 MiB and are not peak measurements.
The synthetic in-memory submission emitted Dask large-graph warnings
(15–31 MiB); production source scans instead submit artifact-reading tasks.

The fixture runner and raw redacted reports are retained in the ignored
repository-local `.cache` directory. Further measurements must include full
source validation, skewed nested payloads, artifact IO, transfer volume, and
worker peaks before claiming end-to-end performance gains.
