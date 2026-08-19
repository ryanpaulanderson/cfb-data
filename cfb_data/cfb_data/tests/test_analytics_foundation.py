"""Test durable analytical products through the installed public client."""

import asyncio
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.analytics._models import GameSummary
from cfb_data.base.types import JSONValue
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.observability import RetrievalStarted
from pydantic import BaseModel, ConfigDict, Field

from cfb_data import (
    AnalyticsConfig,
    AnalyticsStats,
    CFBDArtifactError,
    CFBDClient,
    CFBDRunError,
    CheckpointMode,
    DatasetCatalog,
    DatasetDefinition,
    ExecutionPolicy,
    ParameterBinding,
    RegisteredTransform,
    TableContract,
    TransformBackend,
    TransformNode,
    TransformRegistry,
    loads_yaml_definition,
    registered_source,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


@pytest.mark.asyncio
async def test_all_curated_products_plan_without_io_or_store_writes(
    tmp_path: Path,
) -> None:
    """Compile all twelve datasets and three workflows without side effects."""
    root = tmp_path / "analytics"
    client = CFBDClient("key", analytics=AnalyticsConfig(path=root))
    specifications: dict[str, Mapping[str, object]] = {
        "cfbd.game_summaries": {"year": 2024},
        "cfbd.team_games": {"year": 2024, "team": "Penn State"},
        "cfbd.player_game_stats": {"year": 2024, "team": "Penn State"},
        "cfbd.drives": {"year": 2024, "team": "Penn State"},
        "cfbd.plays": {"year": 2024, "week": 1},
        "cfbd.rosters": {"season": 2024, "team": "Penn State"},
        "cfbd.team_seasons": {"season": 2024, "team": "Penn State"},
        "cfbd.player_seasons": {"season": 2024, "team": "Penn State"},
        "cfbd.poll_rankings": {"season": 2024},
        "cfbd.betting_lines": {"game_id": 401628515},
        "cfbd.recruiting_classes": {
            "class_year": 2024,
            "team": "Penn State",
        },
        "cfbd.coach_seasons": {"year": 2024, "team": "Penn State"},
    }

    for definition_id, parameters in specifications.items():
        plan = await client.datasets.plan(definition_id, params=parameters)
        assert plan.definition_id == definition_id
        assert plan.steps
        assert plan.worst_case_http_attempts <= 100

    workflow_specs: dict[str, Mapping[str, object]] = {
        "cfbd.team_season_analysis": {"season": 2024, "team": "Penn State"},
        "cfbd.single_game_analysis": {"game_id": 401628515},
        "cfbd.program_history": {
            "team": "Penn State",
            "start_year": 2024,
            "end_year": 2024,
        },
    }
    for definition_id, parameters in workflow_specs.items():
        plan = await client.workflows.plan(definition_id, params=parameters)
        assert plan.definition_id == definition_id
        assert plan.outputs
        assert plan.worst_case_http_attempts <= 100
        assert (
            plan.logical_source_requests
            == {
                "cfbd.team_season_analysis": 9,
                "cfbd.single_game_analysis": 6,
                "cfbd.program_history": 9,
            }[definition_id]
        )

    assert not root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_game_summaries_are_durable_and_backend_neutral(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    backend: str,
) -> None:
    """Validate simple/advanced parity, checkpoint reuse, and detached loading."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        assert request.path == "/games"
        return web.json_response([game_response])

    stats = AnalyticsStats()
    retrieval_events: list[object] = []
    root = tmp_path / backend
    async with api_server(handler) as base_url:
        client = CFBDClient(
            "key",
            dataframe_backend=backend,
            base_url=base_url,
            observer=retrieval_events.append,
            analytics=AnalyticsConfig(path=root, observer=stats),
        )
        async with client:
            first = await client.datasets.run(
                "cfbd.game_summaries", params={"year": 2024}
            )
            second = await client.datasets.run(
                "cfbd.game_summaries", params={"year": 2024}
            )
            descriptors = await client.datasets.list_artifacts()
            inspected = await client.datasets.inspect_artifact(
                second.artifact.descriptor.artifact_id
            )
            await client.datasets.pin_artifact(inspected.artifact_id)
            runs = await client.datasets.list_runs(definition_id="cfbd.game_summaries")
            inspected_run = await client.datasets.inspect_run(second.run_id)

    assert calls == 2
    assert first.artifact.descriptor.row_count == 1
    assert first.artifact.descriptor.source_fetched_at is None
    assert second.reused_steps == ("result",)
    assert descriptors
    assert inspected == second.artifact.descriptor
    assert {item.run_id for item in runs} == {first.run_id, second.run_id}
    assert inspected_run.status == "success"
    assert first.artifact.load_table().num_rows == 1
    detached = first.artifact.load(dataframe_backend=backend)
    assert list(detached.columns) == list(GameSummary.model_fields)
    if backend == "pandas":
        assert isinstance(first.frame, pd.DataFrame)
        assert first.frame.loc[0, "home_margin"] == 63
    else:
        assert isinstance(first.frame, pl.DataFrame)
        assert first.frame["home_margin"][0] == 63
    snapshot = stats.snapshot()
    assert snapshot.runs == 2
    assert snapshot.successful_runs == 2
    assert snapshot.reused_steps == 1
    correlated = [
        event for event in retrieval_events if isinstance(event, RetrievalStarted)
    ]
    assert correlated
    assert all(event.analytics_run_id for event in correlated)
    assert all(event.analytics_step_id == "games" for event in correlated)


@pytest.mark.asyncio
async def test_checkpoint_off_persists_outputs_without_memoizing_steps(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep advanced run evidence while disabling all compatible step reuse."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    stats = AnalyticsStats()
    policy = ExecutionPolicy(checkpoint=CheckpointMode.off)
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            analytics=AnalyticsConfig(
                path=tmp_path / "analytics",
                observer=stats,
            ),
        ) as client:
            first = await client.datasets.run(
                "cfbd.game_summaries", params={"year": 2024}, policy=policy
            )
            second = await client.datasets.run(
                "cfbd.game_summaries", params={"year": 2024}, policy=policy
            )
            artifacts = await client.datasets.list_artifacts()

    assert calls == 2
    assert first.reused_steps == second.reused_steps == ()
    assert len(artifacts) == 2
    assert stats.snapshot().reused_steps == 0


@pytest.mark.asyncio
async def test_yaml_workflow_executes_through_the_public_durable_engine(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Run a finite YAML workflow by catalog ID rather than merely compiling it."""
    definition = loads_yaml_definition(
        """
api_version: cfb-data/v1
kind: workflow
id: example.games_workflow
revision: 1
description: Return validated games as one named output.
parameters:
  year:
    type: integer
nodes:
  - kind: source
    id: games
    operation: cfbd.games.list
    revision: 1
    bindings:
      year:
        parameter: year
outputs:
  games: games
"""
    )

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response])

    config = AnalyticsConfig(
        path=tmp_path / "analytics",
        catalog=DatasetCatalog({definition.id: definition}),
    )
    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url, analytics=config) as client:
            plan = await client.workflows.plan(definition.id, params={"year": 2024})
            run = await client.workflows.run(definition.id, params={"year": 2024})

    assert plan.outputs == ("games",)
    assert tuple(run.outputs) == ("games",)
    assert len(run.outputs["games"]) == 1
    assert run.artifacts["games"][0].load_table().num_rows == 1
    assert run.child_run_ids == ()
    assert run.quality["games"]
    assert run.coverage["games"][0].state.value == "present"


