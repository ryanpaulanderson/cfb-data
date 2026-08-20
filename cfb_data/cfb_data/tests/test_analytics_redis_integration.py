"""Exercise recipe execution through the real Redis response cache."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
import pytest_asyncio
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, ExecutionPolicy, RecipeRun
from cfb_data_recipes.game_summaries import game_summaries
from redis.asyncio import Redis

from cfb_data import CFBDClient, DataFrameBackend, RedisCacheConfig, RetryPolicy

ServerFactory = Callable[
    [Callable[[web.Request], object]], AbstractAsyncContextManager[str]
]


@pytest_asyncio.fixture
async def analytics_redis_config() -> AsyncIterator[RedisCacheConfig]:
    """Yield an isolated Redis namespace and remove only its owned keys."""
    url = os.getenv("CFB_DATA_TEST_REDIS_URL")
    if not url:
        pytest.skip("set CFB_DATA_TEST_REDIS_URL for real Redis integration tests")
    config = RedisCacheConfig(
        url=url,
        key_prefix=f"cfb-data-analytics-test-{uuid.uuid4().hex}",
    )
    try:
        yield config
    finally:
        client = Redis.from_url(config.url)
        owned_keys = [
            key async for key in client.scan_iter(match=f"{config.key_prefix}:v1:*")
        ]
        if owned_keys:
            await client.delete(*owned_keys)
        await client.aclose()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_recipe_replays_from_redis_through_every_supported_option(
    analytics_redis_config: RedisCacheConfig,
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Run independent transforms after one source response warms Redis."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        assert request.path == "/games"
        assert request.query == {"year": "2024", "team": "Penn State"}
        return web.json_response([game_response])

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...]
    combinations = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    records: list[list[dict[str, object]]] = []
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "analytics-redis-key",
            base_url=base_url,
            cache=analytics_redis_config,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "warm"),
        ) as client:
            warm: RecipeRun[object] = await game_summaries.run(
                client,
                year=2024,
                team="Penn State",
                policy=ExecutionPolicy(checkpoint_mode="off"),
            )
        assert warm.actual_http_attempts == 1

        for backend, executor in combinations:
            async with CFBDClient(
                "analytics-redis-key",
                base_url=base_url,
                cache=analytics_redis_config,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                with client.cache_mode("local_only"):
                    run: RecipeRun[object] = await game_summaries.run(
                        client,
                        year=2024,
                        team="Penn State",
                        policy=ExecutionPolicy(
                            checkpoint_mode="off",
                            executor=executor,
                            dask_max_workers=1,
                        ),
                    )
            assert run.actual_http_attempts == 0
            assert run.reused_nodes == 0
            digests.append(run.artifact.descriptor.content_digest)
            frame: pd.DataFrame = run.artifact.load()
            records.append(frame.to_dict(orient="records"))
            if executor == "dask":
                assert tuple(item.placement for item in run.lineage) == (
                    "coordinator",
                    "dask",
                    "coordinator",
                )

    assert calls == 1
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])
