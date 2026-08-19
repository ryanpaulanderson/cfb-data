"""Test bounded coordinator-owned asynchronous recipe sources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsStats, RecipeRef, workflow
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.analytics._graph import _CompiledGraph, _CompiledNode
from cfb_data.analytics._observability import _AnalyticsDispatcher
from cfb_data.analytics._persistence import _ArtifactObjectStore, _RunDatabase
from cfb_data.analytics._sources import _SourceRunner
from cfb_data.analytics.observability import AnalyticsEventType
from cfb_data.analytics.operations import value
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games

from cfb_data import CFBDClient, CFBDHTTPError, RetryPolicy

type _ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _source_nodes(graph: _CompiledGraph) -> tuple[_CompiledNode, ...]:
    return tuple(node for node in graph.nodes if node.kind == "source")


def _run(
    database: _RunDatabase,
    *,
    credential_scope: str,
    parent_run_id: str | None = None,
    max_http_attempts: int = 10,
) -> str:
    run = database.create_run(
        recipe_id="cfbd.source_test",
        recipe_revision=1,
        recipe_kind="workflow",
        parameter_fingerprint="a" * 64,
        graph_fingerprint="b" * 64,
        credential_scope=credential_scope,
        max_http_attempts=max_http_attempts,
        parent_run_id=parent_run_id,
        source_behavior=(
            "preserve_snapshot" if parent_run_id is not None else "normal_freshness"
        ),
    )
    database.transition_run(run.run_id, "running")
    return run.run_id


def _runner[FrameT](
    client: CFBDClient[FrameT],
    database: _RunDatabase,
    store: _ArtifactObjectStore,
    *,
    run_id: str,
    parent_run_id: str | None = None,
    concurrency: int = 4,
    stats: AnalyticsStats | None = None,
) -> _SourceRunner:
    bridge = client._analytics_bridge()
    return _SourceRunner(
        endpoint_executor=bridge.executor,
        database=database,
        object_store=store,
        run_id=run_id,
        credential_scope=bridge.credential_scope,
        parent_run_id=parent_run_id,
        source_behavior=(
            "preserve_snapshot" if parent_run_id is not None else "normal_freshness"
        ),
        concurrency=concurrency,
        dispatcher=_AnalyticsDispatcher(stats),
    )


@pytest.mark.asyncio
async def test_independent_sources_overlap_under_exact_limit(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    active = 0
    maximum_active = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return web.json_response([game_response])

    @workflow(id="tests.parallel_sources", revision=1)
    def parallel_sources() -> dict[str, RecipeRef[list[Game]]]:
        return {
            "first": games.as_("first")(year=2024, team="Penn State"),
            "second": games.as_("second")(year=2024, team="Ohio State"),
            "third": games.as_("third")(year=2024, team="Michigan"),
        }

    graph = _compile_recipe(parallel_sources, (), {})
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        async with api_server(handler) as base_url:
            async with CFBDClient(
                "key",
                base_url=base_url,
                retry_policy=RetryPolicy(max_attempts=1),
            ) as client:
                bridge = client._analytics_bridge()
                run_id = _run(database, credential_scope=bridge.credential_scope)
                results = await _runner(
                    client,
                    database,
                    store,
                    run_id=run_id,
                    concurrency=2,
                ).run_batch(_source_nodes(graph), {})

        assert len(results) == 3
        assert maximum_active == 2
        assert database.attempt_count(run_id) == 3
        assert len(database.bindings(run_id)) == 3
    finally:
        database.close()


@pytest.mark.asyncio
async def test_identical_source_requests_share_one_transport(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    dispatches = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal dispatches
        dispatches += 1
        await asyncio.sleep(0.01)
        return web.json_response([game_response])

    @workflow(id="tests.deduplicated_sources", revision=1)
    def deduplicated_sources() -> dict[str, RecipeRef[list[Game]]]:
        return {
            "first": games.as_("first")(year=2024, team="Penn State"),
            "second": games.as_("second")(year=2024, team="Penn State"),
        }

    graph = _compile_recipe(deduplicated_sources, (), {})
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        async with api_server(handler) as base_url:
            async with CFBDClient(
                "key",
                base_url=base_url,
                retry_policy=RetryPolicy(max_attempts=1),
            ) as client:
                bridge = client._analytics_bridge()
                run_id = _run(database, credential_scope=bridge.credential_scope)
                results = await _runner(
                    client,
                    database,
                    store,
                    run_id=run_id,
                ).run_batch(_source_nodes(graph), {})

        assert len(results) == 2
        assert dispatches == 1
        assert database.attempt_count(run_id) == 1
        assert len({result.artifact.content_digest for result in results.values()}) == 1
    finally:
        database.close()


@pytest.mark.asyncio
async def test_late_bound_source_uses_validated_upstream_scalar(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    queries: list[dict[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        queries.append(dict(request.query))
        return web.json_response([game_response])

    @workflow(id="tests.late_bound_source", revision=1)
    def late_bound_source() -> dict[str, RecipeRef[list[Game]]]:
        context = games.as_("context")(game_id=401628347)
        containing_year = games.as_("year").bind(
            year=value(context, path=(0, "season"), expected_type=int)
        )
        return {"context": context, "year": containing_year}

    graph = _compile_recipe(late_bound_source, (), {})
    nodes = _source_nodes(graph)
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        async with api_server(handler) as base_url:
            async with CFBDClient(
                "key",
                base_url=base_url,
                retry_policy=RetryPolicy(max_attempts=1),
            ) as client:
                bridge = client._analytics_bridge()
                run_id = _run(database, credential_scope=bridge.credential_scope)
                runner = _runner(client, database, store, run_id=run_id)
                first = await runner.run_batch((nodes[0],), {})
                second = await runner.run_batch((nodes[1],), first)

        assert len(second) == 1
        assert queries[0] == {"id": "401628347"}
        assert queries[1] == {"year": "2024"}
    finally:
        database.close()


@pytest.mark.asyncio
async def test_preserved_recovery_reuses_source_without_transport(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    dispatches = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal dispatches
        dispatches += 1
        return web.json_response([game_response])

    @workflow(id="tests.recovered_source", revision=1)
    def recovered_source() -> dict[str, RecipeRef[list[Game]]]:
        return {"games": games(year=2024, team="Penn State")}

    graph = _compile_recipe(recovered_source, (), {})
    nodes = _source_nodes(graph)
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    stats = AnalyticsStats()
    try:
        async with api_server(handler) as base_url:
            async with CFBDClient(
                "key",
                base_url=base_url,
                retry_policy=RetryPolicy(max_attempts=1),
            ) as client:
                bridge = client._analytics_bridge()
                parent = _run(database, credential_scope=bridge.credential_scope)
                await _runner(
                    client,
                    database,
                    store,
                    run_id=parent,
                ).run_batch(nodes, {})
                database.transition_run(parent, "failed", node_id="downstream")
                child = _run(
                    database,
                    credential_scope=bridge.credential_scope,
                    parent_run_id=parent,
                )
                results = await _runner(
                    client,
                    database,
                    store,
                    run_id=child,
                    parent_run_id=parent,
                    stats=stats,
                ).run_batch(nodes, {})

        assert dispatches == 1
        assert database.attempt_count(child) == 0
        assert len(results) == 1
        assert database.node_state(child, nodes[0].node_id) == "reused"
        assert stats.snapshot().by_type.get(AnalyticsEventType.step_reused, 0) == 1
    finally:
        database.close()


@pytest.mark.asyncio
async def test_source_failure_cancels_and_awaits_ready_siblings(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    slow_started = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        if request.query.get("team") == "Failing Team":
            await slow_started.wait()
            return web.Response(status=400)
        slow_started.set()
        await asyncio.sleep(10)
        return web.json_response([game_response])

    @workflow(id="tests.failed_source_batch", revision=1)
    def failed_source_batch() -> dict[str, RecipeRef[list[Game]]]:
        return {
            "failing": games.as_("failing")(year=2024, team="Failing Team"),
            "slow": games.as_("slow")(year=2024, team="Slow Team"),
        }

    graph = _compile_recipe(failed_source_batch, (), {})
    nodes = _source_nodes(graph)
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        async with api_server(handler) as base_url:
            async with CFBDClient(
                "key",
                base_url=base_url,
                retry_policy=RetryPolicy(max_attempts=1),
            ) as client:
                bridge = client._analytics_bridge()
                run_id = _run(database, credential_scope=bridge.credential_scope)
                with pytest.raises(CFBDHTTPError):
                    await _runner(
                        client,
                        database,
                        store,
                        run_id=run_id,
                    ).run_batch(nodes, {})

                await asyncio.sleep(0)
                live_source_tasks = [
                    task
                    for task in asyncio.all_tasks()
                    if task is not asyncio.current_task()
                    and task.get_name().startswith("cfb-data-")
                    and not task.done()
                ]

        assert database.node_state(run_id, nodes[0].node_id) == "failed"
        assert database.node_state(run_id, nodes[1].node_id) == "cancelled"
        assert live_source_tasks == []
        assert slow_started.is_set()
    finally:
        database.close()
