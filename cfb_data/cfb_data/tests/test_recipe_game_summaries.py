"""Validate the independent first-party game-summary recipe."""

from __future__ import annotations

import copy
from collections.abc import Callable
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
    RecipeRun,
)
from cfb_data_recipes.game_summaries import (
    GameEnrichmentCoverage,
    GameResultState,
    GameSummary,
    game_summaries,
)

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _game_payloads(game_response: dict[str, object]) -> list[dict[str, object]]:
    """Return future, tied, and decided games in deliberately unstable order."""
    decided = copy.deepcopy(game_response)
    decided["id"] = 3

    tied = copy.deepcopy(game_response)
    tied.update({"id": 2, "homePoints": 21, "awayPoints": 21})

    future = copy.deepcopy(game_response)
    future.update(
        {
            "id": 1,
            "completed": False,
            "homePoints": None,
            "awayPoints": None,
            "homeLineScores": None,
            "awayLineScores": None,
        }
    )
    return [decided, future, tied]


def _media_payload() -> dict[str, object]:
    """Return one source-shaped broadcast for the shared game fixture."""
    return {
        "id": 401628347,
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startTime": "2024-08-31T23:30:00Z",
        "isStartTimeTBD": False,
        "homeTeam": "Alabama",
        "homeConference": "SEC",
        "awayTeam": "Western Kentucky",
        "awayConference": None,
        "mediaType": "tv",
        "outlet": "ESPN",
    }


def _weather_payload() -> dict[str, object]:
    """Return one source-shaped weather observation for the game fixture."""
    return {
        "id": 401628347,
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startTime": "2024-08-31T23:30:00Z",
        "gameIndoors": False,
        "homeTeam": "Alabama",
        "homeConference": "SEC",
        "awayTeam": "Western Kentucky",
        "awayConference": None,
        "venueId": 365,
        "venue": "Bryant-Denny Stadium",
        "temperature": 84.0,
        "dewPoint": 70.0,
        "humidity": 58.0,
        "precipitation": 0.0,
        "snowfall": 0.0,
        "windDirection": 180.0,
        "windSpeed": 8.0,
        "pressure": 29.9,
        "weatherConditionCode": 2.0,
        "weatherCondition": "Partly cloudy",
    }


