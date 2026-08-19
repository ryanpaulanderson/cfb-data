"""Validate the independent first-party game-summary recipe."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    ExecutionPolicy,
)
from cfb_data_recipes.game_summaries import (
    GameResultState,
    GameSummary,
    game_summaries,
)

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

ServerFactory = Callable[[Callable[[web.Request], object]], object]


def _game_payloads(game_response: dict[str, object]) -> list[dict[str, object]]:
    """Return future, tied, and decided games in deliberately unstable order."""
    decided = copy.deepcopy(game_response)
    decided["id"] = 3

    tied = copy.deepcopy(game_response)
    tied.update({"id": 2, "homePoints": 21, "awayPoints": 21})

    future = copy.deepcopy(game_response)
    future.update(
        {
            "id": 1,
            "completed": False,
            "homePoints": None,
            "awayPoints": None,
            "homeLineScores": None,
            "awayLineScores": None,
        }
    )
    return [decided, future, tied]


@pytest.mark.asyncio
async def test_recipe_preserves_source_fields_and_conservative_results(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Derive results only from completed games with both reported scores."""
    payloads = _game_payloads(game_response)

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/games"
        assert request.query == {"year": "2024", "team": "Penn State"}
        return web.json_response(payloads)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "game-summary-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run = await game_summaries.run(
                client,
                year=2024,
                team="Penn State",
            )

    frame = run.value
    assert isinstance(frame, pd.DataFrame)
    assert tuple(frame.columns) == tuple(GameSummary.model_fields)
    assert "id" not in frame.columns
    assert frame["game_id"].tolist() == [1, 2, 3]
    assert pd.isna(frame.loc[0, "result_state"])
    assert pd.isna(frame.loc[0, "total_points"])
    assert pd.isna(frame.loc[0, "margin"])
    assert pd.isna(frame.loc[0, "winner_id"])
    assert pd.isna(frame.loc[0, "loser_id"])
    assert frame.loc[1, "result_state"] == GameResultState.tie
    assert frame.loc[1, "total_points"] == 42
    assert frame.loc[1, "margin"] == 0
    assert pd.isna(frame.loc[1, "winner_id"])
    assert pd.isna(frame.loc[1, "loser_id"])
    assert frame.loc[2, "result_state"] == GameResultState.home_win
    assert frame.loc[2, "total_points"] == 63
    assert frame.loc[2, "margin"] == 63
    assert frame.loc[2, "winner_id"] == 333
    assert frame.loc[2, "loser_id"] == 2459
    assert run.artifact.descriptor.output_id == "cfbd.game_summaries"
    assert run.artifact.descriptor.output_revision == 1


@pytest.mark.asyncio
async def test_recipe_is_portable_across_frame_and_executor_options(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Produce identical canonical content in all four supported combinations."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls = 0
    payloads = _game_payloads(game_response)

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
    dask_placements: list[tuple[str, ...]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "game-summary-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run = await game_summaries.run(
                    client,
                    year=2024,
                    policy=ExecutionPolicy(
                        executor=executor,
                        dask_max_workers=1,
                    ),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))
            if executor == "dask":
                dask_placements.append(tuple(item.placement for item in run.lineage))

    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])
    assert calls == 4
    assert all(
        placements == ("coordinator", "dask", "coordinator")
        for placements in dask_placements
    )


@pytest.mark.asyncio
async def test_recipe_plan_validates_the_endpoint_selector_contract() -> None:
    """Reject missing year and game ID without network or artifact work."""
    client = CFBDClient("game-summary-key")

    with pytest.raises(CFBDRecipeCompilationError, match="endpoint contract"):
        await game_summaries.plan(client, team="Penn State")
