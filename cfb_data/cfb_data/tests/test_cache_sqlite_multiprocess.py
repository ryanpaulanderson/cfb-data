"""Exercise SQLite refresh leases across real spawned processes."""

from __future__ import annotations

import asyncio
import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cfb_data.cache._sqlite import SQLiteCacheBackend
from cfb_data.cache.config import SQLiteCacheConfig


def _lease_worker(
    path: str,
    owner: str,
    ready: multiprocessing.synchronize.Event,
    start: multiprocessing.synchronize.Event,
    results: multiprocessing.queues.Queue,
) -> None:
    """Attempt one shared lease from an independent interpreter process."""

    async def run() -> None:
        backend = await SQLiteCacheBackend(SQLiteCacheConfig(path=Path(path))).open()
        ready.set()
        if not start.wait(timeout=10):
            results.put((owner, "start-timeout"))
        else:
            now = datetime.now(UTC)
            acquired = await backend.acquire_lease(
                "shared-response", owner, now + timedelta(seconds=30), now
            )
            results.put((owner, acquired))
        await backend.close()

    asyncio.run(run())


def test_sqlite_refresh_lease_has_one_cross_process_owner(tmp_path: Path) -> None:
    """Prove two processes cannot simultaneously acquire one live lease."""
    context = multiprocessing.get_context("spawn")
    first_ready = context.Event()
    second_ready = context.Event()
    start = context.Event()
    results = context.Queue()
    path = str(tmp_path / "cache.sqlite3")
    processes = [
        context.Process(
            target=_lease_worker,
            args=(path, "owner-a", first_ready, start, results),
        ),
        context.Process(
            target=_lease_worker,
            args=(path, "owner-b", second_ready, start, results),
        ),
    ]
    for process in processes:
        process.start()
    assert first_ready.wait(timeout=10)
    assert second_ready.wait(timeout=10)
    start.set()
    observed = [results.get(timeout=10), results.get(timeout=10)]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert sorted(result for _, result in observed) == [False, True]
