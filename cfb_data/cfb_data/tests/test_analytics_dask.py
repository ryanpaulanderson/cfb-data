"""Test the managed Dask transform provider contract."""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from cfb_data.analytics import CFBDExecutorError, step
from cfb_data.analytics._dask import _DaskTransformProvider
from pydantic import BaseModel, ConfigDict, TypeAdapter


class _DaskInputRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    label: str


class _DaskOutputRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: int
    label: str
    worker_pid: int | None = None


@step(id="tests.dask_normalize", revision=1, output=_DaskOutputRow)
def _normalize_on_worker(
    rows: list[_DaskInputRow],
    *,
    suffix: str,
) -> list[_DaskOutputRow]:
    return [
        _DaskOutputRow(
            game_id=row.game_id,
            label=f"{row.label.strip()}{suffix}",
            worker_pid=os.getpid(),
        )
        for row in rows
    ]


@step(id="tests.dask_from_text", revision=1, output=_DaskOutputRow)
def _from_text_on_worker(text: str) -> list[_DaskOutputRow]:
    return [_DaskOutputRow(game_id=1, label=text)]


@step(id="tests.coordinator_only", revision=1, output=_DaskOutputRow, dask=False)
def _coordinator_only() -> list[_DaskOutputRow]:
    return []


@pytest.mark.asyncio
async def test_provider_is_lazy_and_rejects_ineligible_work_before_start() -> None:
    """Avoid importing or starting Dask until eligible work is admitted."""
    provider = _DaskTransformProvider(
        max_workers=4,
        threads_per_worker=1,
        transfer_limit_bytes=512 * 1024 * 1024,
    )

    async with provider:
        assert not provider.started
        with pytest.raises(CFBDExecutorError) as exc_info:
            await provider.execute(_coordinator_only, {})

        assert exc_info.value.provider == "dask"
        assert exc_info.value.category == "ineligible"
        assert not provider.started

    assert not provider.started


@pytest.mark.asyncio
async def test_transfer_limit_is_measured_before_cluster_start() -> None:
    """Reject actual encoded input bytes without allocating Dask resources."""
    provider = _DaskTransformProvider(
        max_workers=1,
        threads_per_worker=1,
        transfer_limit_bytes=16,
    )

    async with provider:
        with pytest.raises(CFBDExecutorError) as exc_info:
            await provider.execute(_from_text_on_worker, {"text": "x" * 64})

        assert exc_info.value.category == "transfer_limit"
        assert not provider.started


@pytest.mark.asyncio
async def test_managed_dask_round_trip_uses_arrow_and_closes() -> None:
    """Execute on a process worker and deterministically close owned resources."""
    pytest.importorskip("distributed")
    provider = _DaskTransformProvider(
        max_workers=2,
        threads_per_worker=1,
        transfer_limit_bytes=16 * 1024 * 1024,
    )

    async with provider:
        raw_results = await asyncio.gather(
            provider.execute(
                _normalize_on_worker,
                {
                    "rows": [_DaskInputRow(game_id=401628515, label=" Penn State ")],
                    "suffix": "!",
                },
            ),
            provider.execute(
                _normalize_on_worker,
                {
                    "rows": [_DaskInputRow(game_id=2, label=" Ohio State ")],
                    "suffix": "?",
                },
            ),
        )
        adapter = TypeAdapter(list[_DaskOutputRow])
        first = adapter.validate_python(raw_results[0], strict=True)
        second = adapter.validate_python(raw_results[1], strict=True)

        assert provider.started
        assert [(row.game_id, row.label) for row in first + second] == [
            (401628515, "Penn State!"),
            (2, "Ohio State?"),
        ]
        assert all(row.worker_pid is not None for row in first + second)
        assert all(row.worker_pid != os.getpid() for row in first + second)

    assert not provider.started


@pytest.mark.asyncio
async def test_cancelled_worker_future_is_awaited_before_cleanup() -> None:
    """Preserve cancellation while draining and closing provider resources."""
    pytest.importorskip("distributed")

    @step(id="tests.dask_blocking", revision=1, output=_DaskOutputRow)
    def blocking(delay: float) -> list[_DaskOutputRow]:
        time.sleep(delay)
        return [_DaskOutputRow(game_id=1, label="late")]

    provider = _DaskTransformProvider(
        max_workers=1,
        threads_per_worker=1,
        transfer_limit_bytes=16 * 1024 * 1024,
    )
    async with provider:
        task = asyncio.create_task(provider.execute(blocking, {"delay": 5.0}))
        while not provider.started:
            await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    assert not provider.started
