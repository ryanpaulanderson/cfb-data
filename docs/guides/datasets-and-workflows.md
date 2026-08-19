# Build durable datasets and workflows

The analytics layer combines validated endpoint results into tables with an
explicit row grain, candidate key, ordering, quality checks, and lineage. It
uses the same eager pandas or Polars backend selected for the client.

## Use a curated dataset

```python
from cfb_data import CFBDClient

async with CFBDClient() as client:
    games = await client.datasets.game_summaries(
        year=2024,
        team="Penn State",
    )
```

The direct method returns a DataFrame. Use `run()` when the analysis needs its
artifact, quality evidence, coverage, or run ID:

```python
from cfb_data import ExecutionPolicy

async with CFBDClient() as client:
    plan = await client.datasets.plan(
        "cfbd.team_seasons",
        params={"season": 2024, "team": "Penn State"},
    )
    print(plan.logical_source_requests, plan.worst_case_http_attempts)

    run = await client.datasets.run(
        "cfbd.team_seasons",
        params={"season": 2024, "team": "Penn State"},
        policy=ExecutionPolicy(max_http_attempts=40),
    )

run.artifact.export_parquet("team-seasons.parquet")
```

Planning does not make HTTP calls or create the artifact store. The conservative
attempt estimate includes transport retries. At execution time, exact response-
cache hits consume no attempt budget.

The scheduler runs independent retrievals concurrently, with four in flight by
default, and deduplicates exact source requests across all child datasets in a
workflow snapshot. One run-wide semaphore prevents child datasets from
multiplying that limit. Pure synchronous Python or pandas computation, table
validation, Parquet publication, and artifact consolidation run outside the
event-loop thread. Compute is serial by default; use `ExecutionPolicy` to select
another bounded value when transforms are known to benefit from it.

## Run named workflow outputs

Workflows never choose an arbitrary main table:

```python
async with CFBDClient() as client:
    outputs = await client.workflows.single_game_analysis(game_id=401628515)

summary = outputs["game_summaries"]
plays = outputs["plays"]
lines = outputs["betting_lines"]
```

The initial workflows are:

| Workflow | Default named outputs |
| --- | --- |
| `team_season_analysis` | game summaries, team games, player-game stats, rosters, team seasons, player seasons, coach seasons |
| `single_game_analysis` | game summary, two team perspectives, player-game stats, drives, plays, betting lines |
| `program_history` | game summaries, team games, team seasons, recruiting classes, coach seasons, poll rankings |

`program_history` always exposes its preflight cost. Raise the policy budget
explicitly when a requested range cannot fit under the default 100-attempt hard
limit.

## Understand freshness and recovery

Successful nodes are checkpointed by default. A new run still executes source
nodes through normal cache freshness; it does not substitute an old analytical
snapshot. Deterministic transformations may reuse output when their source
content and complete node fingerprint are unchanged.

If a run fails, the next compatible simple run creates a child and preserves
validated source checkpoints. Advanced code may choose the parent explicitly:

```python
recovered = await client.datasets.run(
    "my_project.cleaned_games",
    params={"year": 2024},
    resume_from=failed_run_id,
)
```

Changing one transform revision invalidates that node and its descendants, not
unrelated ancestors. Run errors expose only a run ID, node ID, and bounded
failure category; inspect the original chained cause in a trusted development
environment when detailed debugging is appropriate.

`ExecutionPolicy(checkpoint=CheckpointMode.outputs_only)` keeps only declared
outputs. `CheckpointMode.off` still publishes the immutable output required by
`DatasetRun` or `WorkflowRun`, but gives it a run-local fingerprint: neither
that output nor an intermediate step is eligible for checkpoint reuse.

## Inspect and retain artifacts

Artifacts are immutable and have no TTL. Paths inside the store are opaque.

