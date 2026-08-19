"""Validate the independent first-party coach-seasons recipe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy, RecipeRun
from cfb_data_recipes.coach_seasons import CoachSeason, TenureCoverage, coach_seasons

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _record(*, games: int = 15, wins: int = 8, losses: int = 7) -> dict[str, object]:
    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": 0,
        "winPercentage": wins / games if games else None,
    }


def _season() -> dict[str, object]:
    """Return one complete detailed coach season."""
    return {
        **_record(),
        "coach": {"id": 24, "firstName": "Sherrone", "lastName": "Moore"},
        "team": {"id": 130, "school": "Michigan", "conference": "Big Ten"},
        "year": 2024,
        "preseasonRank": 9,
        "postseasonRank": None,
        "srs": 6.11,
        "spOverall": 8.2,
        "spOffense": -1.2,
        "spDefense": 10.4,
        "teamMetrics": {
            "spSpecialTeams": 1.2,
            "strengthOfSchedule": None,
            "secondOrderWins": None,
            "fpi": 7.4,
            "yearOverYear": {"wins": -7, "srs": -15.3, "spOverall": -12.4},
        },
        "recruiting": {"rank": 16, "points": 262.4, "talent": 890.1},
        "pollResume": None,
        "attributionComplete": True,
        "recordSplits": None,
        "scoring": None,
        "cfp": {"appeared": False, "seed": None, "outcome": None},
        "draftFollowingSeason": None,
    }


def _tenure() -> dict[str, object]:
    """Return one matching continuous tenure."""
    return {
        "id": 900,
        "coach": {"id": 24, "firstName": "Sherrone", "lastName": "Moore"},
        "team": {"id": 130, "school": "Michigan"},
        "hireDate": "2024-01-26",
        "startYear": 2024,
        "endYear": None,
        "effectiveStart": "2024-01-26T17:00:00Z",
        "effectiveEnd": None,
        "isInterim": True,
        "active": True,
        "seasons": 1,
        "record": _record(),
        "attributionComplete": True,
    }


@pytest.mark.asyncio
async def test_base_and_tenure_enrichment_preserve_nullable_evidence(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Avoid profile calls and expose optional interim/effective evidence."""
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.json_response(
            [_season()] if request.path == "/coaches/seasons" else [_tenure()]
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "coach-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "base"),
        ) as client:
            base: pd.DataFrame = await coach_seasons(client, year=2024)
        async with CFBDClient(
            "coach-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "enriched"),
        ) as client:
            enriched: pd.DataFrame = await coach_seasons(
                client,
                year=2024,
                include_tenure=True,
            )

    assert "/coaches/profile" not in paths
    assert tuple(base.columns) == tuple(CoachSeason.model_fields)
    assert base.loc[0, "tenure_coverage"] == TenureCoverage.not_requested
    assert pd.isna(base.loc[0, "tenure_id"])
    assert pd.isna(base.loc[0, "poll_resume"])
    assert pd.isna(base.loc[0, "scoring"])
    assert enriched.loc[0, "tenure_coverage"] == TenureCoverage.present
    assert enriched.loc[0, "tenure_id"] == 900
    assert enriched.loc[0, "is_interim"]
    assert enriched.loc[0, "effective_start"].tzinfo is not None


@pytest.mark.asyncio
async def test_requested_tenure_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical coach-season table across every option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {"/coaches/seasons": 0, "/coaches/tenures": 0}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(
            [_season()] if request.path == "/coaches/seasons" else [_tenure()]
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
                "coach-seasons-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await coach_seasons.run(
                    client,
                    year=2024,
                    include_tenure=True,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {"/coaches/seasons": 4, "/coaches/tenures": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_missing_requested_tenure_fails_closed(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Fail requested tenure context rather than publishing partial rows."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [_season()] if request.path == "/coaches/seasons" else []
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "coach-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await coach_seasons(client, year=2024, include_tenure=True)

    assert exc_info.value.node_id.endswith("cfbd.coach_seasons.attach_tenure@1")
    assert exc_info.value.category == "ValueError"
