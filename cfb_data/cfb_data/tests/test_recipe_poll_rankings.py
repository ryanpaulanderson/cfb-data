"""Validate the independent first-party poll-rankings recipe."""

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
from cfb_data_recipes.poll_rankings import PollRanking, poll_rankings

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _payload() -> list[dict[str, object]]:
    """Return one snapshot with nullable rank evidence in source order."""
    return [
        {
            "season": 2024,
            "seasonType": "regular",
            "week": 1,
            "polls": [
                {
                    "poll": "AP Top 25",
                    "isFinal": None,
                    "ranks": [
                        {
                            "rank": 2,
                            "teamId": 213,
                            "school": "Penn State",
                            "conference": "Big Ten",
                            "firstPlaceVotes": 5,
                            "points": 1450,
                        },
                        {
                            "rank": None,
                            "teamId": 130,
                            "school": "Michigan",
                            "conference": "Big Ten",
                            "firstPlaceVotes": None,
                            "points": None,
                        },
                    ],
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_recipe_flattens_poll_order_and_preserves_nullable_rank(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Retain poll/rank order separately from nullable rank values."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(_payload())

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "poll-rankings-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await poll_rankings(client, season=2024)

    assert tuple(frame.columns) == tuple(PollRanking.model_fields)
    assert frame["team_id"].tolist() == [213, 130]
    assert frame["rank_ordinal"].tolist() == [0, 1]
    assert frame.loc[0, "rank"] == 2
    assert pd.isna(frame.loc[1, "rank"])
    assert pd.isna(frame.loc[1, "first_place_votes"])
    assert pd.isna(frame.loc[1, "points"])
    assert frame["is_final"].isna().all()


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical ranking table across frames and executors."""
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
                "poll-rankings-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await poll_rankings.run(
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
async def test_duplicate_snapshot_keys_fail_instead_of_deduplicating(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Reject duplicate team/poll snapshot observations."""
    payload = _payload()
    polls = payload[0]["polls"]
    assert isinstance(polls, list)
    first_poll = polls[0]
    assert isinstance(first_poll, dict)
    ranks = first_poll["ranks"]
    assert isinstance(ranks, list)
    ranks.append(copy.deepcopy(ranks[0]))

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "poll-rankings-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await poll_rankings(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.poll_rankings@1")
    assert exc_info.value.category == "ValueError"
