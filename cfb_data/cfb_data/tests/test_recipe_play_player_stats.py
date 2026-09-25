"""Exercise complete play-player-stat retrieval through the public recipe."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AdaptiveSourceContext,
    AnalyticsConfig,
    CFBDRecipeCompilationError,
    CFBDRunError,
    ExecutionPolicy,
    RecipeRef,
    RecipeRun,
    adaptive_source,
    dataset,
)
from cfb_data.games._operations import GAMES_LIST
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.plays._operations import PLAYS_STATS
from cfb_data_recipes.play_player_stats import play_player_stats

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy, SQLiteCacheConfig

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _game(response: dict[str, object], game_id: int) -> dict[str, object]:
    """Return a game fixture with the play-stat fixture's participants."""
    game = copy.deepcopy(response)
    game["id"] = game_id
    game["homeTeam"] = "Michigan"
    game["awayTeam"] = "Fresno State"
    return game


def _stat(
    response: dict[str, object],
    ordinal: int,
    *,
    team: str = "Michigan",
    stat_type: str = "Interception",
) -> dict[str, object]:
    """Return one distinct source row in a game-team-type partition."""
    row = copy.deepcopy(response)
    row["playId"] = f"play-{ordinal:04d}"
    row["team"] = team
    row["opponent"] = "Fresno State" if team == "Michigan" else "Michigan"
    row["statType"] = stat_type
    return row


@pytest.mark.asyncio
async def test_uncapped_game_is_source_faithful_and_plan_is_bounded(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Return the direct partition and expose the adaptive request ceiling."""
    game_id = 401628452
    game = _game(game_response, game_id)
    stat = _stat(play_stat_response, 1)
    paths: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        paths.append(request.path)
        if request.path == "/games":
            return web.json_response([game])
        if request.path == "/plays/stats":
            return web.json_response([stat])
        raise AssertionError(f"Unexpected route {request.path}")

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            plan = await play_player_stats.plan(client, game_ids=(game_id,))
            assert plan.worst_case_http_attempts == 100
            assert plan.diagnostics
            assert any(
                node.allowed_operations
                == (
                    "cfbd.games.list",
                    "cfbd.plays.stats",
                    "cfbd.plays.stat_types",
                )
                for node in plan.nodes
            )
            assert not paths
            inspection = await play_player_stats.inspect(client, game_ids=(game_id,))
            assert "deferred" in inspection.source_dispositions.values()
            assert not paths
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )

    assert paths == ["/games", "/plays/stats"]
    assert isinstance(run.value, pd.DataFrame)
    assert len(run.value) == 1
    assert run.value.loc[0, "athlete_name"] == stat["athleteName"]
    assert run.actual_http_attempts == 2
    assert run.source_coverage[0].state == "present"


@pytest.mark.asyncio
async def test_explicit_game_list_merges_in_stable_game_order(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Expand supplied game IDs at planning and sort independent partitions."""
    ids = (401628453, 401628452)
    requested_games: list[int] = []

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            game_id = int(request.query["id"])
            requested_games.append(game_id)
            return web.json_response([_game(game_response, game_id)])
        game_id = int(request.query["gameId"])
        row = _stat(play_stat_response, 1)
        row["gameId"] = game_id
        return web.json_response([row])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRecipeCompilationError):
                await play_player_stats.plan(
                    client,
                    game_ids=ids,
                    policy=ExecutionPolicy(max_http_attempts=3),
                )
            assert not requested_games
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=ids
            )

    assert set(requested_games) == set(ids)
    assert run.value["game_id"].tolist() == sorted(ids)
    assert run.actual_http_attempts == 4


