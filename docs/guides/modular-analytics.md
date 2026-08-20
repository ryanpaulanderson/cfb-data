# Build durable analyses with modular recipes

Recipes combine validated endpoint rows into reusable analytical products. A
dataset returns one eager pandas or Polars DataFrame. A workflow returns an
immutable mapping of explicitly named DataFrames. Both are ordinary callable
objects that can be imported, composed, planned, executed durably, or authored
in another package without editing a central index.

Endpoint retrieval remains source-shaped. A recipe owns every choice to filter,
join, flatten, clean, or derive a value, so using one recipe does not impose
that policy on unrelated endpoint users.

## Install the options you need

The base installation includes pandas, canonical Arrow tables, local execution,
and durable SQLite/Parquet analytics storage:

```shell
python -m pip install cfb-data
```

Install only the additional options you intend to use:

```shell
python -m pip install "cfb-data[polars]"
python -m pip install "cfb-data[dask]"
python -m pip install "cfb-data[yaml]"
python -m pip install "cfb-data[redis]"
```

The extras can be combined. Dask executes eligible pure transform steps; source
retrieval, attempt budgets, validation, events, and durable artifact commits
remain coordinator-owned.

## Call one dataset

Import a recipe from its independent module and pass the client explicitly:

```python
import asyncio

from cfb_data import CFBDClient
from cfb_data_recipes.game_summaries import game_summaries


async def main() -> None:
    async with CFBDClient() as client:
        games = await game_summaries(
            client,
            year=2024,
            team="Penn State",
        )

    print(games[["week", "home_team", "away_team", "result_state"]])


asyncio.run(main())
```

The normal call returns the client's selected eager backend. Construct the
client with ``dataframe="polars"`` to receive a Polars DataFrame from the same
recipe and canonical table contract.

Analytics storage is lazy. The first execution resolves the platform-specific
user-data directory; endpoint-only use creates no analytics files. Set an
explicit root when a notebook or application should own the artifacts:

```python
from pathlib import Path

from cfb_data import CFBDClient
from cfb_data.analytics import AnalyticsConfig

client = CFBDClient(
    analytics=AnalyticsConfig(root=Path(".analytics")),
)
```

## Plan, inspect, and run durably

``plan()`` compiles and validates a deterministic redacted graph without
reading cache state, files, environment variables, Dask state, or the network:

```python
from cfb_data.analytics import ExecutionPolicy
from cfb_data_recipes.team_seasons import team_seasons

policy = ExecutionPolicy(
    executor="dask",
    retrieval_concurrency=4,
    max_http_attempts=20,
)

plan = await team_seasons.plan(
    client,
    season=2024,
    team="Penn State",
    policy=policy,
)

print(plan.worst_case_http_attempts)
for node in plan.nodes:
    print(node.node_id, node.placement)
```

``inspect()`` recompiles the same request and performs only non-mutating
response-cache and checkpoint lookups. Supplying the plan proves that the
validated parameters and policy still describe the inspected graph:

```python
inspection = await team_seasons.inspect(
    client,
    season=2024,
    team="Penn State",
    policy=policy,
    plan=plan,
)
```

``run()`` returns the frame plus durable evidence:

```python
run = await team_seasons.run(
    client,
    season=2024,
    team="Penn State",
    policy=policy,
)

print(run.run_id, run.actual_http_attempts, run.reused_nodes)
print(run.source_coverage)
run.artifact.export_parquet("outputs/penn-state-2024.parquet")
```

Artifact references validate content when loaded and remain usable after the
client closes:

```python
polars_frame = run.artifact.load(backend="polars")
```

Every actual HTTP attempt—including a retry—must fit the run-wide budget.
Response-cache hits consume no attempt. Dask starts lazily only when eligible,
non-reused compute is ready.

## Compose named workflow outputs

Workflows never choose a hidden primary table:

```python
from cfb_data_recipes.single_game_analysis import single_game_analysis

outputs = await single_game_analysis(client, game_id=401628515)

summary = outputs["game_summaries"]
plays = outputs["plays"]
drives = outputs["drives"]
lines = outputs["betting_lines"]
```

The one-game workflow uses a validated game summary to bind the year, week, and
team required by the historical play and drive routes. Its graph and worst-case
request count are still fixed before I/O; inspection marks those exact cache
lookups as deferred until the upstream scalar values exist.

Advanced workflow runs expose one artifact per name:

```python
run = await single_game_analysis.run(client, game_id=401628515)
run.artifacts["plays"].export_parquet("outputs/plays.parquet")
```

## Recover from a failed run