```python
descriptors = await client.datasets.list_artifacts(limit=25)
descriptor = await client.datasets.inspect_artifact(descriptors[0].artifact_id)
await client.datasets.pin_artifact(descriptor.artifact_id)

candidates = await client.datasets.prune_artifacts(dry_run=True)
removed = await client.datasets.cleanup_orphans()
```

Pinned and run-referenced artifacts cannot be pruned. `ArtifactRef` remains
usable after the client closes and can load a validated pandas or Polars frame
or export consolidated Parquet even when the internal table has several parts.

## Curated table catalog

| Dataset | One row / candidate key |
| --- | --- |
| `game_summaries` | game / `id` |
| `team_games` | team perspective in a game / `(game_id, team_id)` |
| `player_game_stats` | athlete display statistic / `(game_id, team_id, athlete_id, category, stat_type)` |
| `drives` | game-scoped drive / `(game_id, id)` |
| `plays` | game-scoped play / `(game_id, id)` |
| `rosters` | athlete-team-season membership / `(season, team, id)` |
| `team_seasons` | record-established team season / `(year, team_id)` |
| `player_seasons` | roster/stat-union membership / `(season, team, athlete_id)` |
| `poll_rankings` | team in a poll snapshot / `(season, season_type, week, poll, team_id)` |
| `betting_lines` | provider quote / `(game_id, provider, source_ordinal)` |
| `recruiting_classes` | source team class / `(class_year, source_team)` |
| `coach_seasons` | coach-team-season attribution / `(coach, team, year)` |

Scores and derived results remain null until a game is completed and both
scores are present. Player stat displays such as `7/9` remain strings. Betting
lines preserve every provider and do not invent a preferred or closing quote.
Optional enrichment never changes the declared base row universe.

## Extend with trusted Python

A custom definition supplies strict Pydantic parameters, a `TableContract`,
registered source nodes, and versioned registered transforms. The transform
revision is mandatory; notebook source inspection is not a durable identity.
The copyable [trusted Python definition](../../examples/analytics/custom_dataset.py)
builds a completed-games table with one registered source and a pure portable
filter. It is ordinary Python and can be pasted into notebook cells without a
notebook runtime dependency.

Custom callables receive validated inputs, validated parameters, and immutable
configuration. They do not receive the client and cannot perform engine-owned
network fan-out.

## Load safe YAML definitions

Install the optional parser only when YAML definitions are needed:

```shell
python -m pip install "cfb-data[yaml]"
```

```python
from pathlib import Path

from cfb_data import AnalyticsConfig, DatasetCatalog, load_yaml_definition

definition = load_yaml_definition(Path("examples/analytics/game_summaries.yaml"))
analytics = AnalyticsConfig(
    catalog=DatasetCatalog({definition.id: definition}),
)
```

YAML is a finite declarative graph, not a code execution surface. It accepts
registered sources and operations and explicit schemas. Imports, Python paths,
expressions, templates, environment substitution, aliases, custom tags, and
arbitrary fan-out are rejected.

The complete [YAML definition](../../examples/analytics/game_summaries.yaml)
uses a registered source contract; transformed YAML outputs declare their full
ordered row schema explicitly.

YAML and Python `WorkflowDefinition` objects are executable through
`client.workflows.plan()` and `client.workflows.run()` as well as the three
curated workflow methods. Their output names, artifacts, quality outcomes, and
source coverage are preserved in immutable mappings.

## Observe work

`AnalyticsStats` counts runs, steps, reused checkpoints, committed bytes, and
rows without retaining data:

```python
from cfb_data import AnalyticsConfig, AnalyticsStats, CFBDClient

stats = AnalyticsStats()
async with CFBDClient(analytics=AnalyticsConfig(observer=stats)) as client:
    await client.datasets.game_summaries(year=2024)

print(stats.snapshot())
```

Use the normal retrieval observer at the same time for cache and HTTP-attempt
evidence. Retrieval start and finish events carry safe analytics run and step
correlation IDs.
