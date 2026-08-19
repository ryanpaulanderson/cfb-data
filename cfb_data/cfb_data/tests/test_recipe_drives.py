"""Validate the independent first-party drives recipe."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeParameterError,
    CFBDRunError,
    ExecutionPolicy,
    RecipeRun,
)
from cfb_data_recipes.drives import DriveRow, drives

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _drive_payloads(drive_response: dict[str, object]) -> list[dict[str, object]]:
    """Return two drives with complete and partial source clock values."""
    later = copy.deepcopy(drive_response)
    later.update(
        {
            "id": "4016283472",
            "driveNumber": 2,
            "scoring": True,
            "startTime": {"minutes": 11, "seconds": 59},
            "endTime": {"minutes": 10, "seconds": None},
            "elapsed": {"minutes": 1, "seconds": None},
            "endOffenseScore": 7,
        }
    )
    return [later, copy.deepcopy(drive_response)]


@pytest.mark.asyncio
async def test_recipe_preserves_source_clocks_and_direct_arithmetic(
    api_server: ServerFactory,
    drive_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep nullable clock evidence and derive only fully supported values."""
    payloads = _drive_payloads(drive_response)

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/drives"
        assert request.query == {"year": "2024", "team": "Alabama"}
        return web.json_response(payloads)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "drives-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await drives(client, year=2024, team="Alabama")

    assert isinstance(frame, pd.DataFrame)
    assert tuple(frame.columns) == tuple(DriveRow.model_fields)
    assert frame["drive_id"].tolist() == ["4016283471", "4016283472"]
    assert frame["start_clock_seconds"].tolist() == [900, 719]
    assert frame.loc[0, "end_clock_seconds"] == 720
    assert frame.loc[0, "elapsed_seconds"] == 180
    assert pd.isna(frame.loc[1, "end_clock_seconds"])
    assert pd.isna(frame.loc[1, "elapsed_seconds"])
    assert frame["offense_score_change"].tolist() == [0, 7]
    assert frame["defense_score_change"].tolist() == [0, 0]
    assert "drive_success" not in frame.columns


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    drive_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Produce one logical drive table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payloads = _drive_payloads(drive_response)
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response(payloads)

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    records: list[list[dict[str, object]]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "drives-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await drives.run(
                    client,
                    year=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == 4
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_drive_keys_fail_instead_of_deduplicating(
    api_server: ServerFactory,
    drive_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject duplicate game/drive keys at the dataset boundary."""
    payloads = [copy.deepcopy(drive_response), copy.deepcopy(drive_response)]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payloads)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "drives-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await drives(client, year=2024)

    assert exc_info.value.node_id.endswith("cfbd.drives@1")
    assert exc_info.value.category == "ValueError"


@pytest.mark.asyncio
async def test_recipe_plan_requires_a_year() -> None:
    """Reject an omitted required selector before operational I/O."""
    client = CFBDClient("drives-key")

    with pytest.raises(CFBDRecipeParameterError, match="do not match"):
        await drives.plan(client)