A failure raises ``CFBDRunError`` with a safe run ID and failed node identity.
Recovery creates a new immutable child run; it never edits the failed record:

```python
from cfb_data.analytics import CFBDRunError

try:
    run = await team_seasons.run(
        client,
        season=2024,
        team="Penn State",
    )
except CFBDRunError as error:
    recovered = await team_seasons.run(
        client,
        season=2024,
        team="Penn State",
        resume_from=error.run_id,
        source_behavior="preserve_snapshot",
    )
```

Use ``normal_freshness`` for a new evaluation through the current response-cache
policy, or ``refresh`` to require fresh source retrieval. A new run never
substitutes an old analytical source checkpoint for freshness evaluation.

## Use the first-party recipes

Every first-party product is one self-contained module in
``cfb_data_recipes``. The package ``__init__`` does not re-export or import
them.

| Module | Grain or outputs |
| --- | --- |
| ``game_summaries`` | One selected game. |
| ``team_games`` | One team perspective per selected game. |
| ``player_game_stats`` | One long-form athlete/stat observation. |
| ``drives`` | One game-scoped drive. |
| ``plays`` | One game-scoped historical play. |
| ``rosters`` | One athlete/team/season membership. |
| ``team_seasons`` | One records-established team season. |
| ``player_seasons`` | One roster-or-stat athlete/team/season membership. |
| ``poll_rankings`` | One team in one poll snapshot. |
| ``betting_lines`` | One provider quote per game and source ordinal. |
| ``recruiting_classes`` | One team class or uncommitted-year bucket. |
| ``coach_seasons`` | One directly attributed coach/team season. |
| ``team_season_analysis`` | Seven named team-season outputs. |
| ``single_game_analysis`` | Six named game, play, drive, player, and line outputs. |
| ``program_history`` | Six named program outputs over a bounded season range. |

Dataset-specific ``include_*`` parameters request explicit enrichments. They
default to false and cannot change the base row universe. Paid sources preserve
their access tier and fail visibly when requested but unavailable.

## Author an independent Python dataset

Authors use the same decorators and public endpoint sources as the packaged
recipes:

```python
from pydantic import BaseModel, ConfigDict, Field

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games


class CompletedGame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    game_id: int = Field(json_schema_extra={"semantic_type": "identifier"})
    season: int = Field(json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(json_schema_extra={"semantic_type": "dimension"})
    home_team: str
    away_team: str
    total_points: int


@step(id="my.completed_games.normalize", revision=1, output=CompletedGame)
def normalize_completed_games(rows: list[Game]) -> list[CompletedGame]:
    return [
        CompletedGame(
            game_id=row.id,
            season=row.season,
            week=row.week,
            home_team=row.home_team,
            away_team=row.away_team,
            total_points=row.home_points + row.away_points,
        )
        for row in rows
        if row.completed
        and row.home_points is not None
        and row.away_points is not None
    ]


@dataset(
    id="my.completed_games",
    revision=1,
    row=CompletedGame,
    grain="one completed game",
    keys=("game_id",),
    order_by=("season", "week", "game_id"),
    partition_by=("season",),
)
def completed_games(
    *,
    year: int,
    team: str | None = None,
) -> RecipeRef[list[CompletedGame]]:
    return normalize_completed_games(games(year=year, team=team))
```

Importing this module makes ``completed_games`` directly callable and
composable; there is no registration call. Stable cross-run reuse requires the
namespaced IDs and integer revisions. Bump the relevant boundary revision when
its analytical meaning changes.

Installed providers publish module or package targets through the
``cfb_data.recipes`` entry-point group. Discovery validates each trusted
provider transactionally and returns an immutable ``RecipeSnapshot``. Conflicts
fail rather than allowing import order to select a winner.

## Compose recipes safely with YAML

Install the ``yaml`` extra, obtain an explicit immutable snapshot, and load one
finite document:

```python
from pathlib import Path

from cfb_data.analytics import discover_recipes, load_recipe_yaml

snapshot = discover_recipes()
recipe = load_recipe_yaml(
    Path("penn_state_games.yaml").read_text(encoding="utf-8"),
    recipes=snapshot,
)
outputs = await recipe(client, year=2024, team="Penn State")
```

The copyable [YAML example](../../examples/analytics/penn_state_games.yaml)
wraps the exact ``cfbd.game_summaries@3`` dataset as a named workflow output.
YAML can compose exact registered sources, steps, datasets, and workflows, but
it cannot import code, evaluate expressions, expand a graph from returned rows,
or infer a dataset schema from populated data.