@pytest.mark.asyncio
async def test_game_cap_splits_by_both_teams(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Include all rows when an exact-game response reaches the cap."""
    game_id = 401628452
    game = _game(game_response, game_id)
    home = [_stat(play_stat_response, index) for index in range(1_000)]
    away = [
        _stat(play_stat_response, index + 1_000, team="Fresno State")
        for index in range(1_000)
    ]
    selectors: list[str | None] = []

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        if request.path == "/plays/stats":
            team = request.query.get("team")
            selectors.append(team)
            if team == "Michigan":
                return web.json_response(home)
            if team == "Fresno State":
                return web.json_response(away)
            return web.json_response(home + away)
        raise AssertionError(f"Unexpected route {request.path}")

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=[game_id]
            )

    assert selectors == [None, "Michigan", "Fresno State"]
    assert len(run.value) == 2_000
    assert run.actual_http_attempts == 4


@pytest.mark.asyncio
async def test_team_cap_splits_by_every_stat_type(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Use the authoritative vocabulary when a team partition is capped."""
    game_id = 401628452
    game = _game(game_response, game_id)
    first = [_stat(play_stat_response, index, stat_type="A") for index in range(1_000)]
    second = [
        _stat(play_stat_response, index + 1_000, stat_type="B")
        for index in range(1_000)
    ]
    requested_types: list[str | None] = []

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        if request.path == "/plays/stats/types":
            return web.json_response([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
        if request.path == "/plays/stats":
            team = request.query.get("team")
            stat_type_id = request.query.get("statTypeId")
            requested_types.append(stat_type_id)
            if team == "Fresno State":
                return web.json_response([])
            if stat_type_id == "1":
                return web.json_response(first)
            if stat_type_id == "2":
                return web.json_response(second)
            return web.json_response(first + second)
        raise AssertionError(f"Unexpected route {request.path}")

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )

    assert requested_types == [None, None, "1", "2", None]
    assert len(run.value) == 2_000
    assert run.actual_http_attempts == 7


@pytest.mark.asyncio
async def test_irreducible_partition_returns_warned_partial_artifact(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Preserve capped leaf rows with durable, visible partial coverage."""
    game_id = 401628452
    game = _game(game_response, game_id)
    rows = [_stat(play_stat_response, index, stat_type="A") for index in range(2_000)]

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        if request.path == "/plays/stats/types":
            return web.json_response([{"id": 1, "name": "A"}])
        if request.path == "/plays/stats":
            if request.query.get("team") == "Fresno State":
                return web.json_response([])
            return web.json_response(rows)
        raise AssertionError(f"Unexpected route {request.path}")

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )
            repeated: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )

    assert len(run.value) == 2_000
    assert run.source_coverage[0].state == "partial"
    assert len(run.warnings) == 1
    assert "2,000-row API limit" in run.warnings[0]
    assert run.value["coverage_state"].eq("partial").all()
    assert run.value["coverage_warning"].eq(run.warnings[0]).all()
    loaded = run.artifact.load()
    assert loaded["coverage_state"].eq("partial").all()
    assert loaded["coverage_warning"].eq(run.warnings[0]).all()
    assert repeated.source_coverage[0].state == "partial"
    assert repeated.warnings == run.warnings
    assert repeated.source_coverage[0].row_count == 2_000
    assert (
        repeated.artifact.descriptor.content_digest
        == run.artifact.descriptor.content_digest
    )
    assert not any(
        node.reused for node in repeated.lineage if node.node_kind == "source"
    )


@pytest.mark.asyncio
async def test_partial_game_does_not_mark_another_game_partial(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep per-game coverage distinct in one merged artifact."""
    partial_id = 401628452
    complete_id = 401628453
    capped = [_stat(play_stat_response, index, stat_type="A") for index in range(2_000)]
    complete = _stat(play_stat_response, 2_001)
    complete["gameId"] = complete_id

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            game_id = int(request.query["id"])
            return web.json_response([_game(game_response, game_id)])
        if request.path == "/plays/stats/types":
            return web.json_response([{"id": 1, "name": "A"}])
        if request.query["gameId"] == str(complete_id):
            return web.json_response([complete])
        if request.query.get("team") == "Fresno State":
            return web.json_response([])
        return web.json_response(capped)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(complete_id, partial_id)
            )

    states = run.value.groupby("game_id")["coverage_state"].unique().to_dict()
    assert states[partial_id].tolist() == ["partial"]
    assert states[complete_id].tolist() == ["complete"]
    assert (
        run.value.loc[run.value.game_id == complete_id, "coverage_warning"].isna().all()
    )
    assert len(run.warnings) == 1
    assert str(partial_id) in run.warnings[0]
    assert {coverage.state for coverage in run.source_coverage} == {
        "partial",
        "present",
    }


@pytest.mark.asyncio
async def test_invalid_game_list_fails_before_io() -> None:
    """Reject empty, duplicate, and invalid IDs while compiling."""
    client = CFBDClient("test-key")
    for ids in ([], [1, 1], [0], [True], ["1"]):
        with pytest.raises((CFBDRecipeCompilationError, ValueError)):
            await play_player_stats.plan(client, game_ids=ids)


@pytest.mark.asyncio
async def test_adaptive_source_rejects_undeclared_operation_before_io(
    tmp_path: Path,
) -> None:
    """Enforce the source's endpoint allowlist at the coordinator boundary."""

    @adaptive_source(
        id="tests.play_stats_undeclared_operation",
        revision=1,
        output=Game,
        operations=(GAMES_LIST,),
        base_requests=1,
    )
    async def invalid(context: AdaptiveSourceContext) -> list[Game]:
        await context.retrieve(PLAYS_STATS, game_id=1)
        return []

    @dataset(
        id="tests.play_stats_undeclared_dataset",
        revision=1,
        row=Game,
        grain="one game",
        keys=("id",),
        order_by=("id",),
    )
    def invalid_dataset() -> RecipeRef[list[Game]]:
        return invalid()

    async with CFBDClient(
        "test-key", analytics=AnalyticsConfig(root=tmp_path / "analytics")
    ) as client:
        with pytest.raises(CFBDRunError) as failure:
            await invalid_dataset.run(client)

    assert failure.value.category == "CFBDRecipeUsageError"


@pytest.mark.asyncio
async def test_capped_parent_must_be_covered_by_child_partitions(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Fail if a truncated parent contains a row absent from both team parts."""
    game_id = 401628452
    game = _game(game_response, game_id)
    rows = [_stat(play_stat_response, index) for index in range(2_000)]

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        if request.query.get("team") == "Michigan":
            return web.json_response(rows[:-1])
        if request.query.get("team") == "Fresno State":
            return web.json_response([])
        return web.json_response(rows)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as failure:
                await play_player_stats.run(client, game_ids=(game_id,))

    assert failure.value.category == "ValueError"
    assert "partitions disagree" in str(failure.value.__cause__)


@pytest.mark.asyncio
async def test_empty_stats_are_valid_but_missing_game_fails(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Distinguish a real game without stats from an unknown game ID."""
    game_id = 401628452
    game = _game(game_response, game_id)

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response(
                [game] if request.query.get("id") == str(game_id) else []
            )
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            empty: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )
            with pytest.raises(CFBDRunError) as missing:
                await play_player_stats.run(client, game_ids=(game_id + 1,))

    assert empty.value.empty
    assert empty.source_coverage[0].state == "empty"
    assert missing.value.category == "ValueError"


@pytest.mark.asyncio
async def test_mismatch_and_duplicate_key_fail(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject an out-of-game response and ambiguous association grain."""
    game_id = 401628452
    game = _game(game_response, game_id)
    stat = _stat(play_stat_response, 1)
    rows = [dict(stat, gameId=game_id + 1)]

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        return web.json_response(rows)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as mismatch:
                await play_player_stats.run(client, game_ids=(game_id,))
            rows[:] = [stat, dict(stat, stat=2)]
            with pytest.raises(CFBDRunError) as duplicate:
                await play_player_stats.run(client, game_ids=(game_id,))

    assert mismatch.value.category == "ValueError"
    assert duplicate.value.category == "ValueError"


@pytest.mark.asyncio
async def test_attempt_budget_stops_conditional_requests(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Return validated samples if the ceiling blocks a conditional request."""
    game_id = 401628452
    game = _game(game_response, game_id)
    rows = [_stat(play_stat_response, index) for index in range(2_000)]
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        if request.path == "/games":
            return web.json_response([game])
        if request.query.get("team") == "Fresno State":
            return web.json_response([])
        return web.json_response(rows)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRecipeCompilationError):
                await play_player_stats.plan(
                    client,
                    game_ids=(game_id,),
                    policy=ExecutionPolicy(max_http_attempts=1),
                )
            assert calls == 0
            partial: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client,
                game_ids=(game_id,),
                policy=ExecutionPolicy(max_http_attempts=2),
            )

    assert calls == 2
    assert partial.actual_http_attempts == 2
    assert len(partial.value) == 2_000
    assert partial.source_coverage[0].state == "partial"
    assert partial.value["coverage_state"].eq("partial").all()
    assert "attempt budget 2" in partial.warnings[0]


@pytest.mark.asyncio
async def test_retries_are_counted_within_adaptive_source(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Count a transient failure and its successful retry in the run ledger."""
    game_id = 401628452
    game = _game(game_response, game_id)
    stat = _stat(play_stat_response, 1)
    stat_calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal stat_calls
        if request.path == "/games":
            return web.json_response([game])
        stat_calls += 1
        if stat_calls == 1:
            return web.Response(status=503)
        return web.json_response([stat])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )

    assert stat_calls == 2
    assert run.actual_http_attempts == 3
    assert len(run.value) == 1


@pytest.mark.asyncio
async def test_same_output_across_backends_and_executors(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Preserve content and order across the four supported execution paths."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    game_id = 401628452
    game = _game(game_response, game_id)
    rows = [_stat(play_stat_response, 2), _stat(play_stat_response, 1)]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game] if request.path == "/games" else rows)

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "test-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                    client,
                    game_ids=(game_id,),
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            assert run.artifact.load().loc[0, "play_id"] == "play-0001"

    assert len(set(digests)) == 1


@pytest.mark.asyncio
async def test_cached_response_reuses_validated_source(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reuse response-cache entries without new HTTP attempts."""
    game_id = 401628452
    game = _game(game_response, game_id)
    stat = _stat(play_stat_response, 1)
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game] if request.path == "/games" else [stat])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            cache=SQLiteCacheConfig(path=tmp_path / "responses.sqlite3"),
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            first: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )
            second: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,)
            )

    assert calls == 2
    assert first.actual_http_attempts == 2
    assert second.actual_http_attempts == 0


