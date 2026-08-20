"""Validate the independent first-party plays recipe."""

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
    CFBDRecipeCompilationError,
    CFBDRunError,
    ExecutionPolicy,
    RecipeRun,
)
from cfb_data_recipes.plays import PlayRow, WinProbabilityCoverage, plays

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _win_probability(play: dict[str, object]) -> dict[str, object]:
    """Return a complete probability observation for one play fixture."""
    return {
        "gameId": play["gameId"],
        "playId": play["id"],
        "playText": play["playText"],
        "homeId": 130,
        "home": play["home"],
        "awayId": 278,
        "away": play["away"],
        "spread": -21.5,
        "homeBall": False,
        "homeScore": 0,
        "awayScore": 0,
        "yardLine": 75,
        "down": 1,
        "distance": 10,
        "homeWinProbability": 0.82,
        "playNumber": 2,
    }


def _game_id(play: dict[str, object]) -> int:
    """Return the fixture game ID after narrowing its external value."""
    game_id = play["gameId"]
    assert isinstance(game_id, int)
    return game_id


@pytest.mark.asyncio
async def test_base_recipe_preserves_nullable_ppa_and_clock(
    api_server: ServerFactory,
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Preserve source nulls and avoid requesting probability by default."""
    play = copy.deepcopy(play_response)
    play["ppa"] = None
    play["clock"] = {"minutes": 15, "seconds": None}
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.json_response([play])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "plays-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await plays(client, year=2024, week=1)

    assert paths == ["/plays"]
    assert tuple(frame.columns) == tuple(PlayRow.model_fields)
    assert frame.loc[0, "play_id"] == play_response["id"]
    assert pd.isna(frame.loc[0, "ppa"])
    assert pd.isna(frame.loc[0, "clock_seconds"])
    assert (
        frame.loc[0, "win_probability_coverage"] == WinProbabilityCoverage.not_requested
    )
    assert pd.isna(frame.loc[0, "win_probability"])


@pytest.mark.asyncio
async def test_requested_probability_has_four_way_canonical_parity(
    api_server: ServerFactory,
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Attach exact probability identically across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    probability = _win_probability(play_response)
    calls: dict[str, int] = {"/plays": 0, "/metrics/wp": 0}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(
            [play_response] if request.path == "/plays" else [probability]
        )

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
                "plays-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await plays.run(
                    client,
                    year=2024,
                    week=1,
                    game_id=_game_id(play_response),
                    include_win_probability=True,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            restored = run.artifact.load()
            records.append(restored.to_dict(orient="records"))
            assert restored.loc[0, "win_probability"]["home_win_probability"] == 0.82

    assert calls == {"/plays": 4, "/metrics/wp": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_incomplete_probability_fails_without_shrinking_plays(
    api_server: ServerFactory,
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Fail requested enrichment when its stable play key is absent."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([play_response] if request.path == "/plays" else [])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "plays-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await plays(
                    client,
                    year=2024,
                    week=1,
                    game_id=_game_id(play_response),
                    include_win_probability=True,
                )

    assert exc_info.value.node_id.endswith("cfbd.plays.attach_win_probability@1")
    assert exc_info.value.category == "ValueError"


@pytest.mark.asyncio
async def test_probability_requires_an_explicit_game_id() -> None:
    """Reject unbounded one-request-per-game probability fan-out in planning."""
    client = CFBDClient("plays-key")

    with pytest.raises(CFBDRecipeCompilationError, match="builder failed"):
        await plays.plan(
            client,
            year=2024,
            week=1,
            include_win_probability=True,
        )