@pytest.mark.asyncio
async def test_corrupt_checkpoint_fails_closed(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject a truncated content-addressed part through the public artifact ref."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response])

    root = tmp_path / "analytics"
    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", base_url=base_url, analytics=AnalyticsConfig(path=root)
        ) as client:
            run = await client.datasets.run(
                "cfbd.game_summaries", params={"year": 2024}
            )

    descriptor = run.artifact.descriptor
    part = (
        root
        / "objects"
        / descriptor.content_digest[:2]
        / descriptor.content_digest
        / descriptor.parts[0].name
    )
    part.write_bytes(b"truncated")
    with pytest.raises(CFBDArtifactError):
        run.artifact.load_table()


@pytest.mark.asyncio
async def test_workflow_run_is_durable_and_has_only_named_outputs(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Persist composite workflow lineage while preserving valid empty products."""
    requests: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    active = 0
    max_active = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal active, max_active
        requests.append((request.path, tuple(sorted(request.query.items()))))
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.02)
            return web.json_response([])
        finally:
            active -= 1

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            base_url=base_url,
            analytics=AnalyticsConfig(path=tmp_path / "analytics"),
        ) as client:
            run = await client.workflows.run(
                "cfbd.team_season_analysis",
                params={"season": 2024, "team": "Penn State"},
            )
            inspected = await client.datasets.inspect_run(run.run_id)

    assert set(run.outputs) == {
        "game_summaries",
        "team_games",
        "player_game_stats",
        "rosters",
        "team_seasons",
        "player_seasons",
        "coach_seasons",
    }
    assert all(len(frame) == 0 for frame in run.outputs.values())
    assert run.parent_run_id is None
    assert inspected.status == "success"
    assert len(requests) == 9
    assert len(set(requests)) == 9
    assert max_active == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_complex_catalog_slices_preserve_grain_and_nested_values(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    backend: str,
) -> None:
    """Prove two-row perspective and nested player-stat catalog contracts."""
    team_stats = {
        "id": 401628347,
        "teams": [
            {
                "teamId": 333,
                "team": "Alabama",
                "conference": "SEC",
                "homeAway": "home",
                "points": 63,
                "stats": [{"category": "totalYards", "stat": "600"}],
            },
            {
                "teamId": 2459,
                "team": "Western Kentucky",
                "conference": "Conference USA",
                "homeAway": "away",
                "points": 0,
                "stats": [{"category": "totalYards", "stat": "145"}],
            },
        ],
    }
    player_stats = {
        "id": 401628347,
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
                                        "id": "4433970",
                                        "name": "Jalen Milroe",
                                        "stat": "7/9",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    payloads: dict[str, object] = {
        "/games": [game_response],
        "/games/teams": [team_stats],
        "/games/players": [player_stats],
    }

    async def handler(request: web.Request) -> web.Response:
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key",
            dataframe_backend=backend,
            base_url=base_url,
            analytics=AnalyticsConfig(path=tmp_path / backend),
        ) as client:
            team_run = await client.datasets.run(
                "cfbd.team_games", params={"game_id": 401628347}
            )
            player_run = await client.datasets.run(
                "cfbd.player_game_stats", params={"game_id": 401628347}
            )

    team_rows = team_run.artifact.load_table().to_pylist()
    assert [(row["team_id"], row["result"]) for row in team_rows] == [
        (333, "W"),
        (2459, "L"),
    ]
    assert team_rows[0]["stats"] == [{"category": "totalYards", "stat": "600"}]
    assert team_rows[1]["stats"] == [{"category": "totalYards", "stat": "145"}]
    assert player_run.artifact.load_table().to_pylist() == [
        {
            "game_id": 401628347,
            "team_id": 333,
            "team": "Alabama",
            "home_away": "home",
            "conference": "SEC",
            "team_points": 63,
            "athlete_id": "4433970",
            "athlete_name": "Jalen Milroe",
            "category": "passing",
            "stat_type": "C/ATT",
            "stat": "7/9",
        }
    ]


class _RecoveryParams(BaseModel):
    """Validate parameters for the recovery acceptance graph."""

    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=1869)


def _recovery_definition(revision: int) -> DatasetDefinition[BaseModel, BaseModel]:
    contract = TableContract(
        id="test.dataset.recovery_rows",
        revision=1,
        row_model=Game,
        grain="one recovered source game",
        keys=("id",),
        order_by=("id",),
    )
    source = registered_source(
        "games",
        "cfbd.games.list",
        bindings={"year": ParameterBinding("year")},
    )
    return DatasetDefinition(
        id="test.recovery",
        revision=revision,
        parameter_model=_RecoveryParams,
        nodes=(
            source,
            TransformNode(
                id="clean",
                operation_id="test.transform.recovery",
                operation_revision=revision,
                inputs=("games",),
                output=contract,
            ),
        ),
        output_node="clean",
        output=contract,
        description="Exercise immutable child-run recovery.",
    )


def _failing_transform(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    del inputs, parameters, config
    raise RuntimeError("sensitive implementation detail")


def _passing_transform(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    del parameters, config
    return inputs["games"]


@pytest.mark.asyncio
async def test_synchronous_transform_does_not_block_the_event_loop(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Keep notebook and workflow event loops responsive during Python compute."""
    started = threading.Event()
    release = threading.Event()

    def blocking_transform(
        inputs: Mapping[str, Sequence[BaseModel]],
        parameters: BaseModel,
        config: Mapping[str, JSONValue],
    ) -> Sequence[BaseModel]:
        del parameters, config
        started.set()
        if not release.wait(timeout=1):
            raise RuntimeError("event loop did not release worker transform")
        return inputs["games"]

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response])

    definition = _recovery_definition(3)
    config = AnalyticsConfig(
        path=tmp_path / "analytics",
        catalog=DatasetCatalog({definition.id: definition}),
        transforms=TransformRegistry(
            {
                "test.transform.recovery": RegisteredTransform(
                    id="test.transform.recovery",
                    revision=3,
                    backend=TransformBackend.portable,
                    deterministic=True,
                    callable=blocking_transform,
                )
            }
        ),
    )
    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url, analytics=config) as client:
            task = asyncio.create_task(
                client.datasets.run("test.recovery", params={"year": 2024})
            )
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.005)
                assert started.is_set()
                assert not task.done()
            finally:
                release.set()
            run = await task

    assert len(run.frame) == 1


