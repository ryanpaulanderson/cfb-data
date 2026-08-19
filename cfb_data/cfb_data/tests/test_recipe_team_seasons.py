"""Validate the independent first-party team-seasons recipe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy, RecipeRun
from cfb_data_recipes.team_seasons import TeamSeason, team_seasons

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _record() -> dict[str, object]:
    """Return one complete records-defined team season."""
    return {
        "year": 2024,
        "teamId": 130,
        "team": "Michigan",
        "classification": "fbs",
        "conference": "Big Ten",
        "division": "",
        "expectedWins": 10.2,
        "total": {"games": 15, "wins": 12, "losses": 3, "ties": 0},
        "conferenceGames": {"games": 10, "wins": 8, "losses": 2, "ties": 0},
        "homeGames": {"games": 8, "wins": 8, "losses": 0, "ties": 0},
        "awayGames": {"games": 6, "wins": 3, "losses": 3, "ties": 0},
        "neutralSiteGames": {"games": 1, "wins": 1, "losses": 0, "ties": 0},
        "regularSeason": {"games": 12, "wins": 10, "losses": 2, "ties": 0},
        "postseason": {"games": 3, "wins": 2, "losses": 1, "ties": 0},
    }


def _season_unit(*, defense: bool) -> dict[str, object]:
    """Return one complete advanced-season unit."""
    passing_downs: dict[str, object] = {
        "rate": 0.3,
        "ppa": 0.2,
        "successRate": 0.35,
        "explosiveness": None,
    }
    if defense:
        passing_downs["totalPPA"] = 12.5
    return {
        "plays": 700,
        "drives": 120,
        "ppa": 0.15,
        "totalPPA": 105.0,
        "successRate": 0.42,
        "explosiveness": 1.1,
        "powerSuccess": None,
        "stuffRate": 0.15,
        "lineYards": 3.0,
        "lineYardsTotal": 1200,
        "secondLevelYards": 0.8,
        "secondLevelYardsTotal": 320,
        "openFieldYards": 0.7,
        "openFieldYardsTotal": 280,
        "totalOpportunies": 55,
        "pointsPerOpportunity": 4.1,
        "fieldPosition": {"averageStart": 70.0, "averagePredictedPoints": 1.2},
        "havoc": {"total": 0.18, "frontSeven": 0.1, "db": 0.08},
        "standardDowns": {
            "rate": 0.7,
            "ppa": 0.1,
            "successRate": 0.46,
            "explosiveness": 0.9,
        },
        "passingDowns": passing_downs,
        "rushingPlays": {
            "rate": 0.55,
            "ppa": 0.12,
            "totalPPA": 46.0,
            "successRate": 0.43,
            "explosiveness": 0.8,
        },
        "passingPlays": {
            "rate": 0.45,
            "ppa": 0.18,
            "totalPPA": 59.0,
            "successRate": 0.41,
            "explosiveness": 1.4,
        },
    }


def _advanced() -> dict[str, object]:
    """Return one complete advanced team season."""
    return {
        "season": 2024,
        "team": "Michigan",
        "conference": "Big Ten",
        "offense": _season_unit(defense=False),
        "defense": _season_unit(defense=True),
    }


def _statistics() -> list[dict[str, object]]:
    """Return ordered heterogeneous conventional statistics."""
    return [
        {
            "season": 2024,
            "team": "Michigan",
            "conference": "Big Ten",
            "statName": "firstDowns",
            "statValue": 210,
        },
        {
            "season": 2024,
            "team": "Michigan",
            "conference": "Big Ten",
            "statName": "timeOfPossession",
            "statValue": "22041",
        },
    ]


@pytest.mark.asyncio
async def test_recipe_uses_records_universe_and_preserves_ordered_statistics(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Attach heterogeneous statistics without pivoting or changing grain."""

    async def handler(request: web.Request) -> web.Response:
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": _statistics(),
            "/stats/season/advanced": [_advanced()],
        }
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await team_seasons(
                client,
                season=2024,
                team="Michigan",
            )

    assert tuple(frame.columns) == tuple(TeamSeason.model_fields)
    assert len(frame) == 1
    assert frame.loc[0, "team_id"] == 130
    assert [item["name"] for item in frame.loc[0, "statistics"]] == [
        "firstDowns",
        "timeOfPossession",
    ]
    assert [item["value"] for item in frame.loc[0, "statistics"]] == [210, "22041"]
    assert frame.loc[0, "advanced"]["defense"]["passing_downs"]["total_ppa"] == 12.5


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical team-season table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {
        "/records": 0,
        "/stats/season": 0,
        "/stats/season/advanced": 0,
    }

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": _statistics(),
            "/stats/season/advanced": [_advanced()],
        }
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
                "team-seasons-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await team_seasons.run(
                    client,
                    season=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {
        "/records": 4,
        "/stats/season": 4,
        "/stats/season/advanced": 4,
    }
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_required_statistical_coverage_fails_closed(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Fail rather than publish a records row missing required statistics."""

    async def handler(request: web.Request) -> web.Response:
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": [],
            "/stats/season/advanced": [_advanced()],
        }
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await team_seasons(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.team_seasons.compose@1")
    assert exc_info.value.category == "ValueError"
