"""Validate the independent first-party betting-lines recipe."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy, RecipeRun
from cfb_data_recipes.betting_lines import BettingLine, betting_lines

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _payload() -> list[dict[str, object]]:
    """Return two provider quotes preserving open/current null distinctions."""
    return [
        {
            "id": 401628455,
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "startDate": "2024-08-31T19:30:00-04:00",
            "homeTeamId": 130,
            "homeTeam": "Michigan",
            "homeConference": "Big Ten",
            "homeClassification": "fbs",
            "homeScore": 30,
            "awayTeamId": 278,
            "awayTeam": "Fresno State",
            "awayConference": "Mountain West",
            "awayClassification": "fbs",
            "awayScore": 10,
            "lines": [
                {
                    "provider": "DraftKings",
                    "spread": -21.5,
                    "formattedSpread": "Michigan -21.5",
                    "spreadOpen": -22.0,
                    "overUnder": 45.5,
                    "overUnderOpen": 46.0,
                    "homeMoneyline": -1800,
                    "awayMoneyline": 900,
                },
                {
                    "provider": "Consensus",
                    "spread": None,
                    "formattedSpread": "",
                    "spreadOpen": None,
                    "overUnder": None,
                    "overUnderOpen": None,
                    "homeMoneyline": None,
                    "awayMoneyline": None,
                },
            ],
        }
    ]


@pytest.mark.asyncio
async def test_recipe_flattens_quotes_without_selecting_or_relabeling(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Keep every quote and preserve nullable open/current source fields."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(_payload())

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "betting-lines-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await betting_lines(client, season=2024)

    assert tuple(frame.columns) == tuple(BettingLine.model_fields)
    assert frame["provider"].tolist() == ["DraftKings", "Consensus"]
    assert frame["source_ordinal"].tolist() == [0, 1]
    assert frame.loc[0, "spread"] == -21.5
    assert frame.loc[0, "spread_open"] == -22.0
    assert pd.isna(frame.loc[1, "spread"])
    assert pd.isna(frame.loc[1, "spread_open"])
    assert "closing_spread" not in frame.columns
    assert "ats_result" not in frame.columns


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical provider-quote table across all options."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response(_payload())

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
                "betting-lines-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await betting_lines.run(
                    client,
                    season=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == 4
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_game_quote_keys_fail_instead_of_deduplicating(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Reject repeated game/provider/source-ordinal observations."""
    payload = _payload()
    payload.append(copy.deepcopy(payload[0]))

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "betting-lines-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await betting_lines(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.betting_lines@1")
    assert exc_info.value.category == "ValueError"