@pytest.mark.asyncio
async def test_recovery_creates_child_and_reuses_validated_source_snapshot(
    api_server: ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reuse only a compatible ancestor after an implementation revision change."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([game_response])

    root = tmp_path / "analytics"
    async with api_server(handler) as base_url:
        failing_definition = _recovery_definition(1)
        failing_config = AnalyticsConfig(
            path=root,
            catalog=DatasetCatalog({failing_definition.id: failing_definition}),
            transforms=TransformRegistry(
                {
                    "test.transform.recovery": RegisteredTransform(
                        id="test.transform.recovery",
                        revision=1,
                        backend=TransformBackend.portable,
                        deterministic=True,
                        callable=_failing_transform,
                    )
                }
            ),
        )
        with pytest.raises(CFBDRunError) as failed:
            async with CFBDClient(
                "key", base_url=base_url, analytics=failing_config
            ) as client:
                await client.datasets.run("test.recovery", params={"year": 2024})
        assert "sensitive implementation detail" not in str(failed.value)

        passing_definition = _recovery_definition(2)
        passing_config = AnalyticsConfig(
            path=root,
            catalog=DatasetCatalog({passing_definition.id: passing_definition}),
            transforms=TransformRegistry(
                {
                    "test.transform.recovery": RegisteredTransform(
                        id="test.transform.recovery",
                        revision=2,
                        backend=TransformBackend.portable,
                        deterministic=True,
                        callable=_passing_transform,
                    )
                }
            ),
            policy=ExecutionPolicy(max_http_attempts=3),
        )
        async with CFBDClient(
            "key", base_url=base_url, analytics=passing_config
        ) as client:
            recovered = await client.datasets.run(
                "test.recovery", params={"year": 2024}
            )

    assert calls == 1
    assert recovered.parent_run_id == failed.value.run_id
    assert recovered.reused_steps == ("games",)
    assert len(recovered.frame) == 1