@pytest.mark.asyncio
async def test_recipe_preserves_source_fields_and_conservative_results(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Derive results only from completed games with both reported scores."""
    payloads = _game_payloads(game_response)

    async def handler(request: web.Request) -> web.Response:
        assert request.path == "/games"
        assert request.query == {"year": "2024", "team": "Penn State"}
        return web.json_response(payloads)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "game-summary-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await game_summaries.run(
                client,
                year=2024,
                team="Penn State",
            )

    frame = run.value
    assert isinstance(frame, pd.DataFrame)
    assert tuple(frame.columns) == tuple(GameSummary.model_fields)
    assert "id" not in frame.columns
    assert frame["game_id"].tolist() == [1, 2, 3]
    assert pd.isna(frame.loc[0, "result_state"])
    assert pd.isna(frame.loc[0, "total_points"])
    assert pd.isna(frame.loc[0, "margin"])
    assert pd.isna(frame.loc[0, "winner_id"])
    assert pd.isna(frame.loc[0, "loser_id"])
    assert frame.loc[1, "result_state"] == GameResultState.tie
    assert frame.loc[1, "total_points"] == 42
    assert frame.loc[1, "margin"] == 0
    assert pd.isna(frame.loc[1, "winner_id"])
    assert pd.isna(frame.loc[1, "loser_id"])
    assert frame.loc[2, "result_state"] == GameResultState.home_win
    assert frame.loc[2, "total_points"] == 63
    assert frame.loc[2, "margin"] == 63
    assert frame.loc[2, "winner_id"] == 333
    assert frame.loc[2, "loser_id"] == 2459
    assert (
        frame["media_coverage"].tolist()
        == [
            GameEnrichmentCoverage.not_requested,
        ]
        * 3
    )
    assert (
        frame["weather_coverage"].tolist()
        == [
            GameEnrichmentCoverage.not_requested,
        ]
        * 3
    )
    assert run.artifact.descriptor.output_id == "cfbd.game_summaries"
    assert run.artifact.descriptor.output_revision == 2


@pytest.mark.asyncio
async def test_recipe_is_portable_across_frame_and_executor_options(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Produce identical canonical content in all four supported combinations."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls = 0
    payloads = _game_payloads(game_response)

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response(payloads)

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    records: list[list[dict[str, object]]] = []
    dask_placements: list[tuple[str, ...]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "game-summary-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await game_summaries.run(
                    client,
                    year=2024,
                    policy=ExecutionPolicy(
                        executor=executor,
                        dask_max_workers=1,
                    ),
                )
            digests.append(run.artifact.descriptor.content_digest)
            records.append(run.artifact.load().to_dict(orient="records"))
            if executor == "dask":
                dask_placements.append(tuple(item.placement for item in run.lineage))

    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])
    assert calls == 4
    assert all(
        placements == ("coordinator", "dask", "coordinator")
        for placements in dask_placements
    )


@pytest.mark.asyncio
async def test_exact_game_enrichments_are_late_bound_and_four_way_portable(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Attach exact-game media and weather through every supported option."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    payloads: dict[str, object] = {
        "/games": [game_response],
        "/games/media": [_media_payload()],
        "/games/weather": [_weather_payload()],
    }
    calls: dict[str, int] = dict.fromkeys(payloads, 0)

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        if request.path == "/games":
            assert request.query == {"id": "401628347"}
        elif request.path == "/games/media":
            assert request.query == {
                "year": "2024",
                "week": "1",
                "team": "Alabama",
            }
        else:
            assert request.query == {"gameId": "401628347"}
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
                "game-summary-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(
                    root=tmp_path / f"enriched-{backend}-{executor}"
                ),
            ) as client:
                plan = await game_summaries.plan(
                    client,
                    game_id=401628347,
                    include_media=True,
                    include_weather=True,
                )
                run: RecipeRun[pd.DataFrame] = await game_summaries.run(
                    client,
                    game_id=401628347,
                    include_media=True,
                    include_weather=True,
                    policy=ExecutionPolicy(
                        executor=executor,
                        dask_max_workers=1,
                    ),
                )

            assert plan.worst_case_http_attempts == 3
            media_node = next(
                node for node in plan.nodes if "cfbd.games.media" in node.node_id
            )
            assert media_node.deferred_parameters == ("year", "week", "team")
            restored = run.artifact.load()
            assert restored["game_id"].tolist() == [401628347]
            assert restored["media_coverage"].tolist() == [
                GameEnrichmentCoverage.present
            ]
            assert restored["weather_coverage"].tolist() == [
                GameEnrichmentCoverage.present
            ]
            assert restored.loc[0, "media"][0]["outlet"] == "ESPN"
            assert restored.loc[0, "weather"]["temperature"] == 84.0
            digests.append(run.artifact.descriptor.content_digest)
            records.append(restored.to_dict(orient="records"))

    assert calls == dict.fromkeys(payloads, 4)
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_empty_requested_game_enrichments_are_explicit(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Represent valid-empty media and weather without shrinking games."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response] if request.path == "/games" else [])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "game-summary-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "empty-enrichments"),
        ) as client:
            frame: pd.DataFrame = await game_summaries(
                client,
                year=2024,
                team="Alabama",
                include_media=True,
                include_weather=True,
            )

    assert frame["game_id"].tolist() == [401628347]
    assert frame["media_coverage"].tolist() == [GameEnrichmentCoverage.empty]
    assert frame["media"].tolist() == [[]]
    assert frame["weather_coverage"].tolist() == [GameEnrichmentCoverage.empty]
    assert frame["weather"].tolist() == [None]


@pytest.mark.asyncio
async def test_duplicate_game_media_fail_without_changing_base_rows(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject duplicate media identity instead of selecting one broadcast."""
    duplicate_media = _media_payload()

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game_response])
        return web.json_response([duplicate_media, duplicate_media])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "game-summary-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "duplicate-media"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await game_summaries(
                    client,
                    year=2024,
                    team="Alabama",
                    include_media=True,
                )

    assert exc_info.value.node_id.endswith("cfbd.game_summaries.attach_enrichments@1")
    assert exc_info.value.category == "ValueError"


@pytest.mark.asyncio
async def test_media_rejects_unrepresentable_selectors_during_planning() -> None:
    """Reject selector combinations the media route cannot preserve exactly."""
    client = CFBDClient("game-summary-key")

    with pytest.raises(CFBDRecipeCompilationError, match="builder failed"):
        await game_summaries.plan(
            client,
            year=2024,
            home="Alabama",
            include_media=True,
        )


@pytest.mark.asyncio
async def test_recipe_plan_validates_the_endpoint_selector_contract() -> None:
    """Reject missing year and game ID without network or artifact work."""
    client = CFBDClient("game-summary-key")

    with pytest.raises(CFBDRecipeCompilationError, match="endpoint contract"):
        await game_summaries.plan(client, team="Penn State")