@pytest.mark.asyncio
async def test_failed_source_can_resume_after_upstream_correction(
    api_server: ServerFactory,
    game_response: dict[str, object],
    play_stat_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Retry a failed source without carrying forward its invalid rows."""
    game_id = 401628452
    game = _game(game_response, game_id)
    stat = _stat(play_stat_response, 1)
    corrected = False

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        return web.json_response([stat if corrected else dict(stat, gameId=1)])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as failure:
                await play_player_stats.run(client, game_ids=(game_id,))
            corrected = True
            resumed: RecipeRun[pd.DataFrame] = await play_player_stats.run(
                client, game_ids=(game_id,), resume_from=failure.value.run_id
            )

    assert resumed.parent_run_id == failure.value.run_id
    assert resumed.actual_http_attempts == 2
    assert resumed.value.loc[0, "game_id"] == game_id


@pytest.mark.asyncio
async def test_cancellation_releases_inflight_retrieval(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Cancel a waiting source without publishing an incomplete artifact."""
    game_id = 401628452
    game = _game(game_response, game_id)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        if request.path == "/games":
            return web.json_response([game])
        entered.set()
        await release.wait()
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "test-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            task: asyncio.Task[RecipeRun[pd.DataFrame]] = asyncio.create_task(
                play_player_stats.run(client, game_ids=(game_id,))
            )
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
