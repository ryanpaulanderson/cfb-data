"""Exercise calculated Success Rate through the public workflow and HTTP boundary."""

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
)
from cfb_data_recipes.success_rate import success_rate

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _game(
    template: dict[str, object], *, game_id: int = 1, week: int = 1
) -> dict[str, object]:
    game = copy.deepcopy(template)
    game.update(
        {
            "id": game_id,
            "week": week,
            "homeId": 10,
            "homeTeam": "Home",
            "awayId": 20,
            "awayTeam": "Away",
            "homePoints": 7,
            "awayPoints": 0,
        }
    )
    return game


def _play(
    template: dict[str, object],
    *,
    number: int,
    gain: int,
    down: int = 1,
    distance: int = 10,
    kind: str = "Rush",
    text: str | None = None,
) -> dict[str, object]:
    play = copy.deepcopy(template)
    play.update(
        {
            "id": str(number),
            "driveId": "d1",
            "gameId": 1,
            "driveNumber": 1,
            "playNumber": number,
            "home": "Home",
            "away": "Away",
            "offense": "Home",
            "defense": "Away",
            "down": down,
            "distance": distance,
            "yardsToGoal": 50,
            "yardsGained": gain,
            "playType": kind,
            "playText": text,
            "ppa": None,
        }
    )
    return play


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unknown_kind", ["New Upstream Type", "Safety", "Uncategorized Touchdown"]
)
async def test_success_rate_counts_thresholds_unknowns_and_defense(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
    unknown_kind: str,
) -> None:
    payloads = [
        _play(play_response, number=1, gain=5),
        _play(play_response, number=2, gain=4, down=2, distance=6),
        _play(play_response, number=3, gain=3, down=3, distance=3),
        _play(play_response, number=4, gain=50, kind="Pass Interception Return"),
        _play(play_response, number=5, gain=0, kind=unknown_kind),
        _play(
            play_response,
            number=6,
            gain=-1,
            text="Quarterback kneels for loss of 1 yard",
        ),
        _play(play_response, number=7, gain=0, kind="Punt"),
    ]
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.json_response(
            [_game(game_response)] if request.path == "/games" else payloads
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path),
        ) as client:
            outputs = await success_rate(client, year=2024, weeks=(1,))
    assert set(paths) == {"/games", "/plays"}
    plays = outputs["plays"]
    assert isinstance(plays, pd.DataFrame)
    assert plays["successful"].tolist()[:4] == [True, False, True, False]
    games = outputs["team_games"]
    assert isinstance(games, pd.DataFrame)
    offense = games.loc[
        (games["team_id"] == 10)
        & (games["unit"] == "offense")
        & (games["split"] == "all")
    ].iloc[0]
    assert offense["successful_plays"] == 2
    assert offense["evaluated_plays"] == 4
    assert offense["unknown_plays"] == 1
    assert offense["excluded_plays"] == 2
    assert offense["success_rate"] == 0.5
    assert offense["coverage"] == "partial"
    defense = games.loc[
        (games["team_id"] == 20)
        & (games["unit"] == "defense")
        & (games["split"] == "all")
    ].iloc[0]
    assert defense["success_rate"] == offense["success_rate"]
    missing = games.loc[
        (games["team_id"] == 20)
        & (games["unit"] == "offense")
        & (games["split"] == "all")
    ].iloc[0]
    assert missing["coverage"] == "unavailable"
    assert pd.isna(missing["success_rate"])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["duplicate", "identity", "field"])
async def test_invalid_metric_evidence_fails_before_publication(
    failure: str,
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    payloads = [_play(play_response, number=1, gain=5)]
    if failure == "duplicate":
        payloads.append(copy.deepcopy(payloads[0]))
    elif failure == "identity":
        payloads[0]["defense"] = "Different team"
    else:
        payloads[0]["distance"] = 51

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [_game(game_response)] if request.path == "/games" else payloads
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path),
        ) as client:
            with pytest.raises(CFBDRunError):
                await success_rate(client, year=2024, weeks=(1,))


@pytest.mark.asyncio
async def test_success_rate_has_fresh_multipartition_four_way_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payloads = [
        _play(play_response, number=index, gain=index % 7) for index in range(1, 9)
    ]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [_game(game_response)] if request.path == "/games" else payloads
        )

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    signatures: list[tuple[str, ...]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / executor),
            ) as client:
                run = await success_rate.run(
                    client,
                    year=2024,
                    weeks=(1,),
                    policy=ExecutionPolicy(
                        executor=executor, table_partition_rows=2, dask_max_workers=1
                    ),
                )
            signatures.append(
                tuple(
                    run.artifacts[name].descriptor.content_digest
                    for name in ("plays", "team_games", "team_seasons")
                )
            )
    assert all(signature == signatures[0] for signature in signatures)


@pytest.mark.asyncio
async def test_invalid_week_selector_never_calls_http(tmp_path: Path) -> None:
    async with CFBDClient("key", analytics=AnalyticsConfig(root=tmp_path)) as client:
        with pytest.raises(CFBDRecipeCompilationError) as caught:
            await success_rate(client, year=2024, weeks=(1, 1))
        assert isinstance(caught.value.__cause__, ValueError)
        assert "repeat" in str(caught.value.__cause__)


@pytest.mark.asyncio
async def test_fumbles_score_timing_and_pooled_denominators(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    week_one = [
        _play(
            play_response,
            number=1,
            gain=50,
            kind="Fumble Recovery (Opponent)",
            text="Runner run and fumbled; opponent recovered",
        ),
        _play(
            play_response,
            number=2,
            gain=50,
            kind="Fumble Recovery (Own)",
            text="Runner run and fumbled; own recovery",
        ),
        _play(play_response, number=3, gain=10),
    ]
    week_one[2].update({"offenseScore": 7, "scoring": True})
    second_game = _game(game_response, game_id=2, week=2)
    week_two = [_play(play_response, number=1, gain=0)]
    week_two[0]["gameId"] = 2

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [_game(game_response), second_game]
            if request.path == "/games"
            else week_one
            if request.query["week"] == "1"
            else week_two
        )

    async with api_server(handler) as url:
        async with CFBDClient(
            "key", base_url=url, analytics=AnalyticsConfig(root=tmp_path)
        ) as client:
            result = await success_rate(client, year=2024, weeks=(1, 2))
    plays = result["plays"]
    flags = plays.loc[plays["game_id"] == 1, "successful"].tolist()
    assert not flags[0]
    assert pd.isna(flags[1])
    assert flags[2]
    assert plays.loc[plays["game_id"] == 1, "rush_reason"].tolist()[:2] == [
        "fumble_event",
        "fumble_event",
    ]
    assert (
        plays.loc[
            (plays["game_id"] == 1) & (plays["play_id"] == "3"), "preplay_score_margin"
        ].iloc[0]
        == 0
    )
    season = result["team_seasons"]
    offense = season.loc[
        (season["team_id"] == 10)
        & (season["unit"] == "offense")
        & (season["split"] == "all")
    ].iloc[0]
    assert offense["evaluated_plays"] == 3
    assert offense["unknown_plays"] == 1
    assert offense["success_rate"] == pytest.approx(1 / 3)
