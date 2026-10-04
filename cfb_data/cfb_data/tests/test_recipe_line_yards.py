"""Verify joint College ALY against independent constrained matrix calculations."""

from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from time import monotonic

import numpy as np
import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    ExecutionPolicy,
)
from cfb_data_recipes.line_yards import ALYParameters, line_yards
from cfb_data_recipes.success_rate import success_rate

from cfb_data import CFBDClient, RedisCacheConfig, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _population(
    game: dict[str, object], play: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    games: list[dict[str, object]] = []
    plays: list[dict[str, object]] = []
    for game_id, week, home, away in (
        (1, 1, 10, 20),
        (2, 1, 20, 30),
        (3, 2, 30, 10),
        (4, 2, 10, 20),
    ):
        row = copy.deepcopy(game)
        row.update(
            {
                "id": game_id,
                "week": week,
                "homeId": home,
                "awayId": away,
                "homeTeam": f"Team {home}",
                "awayTeam": f"Team {away}",
                "startDate": f"2024-09-{week * 7:02d}T12:00:00Z",
            }
        )
        games.append(row)
        for number, gain in enumerate((-2, 2, 4, 6, 10, 14), start=1):
            offense, defense = (home, away) if number <= 3 else (away, home)
            event = copy.deepcopy(play)
            event.update(
                {
                    "id": f"{game_id}-{number}",
                    "gameId": game_id,
                    "driveId": f"d{game_id}",
                    "driveNumber": 1,
                    "playNumber": number,
                    "offense": f"Team {offense}",
                    "defense": f"Team {defense}",
                    "home": f"Team {home}",
                    "away": f"Team {away}",
                    "yardsToGoal": 50,
                    "yardsGained": gain + (offense // 10 - 2),
                    "playText": "Runner run",
                    "ppa": None,
                }
            )
            plays.append(event)
    return games, plays


def _independent_fit(
    plays: pd.DataFrame, parameters: ALYParameters
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    terms: list[dict[str, tuple[str, float]]] = []
    for row in plays.itertuples(index=False):
        terms.append(
            {
                "intercept": ("constant", 1.0),
                "offense": (str(row.offense_id), 1.0),
                "defense": (str(row.defense_id), -1.0),
                "situation": ("1:6-10:21-50", 1.0),
                "quarter": ("1", 1.0),
                "clock": ("ordinary", 1.0),
                "venue": (row.venue_perspective, 1.0),
                "score_time": ("tied:1:ordinary", 1.0),
            }
        )
    keys = sorted(
        {(block, value[0]) for term in terms for block, value in term.items()}
    )
    x = np.array(
        [
            [
                term.get(block, ("", 0))[1]
                if term.get(block, ("", 0))[0] == level
                else 0
                for block, level in keys
            ]
            for term in terms
        ]
    )
    y = plays["line_yards"].to_numpy(dtype=float)
    ages = (
        plays["start_date"].max() - plays["start_date"]
    ).dt.total_seconds().to_numpy(dtype=float) / 86400
    weights = (
        np.ones(len(plays))
        if parameters.half_life_days is None
        else 2 ** (-ages / parameters.half_life_days)
    )
    exposure = (x != 0).T @ weights
    blocks = sorted({block for block, _ in keys} - {"intercept"})
    c = np.array(
        [
            [
                exposure[index]
                / sum(exposure[k] for k, key in enumerate(keys) if key[0] == block)
                if key[0] == block
                else 0
                for index, key in enumerate(keys)
            ]
            for block in blocks
        ]
    )
    penalty = np.array(
        [
            0
            if block == "intercept"
            else parameters.team_penalty
            if block in {"offense", "defense"}
            else parameters.context_penalty
            for block, _ in keys
        ]
    )
    system = np.block(
        [
            [x.T @ (weights[:, None] * x) + np.diag(penalty), c.T],
            [c, np.zeros((len(c), len(c)))],
        ]
    )
    solution = np.linalg.solve(system, np.r_[x.T @ (weights * y), np.zeros(len(c))])[
        : len(keys)
    ]
    residual = y - x @ solution
    cluster_scores = np.array(
        [
            x[plays["game_id"].to_numpy() == game_id].T
            @ (weights * residual)[plays["game_id"].to_numpy() == game_id]
            for game_id in plays["game_id"].unique()
        ]
    )
    bread = np.linalg.inv(system)[: len(keys), : len(keys)]
    covariance = (
        bread
        @ cluster_scores.T
        @ cluster_scores
        @ bread.T
        * len(cluster_scores)
        / (len(cluster_scores) - 1)
    )
    return dict(zip(keys, solution, strict=True)), dict(
        zip(keys, np.sqrt(np.maximum(0, np.diag(covariance))), strict=True)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("half_life_days", [None, 28.0])
async def test_joint_aly_and_cluster_uncertainty_match_independent_math(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
    half_life_days: float | None,
) -> None:
    games, plays = _population(game_response, play_response)
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        week = int(request.query.get("week", "0"))
        ids = {row["id"] for row in games if row["week"] == week}
        return web.json_response(
            games
            if request.path == "/games"
            else [row for row in plays if row["gameId"] in ids]
        )

    parameters = ALYParameters(
        team_penalty=16, context_penalty=64, half_life_days=half_life_days
    )
    async with api_server(handler) as url:
        async with CFBDClient(
            "key",
            base_url=url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path),
        ) as client:
            result = await line_yards(
                client, year=2024, weeks=(1, 2), parameters=parameters
            )
    assert set(paths) == {"/games", "/plays"}
    evidence = result["plays"]
    assert isinstance(evidence, pd.DataFrame)
    expected, stderr = _independent_fit(evidence, parameters)
    model = result["model"]
    assert isinstance(model, pd.DataFrame)
    for row in model.itertuples(index=False):
        assert row.estimate == pytest.approx(
            expected[(row.block, row.level)], abs=1e-10
        )
        assert row.cluster_standard_error == pytest.approx(
            stderr[(row.block, row.level)], abs=1e-10
        )
        assert row.equation_residual < 1e-9
    teams = result["team_seasons"]
    assert isinstance(teams, pd.DataFrame)
    ages = (
        evidence["start_date"].max() - evidence["start_date"]
    ).dt.total_seconds().to_numpy(dtype=float) / 86400
    weights = (
        np.ones(len(evidence))
        if half_life_days is None
        else 2 ** (-ages / half_life_days)
    )
    baseline = np.average(
        evidence["yards_gained"].to_numpy(dtype=float), weights=weights
    )
    for row in teams.itertuples(index=False):
        effect = expected[(row.unit, str(row.team_id))]
        assert row.adjusted_line_yards == pytest.approx(
            baseline + (effect if row.unit == "offense" else -effect)
        )
        assert row.coverage == "present"
    assert result["calibration"].iloc[0]["policy"] == "explicit"


@pytest.mark.asyncio
async def test_aly_forward_selection_and_output_filter_keep_full_population(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    games, plays = _population(game_response, play_response)
    queries: list[dict[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        queries.append(dict(request.query))
        week = int(request.query.get("week", "0"))
        ids = {row["id"] for row in games if row["week"] == week}
        return web.json_response(
            games
            if request.path == "/games"
            else [row for row in plays if row["gameId"] in ids]
        )

    candidates = (
        ALYParameters(team_penalty=16, context_penalty=64),
        ALYParameters(team_penalty=128, context_penalty=512, half_life_days=28),
    )
    async with api_server(handler) as url:
        async with CFBDClient(
            "key", base_url=url, analytics=AnalyticsConfig(root=tmp_path)
        ) as client:
            result = await line_yards(
                client, year=2024, weeks=(1, 2), candidates=candidates, team="Team 10"
            )
    calibration = result["calibration"]
    assert isinstance(calibration, pd.DataFrame)
    assert calibration["selected"].sum() == 1
    assert calibration["evaluated_plays"].tolist() == [12, 12]
    assert calibration["folds"].tolist() == [1, 1]
    winner = calibration.sort_values(["mean_squared_error", "candidate_id"]).iloc[0]
    assert winner["selected"]
    evidence = result["plays"]
    for index, candidate in enumerate(candidates):
        expected, _ = _independent_fit(evidence.loc[evidence["week"] == 1], candidate)
        errors: list[float] = []
        for row in evidence.loc[evidence["week"] == 2].itertuples(index=False):
            prediction = (
                expected[("intercept", "constant")]
                + expected[("offense", str(row.offense_id))]
                - expected[("defense", str(row.defense_id))]
                + expected[("venue", row.venue_perspective)]
            )
            errors.append((row.line_yards - prediction) ** 2)
        assert calibration.iloc[index]["mean_squared_error"] == pytest.approx(
            np.mean(errors)
        )
    assert set(result["team_seasons"]["team_id"]) == {10}
    assert set(result["model"].loc[result["model"]["block"] == "offense", "level"]) == {
        "10",
        "20",
        "30",
    }
    assert all("team" not in query for query in queries)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [True, False])
async def test_aly_retains_unavailable_and_excluded_populations(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
    empty: bool,
) -> None:
    games, plays = _population(game_response, play_response)
    for play in plays:
        play["playType"] = "Sack"

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(
            games if request.path == "/games" else [] if empty else plays[:6]
        )

    async with api_server(handler) as url:
        async with CFBDClient(
            "key", base_url=url, analytics=AnalyticsConfig(root=tmp_path)
        ) as client:
            result = await line_yards(
                client,
                year=2024,
                weeks=(1,),
                parameters=ALYParameters(team_penalty=16, context_penalty=64),
            )
    assert result["model"].empty
    assert result["team_seasons"]["adjusted_line_yards"].isna().all()
    assert result["team_seasons"]["evaluated_rushes"].sum() == 0
    assert "unavailable" in set(result["team_seasons"]["coverage"])
    if not empty:
        assert "empty" in set(result["team_seasons"]["coverage"])


@pytest.mark.asyncio
async def test_aly_multipartition_local_dask_and_backend_parity(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    games, plays = _population(game_response, play_response)

    async def handler(request: web.Request) -> web.Response:
        week = int(request.query.get("week", "0"))
        ids = {row["id"] for row in games if row["week"] == week}
        return web.json_response(
            games
            if request.path == "/games"
            else [row for row in plays if row["gameId"] in ids]
        )

    frames: list[dict[str, pd.DataFrame]] = []
    async with api_server(handler) as url:
        for backend, executor in (
            ("pandas", "local"),
            ("polars", "local"),
            ("pandas", "dask"),
            ("polars", "dask"),
        ):
            async with CFBDClient(
                "key",
                base_url=url,
                dataframe_backend=backend,
                analytics=AnalyticsConfig(root=tmp_path / executor),
            ) as client:
                run = await line_yards.run(
                    client,
                    year=2024,
                    weeks=(1, 2),
                    parameters=ALYParameters(team_penalty=16, context_penalty=64),
                    policy=ExecutionPolicy(
                        executor=executor, table_partition_rows=12, dask_max_workers=1
                    ),
                )
                if backend == "pandas":
                    assert any(
                        not node.reused and node.node_kind == "step"
                        for node in run.lineage
                    )
                frames.append(
                    {
                        name: value
                        if isinstance(value, pd.DataFrame)
                        else value.to_pandas()
                        for name, value in run.value.items()
                    }
                )
    for result in frames[1:]:
        for name, expected in frames[0].items():
            pd.testing.assert_frame_equal(
                result[name].convert_dtypes(dtype_backend="pyarrow"),
                expected.convert_dtypes(dtype_backend="pyarrow"),
                check_dtype=False,
                rtol=1e-10,
                atol=1e-10,
            )
    assert not any(
        "different `run_spec`" in record.getMessage() for record in caplog.records
    )


@pytest.mark.asyncio
async def test_aly_no_validation_evidence_selects_no_model(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    games, _ = _population(game_response, play_response)

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(games if request.path == "/games" else [])

    async with api_server(handler) as url:
        async with CFBDClient(
            "key", base_url=url, analytics=AnalyticsConfig(root=tmp_path)
        ) as client:
            result = await line_yards(
                client,
                year=2024,
                weeks=(1, 2),
                candidates=(ALYParameters(team_penalty=16, context_penalty=64),),
            )
    assert result["model"].empty
    assert result["calibration"]["evaluated_plays"].sum() == 0
    assert not result["calibration"]["selected"].any()
    assert result["team_seasons"]["adjusted_line_yards"].isna().all()


@pytest.mark.asyncio
async def test_aly_configuration_fails_before_retrieval(tmp_path: Path) -> None:
    async with CFBDClient("key", analytics=AnalyticsConfig(root=tmp_path)) as client:
        with pytest.raises(CFBDRecipeCompilationError) as caught:
            await line_yards(client, year=2024, weeks=(1,))
        assert isinstance(caught.value.__cause__, ValueError)
        assert "at least two" in str(caught.value.__cause__)


@pytest.mark.redis
@pytest.mark.asyncio
async def test_calculated_recipes_reexecute_from_real_redis(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_response: dict[str, object],
    tmp_path: Path,
) -> None:
    url = os.getenv("CFB_DATA_TEST_REDIS_URL")
    if not url:
        pytest.skip("set CFB_DATA_TEST_REDIS_URL for real Redis integration")
    from redis.asyncio import Redis

    config = RedisCacheConfig(
        url=url, key_prefix=f"cfb-data-derived-test-{uuid.uuid4().hex}"
    )
    games, plays = _population(game_response, play_response)
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        week = int(request.query.get("week", "0"))
        ids = {row["id"] for row in games if row["week"] == week}
        return web.json_response(
            games
            if request.path == "/games"
            else [row for row in plays if row["gameId"] in ids]
        )

    try:
        async with api_server(handler) as base_url:
            records: list[dict[str, object]] = []
            for mode in ("cold", "warm"):
                async with CFBDClient(
                    "key",
                    base_url=base_url,
                    cache=config,
                    analytics=AnalyticsConfig(root=tmp_path / mode),
                ) as client:
                    started = monotonic()
                    with client.cache_mode(
                        "default" if mode == "cold" else "local_only"
                    ):
                        success = await success_rate.run(
                            client,
                            year=2024,
                            weeks=(1, 2),
                            policy=ExecutionPolicy(
                                checkpoint_mode="off", table_partition_rows=4
                            ),
                        )
                        aly = await line_yards.run(
                            client,
                            year=2024,
                            weeks=(1, 2),
                            parameters=ALYParameters(
                                team_penalty=16, context_penalty=64
                            ),
                            policy=ExecutionPolicy(
                                checkpoint_mode="off", table_partition_rows=4
                            ),
                        )
                    attempts = success.actual_http_attempts + aly.actual_http_attempts
                    assert attempts == (3 if mode == "cold" else 0)
                    assert success.reused_nodes == aly.reused_nodes == 0
                    records.append(
                        {
                            "mode": mode,
                            "seconds": monotonic() - started,
                            "attempts": attempts,
                            "digests": {
                                name: artifact.descriptor.content_digest
                                for name, artifact in aly.artifacts.items()
                            },
                        }
                    )
            assert calls == 3
            assert records[0]["digests"] == records[1]["digests"]
            print(records)
    finally:
        redis = Redis.from_url(url)
        try:
            keys = [
                key async for key in redis.scan_iter(match=f"{config.key_prefix}:v1:*")
            ]
            if keys:
                await redis.delete(*keys)
        finally:
            await redis.aclose()
