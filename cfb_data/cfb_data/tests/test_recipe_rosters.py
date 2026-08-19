"""Validate the independent first-party rosters recipe."""

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
from cfb_data_recipes.rosters import RosterMembership, TeamIdentityStatus, rosters

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _roster_player(
    *, athlete_id: str, team: str, recruit_ids: list[str] | None = None
) -> dict[str, object]:
    """Return one complete roster membership fixture."""
    return {
        "id": athlete_id,
        "firstName": "Sample",
        "lastName": "Player",
        "team": team,
        "height": 74.0,
        "weight": 220,
        "jersey": 4,
        "year": 3,
        "position": "QB",
        "homeCity": "Katy",
        "homeState": "TX",
        "homeCountry": "USA",
        "homeLatitude": 29.7858,
        "homeLongitude": -95.8245,
        "homeCountyFIPS": "48201",
        "recruitIds": recruit_ids,
    }


def _team(team_id: int, school: str, aliases: list[str] | None) -> dict[str, object]:
    """Return one complete temporal team-identity fixture."""
    return {
        "id": team_id,
        "school": school,
        "mascot": None,
        "abbreviation": None,
        "alternateNames": aliases,
        "conference": "Big Ten",
        "division": None,
        "classification": "fbs",
        "color": None,
        "alternateColor": None,
        "logos": None,
        "twitter": None,
        "location": None,
    }


@pytest.mark.asyncio
async def test_recipe_records_resolved_unresolved_and_ambiguous_identity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Retain every membership while making identity uncertainty explicit."""
    roster_payload = [
        _roster_player(
            athlete_id="009", team="Penn State", recruit_ids=["70001", "70002"]
        ),
        _roster_player(athlete_id="010", team="Unknown College"),
        _roster_player(athlete_id="011", team="State"),
    ]
    team_payload = [
        _team(213, "Penn State", ["PSU", "State"]),
        _team(999, "Example State", ["State"]),
    ]

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/roster":
            assert request.query == {"team": "Penn State", "year": "2024"}
            return web.json_response(roster_payload)
        assert request.path == "/teams"
        assert request.query == {"year": "2024"}
        return web.json_response(team_payload)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "rosters-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await rosters(
                client,
                season=2024,
                team="Penn State",
            )

    assert tuple(frame.columns) == tuple(RosterMembership.model_fields)
    assert frame["athlete_id"].tolist() == ["009", "011", "010"]
    assert frame["team_identity_status"].tolist() == [
        TeamIdentityStatus.resolved,
        TeamIdentityStatus.ambiguous,
        TeamIdentityStatus.unresolved,
    ]
    assert frame["team_id"].tolist()[0] == 213
    assert frame.loc[1, "team_identity_candidate_ids"] == [213, 999]
    assert frame.loc[2, "team_identity_candidate_ids"] == []
    assert frame.loc[0, "recruit_ids"] == ["70001", "70002"]


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical membership table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    roster_payload = [_roster_player(athlete_id="009", team="PSU")]
    team_payload = [_team(213, "Penn State", ["PSU"])]
    calls: dict[str, int] = {"/roster": 0, "/teams": 0}

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        return web.json_response(
            roster_payload if request.path == "/roster" else team_payload
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
                "rosters-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await rosters.run(
                    client,
                    season=2024,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))

    assert calls == {"/roster": 4, "/teams": 4}
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_duplicate_memberships_fail_instead_of_deduplicating(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Reject duplicate season/team/athlete keys at the dataset boundary."""
    player = _roster_player(athlete_id="009", team="Penn State")

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            [copy.deepcopy(player), copy.deepcopy(player)]
            if request.path == "/roster"
            else [_team(213, "Penn State", None)]
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "rosters-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await rosters(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.rosters@1")
    assert exc_info.value.category == "ValueError"
