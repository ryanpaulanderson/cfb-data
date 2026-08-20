"""Exercise analytics node leases across real spawned processes."""

from __future__ import annotations

import multiprocessing
from datetime import timedelta
from pathlib import Path

from cfb_data.analytics._persistence import _RunDatabase


def _lease_worker(
    path: str,
    run_id: str,
    owner_token: str,
    ready: multiprocessing.synchronize.Event,
    start: multiprocessing.synchronize.Event,
    results: multiprocessing.queues.Queue[tuple[str, bool | str]],
) -> None:
    """Attempt one shared analytics lease from an independent process."""
    database = _RunDatabase(Path(path))
    try:
        ready.set()
        if not start.wait(timeout=10):
            results.put((owner_token, "start-timeout"))
            return
        acquired = database.acquire_node_lease(
            lease_key="a" * 64,
            owner_token=owner_token,
            run_id=run_id,
            node_id="shared-step",
            ttl=timedelta(seconds=30),
        )
        results.put((owner_token, acquired))
    finally:
        database.close()


def test_node_lease_has_one_cross_process_owner(tmp_path: Path) -> None:
    """Prove two processes cannot simultaneously own one live node lease."""
    path = tmp_path / "runs.sqlite3"
    database = _RunDatabase(path)
    try:
        runs = tuple(
            database.create_run(
                recipe_id="cfbd.cross_process",
                recipe_revision=1,
                recipe_kind="dataset",
                parameter_fingerprint=character * 64,
                graph_fingerprint="f" * 64,
                credential_scope="scope-a",
            )
            for character in ("b", "c")
        )
    finally:
        database.close()

    context = multiprocessing.get_context("spawn")
    ready_events = (context.Event(), context.Event())
    start = context.Event()
    results = context.Queue()
    processes = tuple(
        context.Process(
            target=_lease_worker,
            args=(
                str(path),
                run.run_id,
                owner_token,
                ready,
                start,
                results,
            ),
        )
        for run, owner_token, ready in zip(
            runs,
            ("d" * 64, "e" * 64),
            ready_events,
            strict=True,
        )
    )
    for process in processes:
        process.start()
    for ready in ready_events:
        assert ready.wait(timeout=10)
    start.set()
    observed = tuple(results.get(timeout=10) for _ in processes)
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert sorted(result for _, result in observed) == [False, True]
