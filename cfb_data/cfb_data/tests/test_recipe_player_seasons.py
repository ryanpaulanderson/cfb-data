"""Validate the independent first-party player-seasons recipe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy, RecipeRun
from cfb_data_recipes.player_seasons import PlayerSeason, player_seasons

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _roster_player(athlete_id: str) -> dict[str, object]:
    """Return one complete roster membership fixture."""
    return {
        "id": athlete_id,
        "firstName": "Roster",
        "lastName": athlete_id,
        "team": "Penn State",
        "height": 74.0,
        "weight": 220,
        "jersey": 4,
        "year": 3,
        "position": "QB",
        "homeCity": None,
        "homeState": None,
        "homeCountry": None,
        "homeLatitude": None,
        "homeLongitude": None,
        "homeCountyFIPS": None,
        "recruitIds": None,
    }


def _team() -> dict[str, object]:
    """Return temporal Penn State identity evidence."""
    return {
        "id": 213,
        "school": "Penn State",
        "mascot": "Nittany Lions",
        "abbreviation": "PSU",
        "alternateNames": ["Penn St."],
        "conference": "Big Ten",
        "division": None,
        "classification": "fbs",
        "color": None,
        "alternateColor": None,
        "logos": None,
        "twitter": None,
        "location": None,
    }


def _stat(athlete_id: str, stat_type: str, stat: str) -> dict[str, object]:
    """Return one long-form player-season statistic."""
    return {
        "season": 2024,
        "playerId": athlete_id,
        "player": f"Statistics {athlete_id}",
        "position": "QB",
        "team": "Penn State",
        "conference": "Big Ten",
        "category": "passing",
        "statType": stat_type,
        "stat": stat,
    }


@pytest.mark.asyncio
async def test_recipe_unions_roster_only_and_stats_only_athletes(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Retain both source populations and preserve display statistics."""
    payloads: dict[str, object] = {
        "/roster": [_roster_player("001"), _roster_player("002")],
        "/teams": [_team()],
        "/stats/player/season": [
            _stat("001", "C/ATT", "7/9"),
            _stat("003", "YDS", "210"),
        ],
    }
    calls: dict[str, int] = {path: 0 for path in payloads}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "player-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await player_seasons(
                client,
                season=2024,
                team="Penn State",
            )

    assert calls == {"/roster": 1, "/teams": 1, "/stats/player/season": 1}
    assert tuple(frame.columns) == tuple(PlayerSeason.model_fields)
    assert frame["athlete_id"].tolist() == ["001", "002", "003"]
    assert frame["roster_present"].tolist() == [True, True, False]
    assert frame["statistics_present"].tolist() == [True, False, True]
    assert frame.loc[0, "statistics"][0]["stat"] == "7/9"
    assert frame.loc[2, "statistics"][0]["stat"] == "210"
    assert frame["team_id"].tolist() == [213, 213, 213]


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical player-season table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payloads: dict[str, object] = {
        "/roster": [_roster_player("001")],
        "/teams": [_team()],
        "/stats/player/season": [_stat("001", "C/ATT", "7/9")],
    }
    calls: dict[str, int] = {path: 0 for path in payloads}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(payloads[request.path])

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
                "player-seasons-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await player_seasons.run(
                    client,
                    season=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {"/roster": 4, "/teams": 4, "/stats/player/season": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_statistic_keys_fail_instead_of_aggregating(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Reject duplicate athlete/category/type observations."""
    statistic = _stat("001", "C/ATT", "7/9")
    payloads: dict[str, object] = {
        "/roster": [_roster_player("001")],
        "/teams": [_team()],
        "/stats/player/season": [statistic, statistic],
    }

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "player-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await player_seasons(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.player_seasons.compose@1")
    assert exc_info.value.category == "ValueError"
