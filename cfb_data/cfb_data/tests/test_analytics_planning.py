"""Black-box tests for pure recipe planning and read-only inspection."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    ExecutionPolicy,
    RecipePlan,
    RecipeRef,
    dataset,
    step,
    workflow,
)
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games
from pydantic import BaseModel, ConfigDict

from cfb_data import CFBDClient, RetryPolicy, SQLiteCacheConfig

ServerFactory = Callable[[Callable[[web.Request], object]], object]


class _StaticRow(BaseModel):
    """Represent one deterministic no-source inspection row."""

    model_config = ConfigDict(extra="forbid")

    value: int


@dataset(
    id="tests.planned_games",
    revision=1,
    row=Game,
    grain="one game",
    keys=("id",),
    order_by=("season", "week", "id"),
)
def _planned_games(year: int, team: str | None = None) -> RecipeRef[list[Game]]:
    """Build one source-faithful dataset for planner tests."""
    return games(year=year, team=team)


@step(id="tests.static_inspection_step", revision=1, output=_StaticRow)
def _static_rows() -> list[_StaticRow]:
    """Return one deterministic row without an upstream source."""
    return [_StaticRow(value=1)]


@dataset(
    id="tests.static_inspection_dataset",
    revision=1,
    row=_StaticRow,
    grain="one static row",
    keys=("value",),
)
def _static_dataset() -> RecipeRef[list[_StaticRow]]:
    """Build one dependency-free checkpoint inspection fixture."""
    return _static_rows()


@pytest.mark.asyncio
async def test_plan_is_state_independent_and_creates_no_files(tmp_path: Path) -> None:
    """Compile and budget without resolving configured storage paths."""
    artifact_root = tmp_path / "analytics-does-not-exist"
    cache_path = tmp_path / "cache-does-not-exist.sqlite3"
    client = CFBDClient(
        "planning-key",
        retry_policy=RetryPolicy(max_attempts=2),
        cache=SQLiteCacheConfig(path=cache_path),
        analytics=AnalyticsConfig(root=artifact_root),
    )

    plan = await _planned_games.plan(client, year=2024, team="Penn State")

    assert isinstance(plan, RecipePlan)
    assert plan.recipe_id == "tests.planned_games"
    assert plan.graph_fingerprint
    assert plan.outputs == ("value",)
    assert [node.kind for node in plan.nodes] == ["source", "dataset"]
    assert plan.worst_case_http_attempts == 2
    assert not cache_path.exists()
    assert not artifact_root.exists()


@pytest.mark.asyncio
async def test_plan_redacts_selector_values_and_places_only_compute_on_dask() -> None:
    """Expose shape and placement without storing raw analytical selectors."""
    client = CFBDClient("planning-key")
    plan = await _planned_games.plan(
        client,
        year=2024,
        team="private-team-selector",
        policy=ExecutionPolicy(executor="dask"),
    )

    rendered = repr(plan)
    assert "private-team-selector" not in rendered
    assert all(node.placement == "coordinator" for node in plan.nodes)
    assert plan.nodes[0].parameter_names == (
        "year",
        "week",
        "season_type",
        "team",
        "home",
        "away",
        "conference",
        "classification",
        "game_id",
        "competition",
        "round",
    )


@pytest.mark.asyncio
async def test_plan_rejects_retry_inclusive_attempts_above_policy() -> None:
    """Fail preflight before I/O when worst-case transport attempts exceed policy."""
    client = CFBDClient("planning-key", retry_policy=RetryPolicy(max_attempts=3))

    with pytest.raises(CFBDRecipeCompilationError, match="HTTP attempts"):
        await _planned_games.plan(
            client,
            year=2024,
            policy=ExecutionPolicy(max_http_attempts=2),
        )


@pytest.mark.asyncio
async def test_plan_counts_identical_source_requests_once() -> None:
    """Match runtime request deduplication in retry-inclusive preflight cost."""

    @workflow(id="tests.planned_deduplicated_games", revision=1)
    def planned_deduplicated_games() -> dict[str, RecipeRef[list[Game]]]:
        return {
            "first": games.as_("first")(year=2024, team="Penn State"),
            "second": games.as_("second")(year=2024, team="Penn State"),
        }

    client = CFBDClient("planning-key", retry_policy=RetryPolicy(max_attempts=3))

    plan = await planned_deduplicated_games.plan(client)

    assert plan.worst_case_http_attempts == 3


@pytest.mark.asyncio
async def test_plan_expands_recompute_through_dependency_descendants() -> None:
    """Expose forced execution for a selected node and every downstream node."""
    client = CFBDClient("planning-key")
    baseline = await _planned_games.plan(client, year=2024, team="Penn State")
    source_id = baseline.nodes[0].node_id

    forced = await _planned_games.plan(
        client,
        year=2024,
        team="Penn State",
        policy=ExecutionPolicy(recompute_nodes=(source_id,)),
    )

    assert all(node.recompute for node in forced.nodes)


@pytest.mark.asyncio
async def test_plan_rejects_an_unknown_recompute_node_before_io(
    tmp_path: Path,
) -> None:
    """Require expert recompute controls to reference the exact compiled plan."""
    root = tmp_path / "analytics"
    client = CFBDClient(
        "planning-key",
        analytics=AnalyticsConfig(root=root),
    )

    with pytest.raises(CFBDRecipeCompilationError, match="unknown recompute"):
        await _planned_games.plan(
            client,
            year=2024,
            team="Penn State",
            policy=ExecutionPolicy(recompute_nodes=("missing-node",)),
        )

    assert not root.exists()


@pytest.mark.asyncio
async def test_inspection_reads_an_exact_cached_source_without_mutation(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Report exact fresh coverage while preserving database bytes and mtime."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        assert request.path == "/games"
        return web.json_response([game_response])

    cache_path = tmp_path / "cache.sqlite3"
    artifact_root = tmp_path / "analytics"
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "inspection-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            cache=SQLiteCacheConfig(path=cache_path),
            analytics=AnalyticsConfig(root=artifact_root),
        ) as client:
            await client.games.list(year=2024, team="Penn State")
            plan = await _planned_games.plan(client, year=2024, team="Penn State")
            before_bytes = cache_path.read_bytes()
            before_mtime = cache_path.stat().st_mtime_ns

            inspection = await _planned_games.inspect(
                client,
                year=2024,
                team="Penn State",
                plan=plan,
            )

            assert tuple(inspection.source_dispositions.values()) == ("fresh",)
            assert tuple(inspection.checkpoint_dispositions.values()) == (
                "disabled",
                "missing",
            )
            assert cache_path.read_bytes() == before_bytes
            assert cache_path.stat().st_mtime_ns == before_mtime
            assert not artifact_root.exists()
    assert calls == 1


@pytest.mark.asyncio
async def test_inspection_rejects_a_plan_for_different_parameters_before_lookup(
    tmp_path: Path,
) -> None:
    """Require plan and validated parameter identity to agree before store reads."""
    cache_path = tmp_path / "cache.sqlite3"
    client = CFBDClient(
        "inspection-key",
        cache=SQLiteCacheConfig(path=cache_path),
    )
    plan = await _planned_games.plan(client, year=2024, team="Penn State")

    with pytest.raises(CFBDRecipeCompilationError, match="does not match"):
        await _planned_games.inspect(
            client,
            year=2024,
            team="Ohio State",
            plan=plan,
        )
    assert not cache_path.exists()


@pytest.mark.asyncio
async def test_inspection_validates_reusable_checkpoint_without_mutation(
    tmp_path: Path,
) -> None:
    """Distinguish reusable and deferred nodes while preserving store bytes."""
    root = tmp_path / "analytics"
    config = AnalyticsConfig(root=root)
    async with CFBDClient("inspection-key", analytics=config) as client:
        await _static_dataset.run(client)
        before = {
            path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path.is_file()
        }

        inspection = await _static_dataset.inspect(client)

        after = {
            path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path.is_file()
        }

    assert tuple(inspection.checkpoint_dispositions.values()) == (
        "reusable",
        "deferred",
    )
    assert after == before


@pytest.mark.asyncio
async def test_inspection_reports_corrupt_checkpoint_without_repair(
    tmp_path: Path,
) -> None:
    """Fail closed in preflight without deleting or replacing invalid content."""
    root = tmp_path / "analytics"
    async with CFBDClient(
        "inspection-key",
        analytics=AnalyticsConfig(root=root),
    ) as client:
        run = await _static_dataset.run(client)
        step_id = (await _static_dataset.plan(client)).nodes[0].node_id
        digest = next(
            evidence.content_digest
            for evidence in run.lineage
            if evidence.node_id == step_id
        )
        manifest = root / "objects" / "sha256" / digest[:2] / digest / "manifest.json"
        manifest.write_bytes(b"{}")
        before_mtime = manifest.stat().st_mtime_ns

        inspection = await _static_dataset.inspect(client)

    assert inspection.checkpoint_dispositions[step_id] == "corrupt"
    assert manifest.read_bytes() == b"{}"
    assert manifest.stat().st_mtime_ns == before_mtime
