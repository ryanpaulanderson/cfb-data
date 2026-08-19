"""Test local transform execution, validation, reuse, and cancellation."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
from cfb_data.analytics import RecipeRef, dataset, step, workflow
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.analytics._compute import _LocalTransformProvider
from cfb_data.analytics._observability import _AnalyticsDispatcher
from cfb_data.analytics._persistence import _ArtifactObjectStore, _RunDatabase
from cfb_data.analytics._transforms import _TransformRunner
from pydantic import BaseModel, ConfigDict


class _RawRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    label: str


class _CleanRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    label: str


def _run(database: _RunDatabase, *, parent_run_id: str | None = None) -> str:
    run = database.create_run(
        recipe_id="tests.cleaned_rows",
        recipe_revision=1,
        recipe_kind="dataset",
        parameter_fingerprint="a" * 64,
        graph_fingerprint="b" * 64,
        credential_scope="scope-a",
        parent_run_id=parent_run_id,
    )
    database.transition_run(run.run_id, "running")
    return run.run_id


def _runner(
    database: _RunDatabase,
    store: _ArtifactObjectStore,
    *,
    run_id: str,
    concurrency: int = 1,
    parent_run_id: str | None = None,
) -> _TransformRunner:
    return _TransformRunner(
        provider=_LocalTransformProvider(concurrency=concurrency),
        database=database,
        object_store=store,
        run_id=run_id,
        credential_scope="scope-a",
        parent_run_id=parent_run_id,
        source_behavior=(
            "preserve_snapshot" if parent_run_id is not None else "normal_freshness"
        ),
        backend="pandas",
        dispatcher=_AnalyticsDispatcher(None),
    )


@pytest.mark.asyncio
async def test_sync_step_runs_off_loop_and_dataset_validates_contract(
    tmp_path: Path,
) -> None:
    execution_threads: list[int] = []

    @step(id="tests.normalize_rows", revision=1, output=_CleanRow)
    def normalize(rows: list[_RawRow]) -> list[_CleanRow]:
        execution_threads.append(threading.get_ident())
        return [_CleanRow(id=row.id, label=row.label.strip()) for row in rows]

    @dataset(
        id="tests.cleaned_rows",
        revision=1,
        row=_CleanRow,
        grain="one row",
        keys=("id",),
        order_by=("id",),
    )
    def cleaned_rows() -> RecipeRef[list[_CleanRow]]:
        return normalize(
            [
                _RawRow(id=1, label=" first "),
                _RawRow(id=2, label=" second "),
            ]
        )

    graph = _compile_recipe(cleaned_rows, (), {})
    step_node, dataset_node = graph.nodes
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        run_id = _run(database)
        runner = _runner(database, store, run_id=run_id)
        transformed = await runner.run_batch((step_node,), {})
        final = await runner.run_batch((dataset_node,), transformed)

        rows = final[dataset_node.node_id].value
        assert rows == [
            _CleanRow(id=1, label="first"),
            _CleanRow(id=2, label="second"),
        ]
        assert execution_threads != [threading.get_ident()]
        assert len(database.bindings(run_id)) == 2
        placements = {
            binding.node_id: binding.placement for binding in database.bindings(run_id)
        }
        assert placements[step_node.node_id] == "local"
        assert placements[dataset_node.node_id] == "coordinator"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_local_compute_concurrency_is_exact(tmp_path: Path) -> None:
    active = 0
    maximum = 0
    lock = threading.Lock()

    @step(id="tests.slow_rows", revision=1, output=_CleanRow)
    def slow(rows: list[_CleanRow]) -> list[_CleanRow]:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return rows

    @workflow(id="tests.parallel_transforms", revision=1)
    def parallel_transforms() -> dict[str, RecipeRef[list[_CleanRow]]]:
        return {
            "first": slow.as_("first")([_CleanRow(id=1, label="a")]),
            "second": slow.as_("second")([_CleanRow(id=2, label="b")]),
            "third": slow.as_("third")([_CleanRow(id=3, label="c")]),
        }

    graph = _compile_recipe(parallel_transforms, (), {})
    nodes = tuple(node for node in graph.nodes if node.kind == "step")
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        run_id = _run(database)
        await _runner(
            database,
            store,
            run_id=run_id,
            concurrency=2,
        ).run_batch(nodes, {})

        assert maximum == 2
    finally:
        database.close()


@pytest.mark.asyncio
async def test_dataset_duplicate_keys_fail_without_successful_binding(
    tmp_path: Path,
) -> None:
    @step(id="tests.duplicate_rows", revision=1, output=_CleanRow)
    def duplicates() -> list[_CleanRow]:
        return [
            _CleanRow(id=1, label="first"),
            _CleanRow(id=1, label="second"),
        ]

    @dataset(
        id="tests.duplicate_dataset",
        revision=1,
        row=_CleanRow,
        grain="one row",
        keys=("id",),
    )
    def duplicate_dataset() -> RecipeRef[list[_CleanRow]]:
        return duplicates()

    graph = _compile_recipe(duplicate_dataset, (), {})
    step_node, dataset_node = graph.nodes
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        run_id = _run(database)
        runner = _runner(database, store, run_id=run_id)
        transformed = await runner.run_batch((step_node,), {})

        with pytest.raises(ValueError, match="not unique"):
            await runner.run_batch((dataset_node,), transformed)

        assert database.node_state(run_id, dataset_node.node_id) == "failed"
        assert len(database.bindings(run_id)) == 1
    finally:
        database.close()


@pytest.mark.asyncio
async def test_cancelled_transform_awaits_started_thread_work(tmp_path: Path) -> None:
    worker_finished = threading.Event()

    @step(id="tests.cancellable_rows", revision=1, output=_CleanRow)
    def slow() -> list[_CleanRow]:
        time.sleep(0.05)
        worker_finished.set()
        return [_CleanRow(id=1, label="done")]

    @dataset(
        id="tests.cancellable_dataset",
        revision=1,
        row=_CleanRow,
        grain="one row",
        keys=("id",),
    )
    def cancellable_dataset() -> RecipeRef[list[_CleanRow]]:
        return slow()

    graph = _compile_recipe(cancellable_dataset, (), {})
    node = graph.nodes[0]
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        run_id = _run(database)
        task = asyncio.create_task(
            _runner(database, store, run_id=run_id).run_batch((node,), {})
        )
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert worker_finished.is_set()
        assert database.node_state(run_id, node.node_id) == "cancelled"
        assert database.bindings(run_id) == ()
    finally:
        database.close()


@pytest.mark.asyncio
async def test_deterministic_transform_reuses_global_checkpoint(
    tmp_path: Path,
) -> None:
    executions = 0

    @step(id="tests.reused_rows", revision=1, output=_CleanRow)
    def reusable() -> list[_CleanRow]:
        nonlocal executions
        executions += 1
        return [_CleanRow(id=1, label="stable")]

    @dataset(
        id="tests.reused_dataset",
        revision=1,
        row=_CleanRow,
        grain="one row",
        keys=("id",),
    )
    def reused_dataset() -> RecipeRef[list[_CleanRow]]:
        return reusable()

    graph = _compile_recipe(reused_dataset, (), {})
    root = tmp_path / "analytics"
    store = _ArtifactObjectStore(root)
    database = _RunDatabase(root / "runs.sqlite3")
    try:
        first_run = _run(database)
        first_runner = _runner(database, store, run_id=first_run)
        first_step = await first_runner.run_batch((graph.nodes[0],), {})
        await first_runner.run_batch((graph.nodes[1],), first_step)

        second_run = _run(database)
        second_runner = _runner(database, store, run_id=second_run)
        second_step = await second_runner.run_batch((graph.nodes[0],), {})
        await second_runner.run_batch((graph.nodes[1],), second_step)

        assert executions == 1
        assert database.node_state(second_run, graph.nodes[0].node_id) == "reused"
        assert database.node_state(second_run, graph.nodes[1].node_id) == "reused"
    finally:
        database.close()
