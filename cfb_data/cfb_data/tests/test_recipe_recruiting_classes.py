"""Validate the independent first-party recruiting-classes recipe."""

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
from cfb_data_recipes.recruiting_classes import (
    RecruitingClass,
    RecruitingClassStatus,
    recruiting_classes,
)

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _ranking(team: str, rank: int) -> dict[str, object]:
    """Return one team class ranking."""
    return {"year": 2024, "rank": rank, "team": team, "points": 250.5}


def _recruit(recruit_id: str, committed_to: str | None) -> dict[str, object]:
    """Return one complete individual recruit."""
    return {
        "id": recruit_id,
        "athleteId": None,
        "recruitType": "HighSchool",
        "year": 2024,
        "ranking": 10,
        "name": f"Recruit {recruit_id}",
        "school": "Example High",
        "committedTo": committed_to,
        "position": "QB",
        "height": 74.0,
        "weight": 205,
        "stars": 4,
        "rating": 0.95,
        "city": "Example",
        "stateProvince": "PA",
        "country": "USA",
        "hometownInfo": {"latitude": None, "longitude": None, "fipsCode": None},
    }


@pytest.mark.asyncio
async def test_recipe_unions_ranked_commitment_only_and_uncommitted_classes(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Retain every source population without using recruiting aggregates."""
    paths: list[str] = []
    payloads: dict[str, object] = {
        "/recruiting/teams": [
            _ranking("Penn State", 5),
            _ranking("Ranked Without Commits", 20),
        ],
        "/recruiting/players": [
            _recruit("001", "Penn State"),
            _recruit("002", "Commitments Only"),
            _recruit("003", None),
        ],
    }

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "recruiting-classes-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await recruiting_classes(client, class_year=2024)

    assert set(paths) == {"/recruiting/teams", "/recruiting/players"}
    assert "/recruiting/groups" not in paths
    assert tuple(frame.columns) == tuple(RecruitingClass.model_fields)
    assert frame["status"].tolist() == [
        RecruitingClassStatus.ranked,
        RecruitingClassStatus.ranked,
        RecruitingClassStatus.commitments_only,
        RecruitingClassStatus.uncommitted,
    ]
    assert frame["source_team"].tolist()[:3] == [
        "Penn State",
        "Ranked Without Commits",
        "Commitments Only",
    ]
    assert pd.isna(frame.loc[3, "source_team"])
    assert frame["recruit_count"].tolist() == [1, 0, 1, 1]


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical recruiting-class table across all options."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payloads: dict[str, object] = {
        "/recruiting/teams": [_ranking("Penn State", 5)],
        "/recruiting/players": [_recruit("001", "Penn State")],
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
                "recruiting-classes-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await recruiting_classes.run(
                    client,
                    class_year=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {"/recruiting/teams": 4, "/recruiting/players": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_recruit_ids_fail_instead_of_counting_twice(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Reject duplicate individual recruit identity."""
    recruit = _recruit("001", "Penn State")
    payloads: dict[str, object] = {
        "/recruiting/teams": [_ranking("Penn State", 5)],
        "/recruiting/players": [recruit, copy.deepcopy(recruit)],
    }

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "recruiting-classes-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await recruiting_classes(client, class_year=2024)

    assert exc_info.value.node_id.endswith("cfbd.recruiting_classes.compose@1")
    assert exc_info.value.category == "ValueError"
