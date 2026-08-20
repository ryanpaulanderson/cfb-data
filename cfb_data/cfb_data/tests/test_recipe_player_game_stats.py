"""Validate the independent long-form player-game-stat recipe."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy
from cfb_data_recipes.player_game_stats import PlayerGameStat, player_game_stats

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

ServerFactory = Callable[[Callable[[web.Request], object]], object]


def _player_stats_payload(game_id: int) -> list[dict[str, object]]:
    """Return representative nested source observations for both game sides."""
    return [
        {
            "id": game_id,
            "teams": [
                {
                    "team": "Alabama",
                    "conference": "SEC",
                    "homeAway": "home",
                    "points": 63,
                    "categories": [
                        {
                            "name": "passing",
                            "types": [
                                {
                                    "name": "C/ATT",
                                    "athletes": [
                                        {
                                            "id": "009",
                                            "name": "Sample Quarterback",
                                            "stat": "7/9",
                                        }
                                    ],
                                },
                                {
                                    "name": "YDS",
                                    "athletes": [
                                        {
                                            "id": "009",
                                            "name": "Sample Quarterback",
                                            "stat": "210",
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "team": "Western Kentucky",
                    "conference": None,
                    "homeAway": "away",
                    "points": 0,
                    "categories": [
                        {
                            "name": "rushing",
                            "types": [
                                {
                                    "name": "YDS",
                                    "athletes": [
                                        {
                                            "id": "1001",
                                            "name": "Sample Runner",
                                            "stat": "42",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            ],
        }
    ]


@pytest.mark.asyncio
async def test_recipe_flattens_nesting_and_preserves_display_statistics(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Resolve game-scoped team IDs without coercing compound stat strings."""
    payload = _player_stats_payload(int(game_response["id"]))

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game_response])
        assert request.path == "/games/players"
        return web.json_response(payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "player-game-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame = await player_game_stats(
                client,
                year=2024,
                team="Alabama",
            )

    assert isinstance(frame, pd.DataFrame)
    assert tuple(frame.columns) == tuple(PlayerGameStat.model_fields)
    assert frame["team_id"].tolist() == [333, 333, 2459]
    assert frame["athlete_id"].tolist() == ["009", "009", "1001"]
    assert frame["category"].tolist() == ["passing", "passing", "rushing"]
    assert frame["stat_type"].tolist() == ["C/ATT", "YDS", "YDS"]
    assert frame["stat"].tolist() == ["7/9", "210", "42"]
    assert frame["stat"].dtype.name == "string"


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Produce one logical long-form table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payload = _player_stats_payload(int(game_response["id"]))
    calls: dict[str, int] = {"/games": 0, "/games/players": 0}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(
            [game_response] if request.path == "/games" else payload
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
                "player-game-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run = await player_game_stats.run(
                    client,
                    year=2024,
                    team="Alabama",
                    policy=ExecutionPolicy(
                        executor=executor,
                        dask_max_workers=1,
                    ),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {"/games": 4, "/games/players": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_candidate_keys_fail_instead_of_aggregating(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject duplicate athlete/category/type observations at the dataset boundary."""
    payload = _player_stats_payload(int(game_response["id"]))
    duplicate = copy.deepcopy(
        payload[0]["teams"][0]["categories"][0]["types"][0]["athletes"][0]
    )
    payload[0]["teams"][0]["categories"][0]["types"][0]["athletes"].append(duplicate)

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [game_response] if request.path == "/games" else payload
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "player-game-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await player_game_stats(
                    client,
                    year=2024,
                    team="Alabama",
                )

    assert exc_info.value.node_id.endswith("cfbd.player_game_stats@1")
    assert exc_info.value.category == "ValueError"
