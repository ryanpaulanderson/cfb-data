"""Validate modular recipes against bounded live CFBD and persistent Redis data."""

from __future__ import annotations

import asyncio
import json
import os
import platform
from collections.abc import Awaitable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol, cast

import pytest
from cfb_data._transport import _attempt_reservation_context
from cfb_data.analytics import (
    AnalyticsConfig,
    AnalyticsEvent,
    AnalyticsEventType,
    AnalyticsStats,
    CFBDRunError,
    DatasetRecipe,
    ExecutionPolicy,
    RecipeInspection,
    RecipePlan,
    RecipeRef,
    RecipeRun,
    WorkflowRecipe,
    dataset,
    step,
)
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.games.sources import games
from cfb_data.tests._live_budget import LiveCallLedger
from cfb_data_recipes.betting_lines import betting_lines
from cfb_data_recipes.coach_seasons import coach_seasons
from cfb_data_recipes.drives import drives
from cfb_data_recipes.game_summaries import game_summaries
from cfb_data_recipes.player_game_stats import player_game_stats
from cfb_data_recipes.player_seasons import player_seasons
from cfb_data_recipes.plays import plays
from cfb_data_recipes.poll_rankings import poll_rankings
from cfb_data_recipes.program_history import program_history
from cfb_data_recipes.recruiting_classes import recruiting_classes
from cfb_data_recipes.rosters import rosters
from cfb_data_recipes.single_game_analysis import single_game_analysis
from cfb_data_recipes.team_games import team_games
from cfb_data_recipes.team_season_analysis import team_season_analysis
from cfb_data_recipes.team_seasons import team_seasons

from cfb_data import (
    CFBDClient,
    DataFrameBackend,
    RedisCacheConfig,
    RetrievalStats,
    RetryPolicy,
)

_REDIS_PREFIX = "cfb-data:penn-state-atlas"
_GAME_ID = 401628515
_SEASON = 2024
_TEAM = "Penn State"
_MAX_SESSION_ATTEMPTS = 90
_SAFETY_CUSHION = 25
type _ExecutorName = Literal["local", "dask"]
type _ExecutableRecipe = DatasetRecipe[..., object] | WorkflowRecipe[..., object]


class _RecipeRunner(Protocol):
    """Describe heterogeneous recipe execution after scenario validation."""

    def __call__(
        self,
        client: object,
        **parameters: object,
    ) -> Awaitable[RecipeRun[object]]:
        """Execute one scenario through a callable recipe."""


@dataclass(frozen=True, slots=True)
class _EventCollector:
    """Append redacted analytics events through the observer protocol."""

    events: list[AnalyticsEvent]

    def __call__(self, event: AnalyticsEvent) -> None:
        """Record one immutable analytics event."""
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class _Scenario:
    """Bind one independently importable recipe to non-secret live selectors."""

    recipe: object
    parameters: Mapping[str, object]

    @property
    def name(self) -> str:
        """Return the recipe's stable identity."""
        recipe = _executable(self)
        if recipe.id is None:
            raise AssertionError("Live recipes must have stable identities")
        return recipe.id


@dataclass(slots=True)
class _AttemptPacer:
    """Serialize real attempts enough to avoid an accidental request burst."""

    minimum_interval_seconds: float = 1.35
    _last_dispatch: float | None = None
    _lock: asyncio.Lock | None = None

    async def wait(self) -> None:
        """Wait until the next ledgered attempt may be dispatched."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = monotonic()
            if self._last_dispatch is not None:
                remaining = self.minimum_interval_seconds - (now - self._last_dispatch)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_dispatch = monotonic()


@pytest.mark.live_analytics
@pytest.mark.asyncio
async def test_live_modular_recipe_acceptance(tmp_path: Path) -> None:
    """Verify planning, Redis reuse, parity, recovery, and freshness live."""
    if os.getenv("CFB_DATA_RUN_LIVE_ANALYTICS") != "1":
        pytest.skip("set CFB_DATA_RUN_LIVE_ANALYTICS=1 for live analytics testing")
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        pytest.skip("set CFBD_API_KEY for live analytics testing")
    pytest.importorskip("polars")
    pytest.importorskip("distributed")

    redis_url = os.getenv("CFB_DATA_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")
    ledger = LiveCallLedger(
        Path(os.getenv("CFB_DATA_LIVE_LEDGER", ".cfb-data-live/call-ledger.json"))
    )
    initial = ledger.snapshot()
    authorized_ceiling = ledger.authorized_ceiling(
        maximum_new_attempts=_MAX_SESSION_ATTEMPTS,
        safety_cushion=_SAFETY_CUSHION,
    )
    cache = RedisCacheConfig(url=redis_url, key_prefix=_REDIS_PREFIX)
    retry_policy = RetryPolicy(max_attempts=3)
    all_scenarios = _all_scenarios()
    live_scenarios = _live_scenarios()
    plans = await _plan_all(
        api_key=api_key,
        cache=cache,
        retry_policy=retry_policy,
        root=tmp_path / "preflight",
        scenarios=all_scenarios,
        ledger=ledger,
        initial_spent=initial.spent,
    )
    live_plans = {scenario.name: plans[scenario.name] for scenario in live_scenarios}
    source_candidates = sum(
        sum(node.kind == "source" for node in plan.nodes)
        for plan in live_plans.values()
    )
    worst_case_attempts = sum(
        plan.worst_case_http_attempts for plan in live_plans.values()
    )
    assert source_candidates <= 30
    assert worst_case_attempts <= authorized_ceiling - initial.spent

    inspections = await _inspect_live_scenarios(
        api_key=api_key,
        cache=cache,
        retry_policy=retry_policy,
        root=tmp_path / "inspection",
        scenarios=live_scenarios,
        plans=live_plans,
    )
    assert ledger.snapshot().spent == initial.spent
    assert not (tmp_path / "inspection").exists()

    report_path = Path(".cfb-data-live/live-analytics-report.json")
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "redis_prefix": _REDIS_PREFIX,
        "persistent_cache_cleanup": "not performed",
        "initial_ledger": asdict(initial),
        "authorized_ceiling": authorized_ceiling,
        "authorized_new_attempts": authorized_ceiling - initial.spent,
        "source_candidates": source_candidates,
        "planned_worst_case_attempts": worst_case_attempts,
        "plans": _plan_evidence(plans),
        "inspection": _inspection_evidence(inspections),
        "environment": _environment_evidence(),
        "warnings": [],
        "skips": [],
    }
    pacer = _AttemptPacer()

    async def reserve_global_attempt(endpoint: str, attempt: int) -> None:
        del attempt
        await pacer.wait()
        await asyncio.to_thread(
            ledger.reserve,
            endpoint,
            authorized_ceiling=authorized_ceiling,
        )

    try:
        with _attempt_reservation_context(reserve_global_attempt):
            warm_runs, warm_retrieval, warm_analytics = await _run_matrix(
                api_key=api_key,
                cache=cache,
                retry_policy=retry_policy,
                root=tmp_path / "warm",
                scenarios=live_scenarios,
                backend="pandas",
                executor="local",
                local_only=False,
                checkpoint_mode="off",
            )
            warm_signatures = _signatures(warm_runs)
            combinations: tuple[tuple[DataFrameBackend, _ExecutorName], ...] = (
                ("pandas", "local"),
                ("polars", "local"),
                ("pandas", "dask"),
                ("polars", "dask"),
            )
            parity: dict[str, object] = {}
            for backend, executor in combinations:
                before = ledger.snapshot().spent
                runs, retrieval, analytics = await _run_matrix(
                    api_key=api_key,
                    cache=cache,
                    retry_policy=retry_policy,
                    root=tmp_path / f"{backend}-{executor}",
                    scenarios=live_scenarios,
                    backend=backend,
                    executor=executor,
                    local_only=True,
                    checkpoint_mode="off",
                )
                assert ledger.snapshot().spent == before
                assert retrieval.snapshot().http_attempts == 0
                assert all(run.actual_http_attempts == 0 for run in runs.values())
                assert _signatures(runs) == warm_signatures
                dask_nodes = sum(
                    node.placement == "dask"
                    for run in runs.values()
                    for node in run.lineage
                )
                if executor == "dask":
                    assert dask_nodes > 0
                else:
                    assert dask_nodes == 0
                parity[f"{backend}/{executor}"] = {
                    "retrieval": _retrieval_evidence(retrieval),
                    "analytics": _analytics_evidence(analytics),
                    "runs": _run_evidence(runs),
                    "dask_nodes": dask_nodes,
                    "attempt_delta": ledger.snapshot().spent - before,
                }

            replay = await _checkpoint_replay(
                api_key=api_key,
                cache=cache,
                retry_policy=retry_policy,
                root=tmp_path / "checkpoint-replay",
                scenarios=live_scenarios,
            )
            recovery = await _recovery_evidence(
                api_key=api_key,
                cache=cache,
                retry_policy=retry_policy,
                root=tmp_path / "recovery",
            )
            fresh = await _fresh_run_evidence(
                api_key=api_key,
                cache=cache,
                retry_policy=retry_policy,
                root=tmp_path / "checkpoint-replay",
            )

        final = ledger.snapshot()
        report.update(
            {
                "status": "passed",
                "attempt_delta": final.spent - initial.spent,
                "warm": {
                    "retrieval": _retrieval_evidence(warm_retrieval),
                    "analytics": _analytics_evidence(warm_analytics),
                    "runs": _run_evidence(warm_runs),
                },
                "canonical_signatures": warm_signatures,
                "parity": parity,
                "checkpoint_replay": replay,
                "recovery": recovery,
                "fresh_run": fresh,
            }
        )
    except BaseException as exc:
        report.update(
            {
                "status": "failed",
                "failure_category": type(exc).__name__,
                "attempt_delta": ledger.snapshot().spent - initial.spent,
            }
        )
        raise
    finally:
        report["final_ledger"] = asdict(ledger.snapshot())
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


async def _plan_all(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
    scenarios: Sequence[_Scenario],
    ledger: LiveCallLedger,
    initial_spent: int,
) -> dict[str, RecipePlan]:
    """Compile every first-party product without operational I/O."""
    client = CFBDClient(
        api_key,
        cache=cache,
        retry_policy=retry_policy,
        analytics=AnalyticsConfig(root=root),
    )
    plans: dict[str, RecipePlan] = {}
    for scenario in scenarios:
        recipe = _executable(scenario)
        plans[scenario.name] = await recipe.plan(
            client,
            policy=ExecutionPolicy(max_http_attempts=_MAX_SESSION_ATTEMPTS),
            **scenario.parameters,
        )
    assert len(plans) == 15
    assert not root.exists()
    assert ledger.snapshot().spent == initial_spent
    return plans


async def _inspect_live_scenarios(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
    scenarios: Sequence[_Scenario],
    plans: Mapping[str, RecipePlan],
) -> dict[str, RecipeInspection]:
    """Inspect exact Redis and checkpoint state without executing sources."""
    inspections: dict[str, RecipeInspection] = {}
    async with CFBDClient(
        api_key,
        cache=cache,
        retry_policy=retry_policy,
        analytics=AnalyticsConfig(root=root),
    ) as client:
        for scenario in scenarios:
            recipe = _executable(scenario)
            inspections[scenario.name] = await recipe.inspect(
                client,
                plan=plans[scenario.name],
                policy=ExecutionPolicy(max_http_attempts=_MAX_SESSION_ATTEMPTS),
                **scenario.parameters,
            )
    return inspections


async def _run_matrix(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
    scenarios: Sequence[_Scenario],
    backend: DataFrameBackend,
    executor: _ExecutorName,
    local_only: bool,
    checkpoint_mode: Literal["all", "off"],
) -> tuple[dict[str, RecipeRun[object]], RetrievalStats, AnalyticsStats]:
    """Execute one isolated matrix and return bounded run evidence."""
    retrieval = RetrievalStats()
    analytics = AnalyticsStats()
    runs: dict[str, RecipeRun[object]] = {}
    async with CFBDClient(
        api_key,
        cache=cache,
        dataframe_backend=backend,
        retry_policy=retry_policy,
        observer=retrieval,
        analytics=AnalyticsConfig(root=root, observer=analytics),
    ) as client:
        scope = client.cache_mode("local_only") if local_only else nullcontext()
        with scope:
            for scenario in scenarios:
                runs[scenario.name] = await _run_scenario(
                    scenario,
                    client,
                    policy=ExecutionPolicy(
                        executor=executor,
                        max_http_attempts=_MAX_SESSION_ATTEMPTS,
                        checkpoint_mode=checkpoint_mode,
                        dask_max_workers=2,
                    ),
                )
    return runs, retrieval, analytics


async def _checkpoint_replay(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
    scenarios: Sequence[_Scenario],
) -> dict[str, object]:
    """Prove compatible transforms replay without starting Dask work."""
    retrieval = RetrievalStats()
    events: list[AnalyticsEvent] = []
    policy = ExecutionPolicy(
        executor="dask",
        max_http_attempts=_MAX_SESSION_ATTEMPTS,
        dask_max_workers=2,
    )
    async with CFBDClient(
        api_key,
        cache=cache,
        retry_policy=retry_policy,
        observer=retrieval,
        analytics=AnalyticsConfig(root=root, observer=_EventCollector(events)),
    ) as client:
        with client.cache_mode("local_only"):
            first = {
                scenario.name: await _run_scenario(scenario, client, policy=policy)
                for scenario in scenarios
            }
            events.clear()
            second = {
                scenario.name: await _run_scenario(scenario, client, policy=policy)
                for scenario in scenarios
            }
    assert _signatures(first) == _signatures(second)
    assert retrieval.snapshot().http_attempts == 0
    assert all(run.actual_http_attempts == 0 for run in second.values())
    assert all(run.reused_nodes > 0 for run in second.values())
    assert not any(
        event.event_type is AnalyticsEventType.step_started
        and event.placement == "dask"
        for event in events
    )
    return {
        "first": _run_evidence(first),
        "second": _run_evidence(second),
        "retrieval": _retrieval_evidence(retrieval),
        "second_run_dask_starts": sum(
            event.event_type is AnalyticsEventType.step_started
            and event.placement == "dask"
            for event in events
        ),
    }


async def _recovery_evidence(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
) -> dict[str, object]:
    """Fail downstream, revise the step, and reuse the parent source snapshot."""

    @step(id="tests.live.recovery.clean", revision=1, output=Game)
    def failing(rows: list[Game]) -> list[Game]:
        del rows
        raise RuntimeError("injected live recovery failure")

    @step(id="tests.live.recovery.clean", revision=2, output=Game)
    def fixed(rows: list[Game]) -> list[Game]:
        return rows

    selected_step = failing

    @dataset(
        id="tests.live.recovery",
        revision=1,
        row=Game,
        grain="one exact game",
        keys=("id",),
        order_by=("season", "week", "id"),
    )
    def recoverable(*, game_id: int) -> RecipeRef[list[Game]]:
        return selected_step(games(game_id=game_id))

    retrieval = RetrievalStats()
    async with CFBDClient(
        api_key,
        cache=cache,
        retry_policy=retry_policy,
        observer=retrieval,
        analytics=AnalyticsConfig(root=root),
    ) as client:
        with client.cache_mode("local_only"):
            with pytest.raises(CFBDRunError) as failed:
                await recoverable.run(client, game_id=_GAME_ID)
            selected_step = fixed
            repaired: RecipeRun[object] = await recoverable.run(
                client,
                game_id=_GAME_ID,
                resume_from=failed.value.run_id,
            )
    assert repaired.parent_run_id == failed.value.run_id
    assert repaired.actual_http_attempts == 0
    assert repaired.reused_nodes >= 1
    assert retrieval.snapshot().http_attempts == 0
    return {
        "failed_run_id": failed.value.run_id,
        "child_run_id": repaired.run_id,
        "parent_run_id": repaired.parent_run_id,
        "actual_http_attempts": repaired.actual_http_attempts,
        "reused_nodes": repaired.reused_nodes,
        "lineage": _lineage_evidence(repaired),
    }


async def _fresh_run_evidence(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    retry_policy: RetryPolicy,
    root: Path,
) -> dict[str, object]:
    """Prove a new run consults current Redis freshness, not source checkpoints."""
    retrieval = RetrievalStats()
    async with CFBDClient(
        api_key,
        cache=cache,
        retry_policy=retry_policy,
        observer=retrieval,
        analytics=AnalyticsConfig(root=root),
    ) as client:
        run: RecipeRun[object] = await game_summaries.run(
            client,
            year=_SEASON,
            team=_TEAM,
            policy=ExecutionPolicy(max_http_attempts=_MAX_SESSION_ATTEMPTS),
        )
    snapshot = retrieval.snapshot()
    assert run.parent_run_id is None
    assert snapshot.endpoint_retrievals > 0
    assert snapshot.cache_served_retrievals > 0 or snapshot.http_attempts > 0
    return {
        "run_id": run.run_id,
        "parent_run_id": run.parent_run_id,
        "actual_http_attempts": run.actual_http_attempts,
        "retrieval": _retrieval_evidence(retrieval),
        "lineage": _lineage_evidence(run),
    }


async def _run_scenario(
    scenario: _Scenario,
    client: CFBDClient[object],
    *,
    policy: ExecutionPolicy,
) -> RecipeRun[object]:
    """Run one dataset or workflow through its callable recipe object."""
    recipe = _executable(scenario)
    runner = cast(_RecipeRunner, recipe.run)
    return await runner(
        client,
        policy=policy,
        **scenario.parameters,
    )


def _executable(scenario: _Scenario) -> _ExecutableRecipe:
    """Narrow a scenario's independently imported callable recipe."""
    if not isinstance(scenario.recipe, DatasetRecipe | WorkflowRecipe):
        raise AssertionError("Live scenario is not an executable recipe")
    return cast(_ExecutableRecipe, scenario.recipe)


def _all_scenarios() -> tuple[_Scenario, ...]:
    """Return one valid plan-only invocation for every first-party product."""
    return (
        _Scenario(game_summaries, {"year": _SEASON, "team": _TEAM}),
        _Scenario(team_games, {"year": _SEASON, "team": _TEAM}),
        _Scenario(player_game_stats, {"year": _SEASON, "team": _TEAM}),
        _Scenario(drives, {"year": _SEASON, "week": 1, "team": _TEAM}),
        _Scenario(plays, {"year": _SEASON, "week": 1, "team": _TEAM}),
        _Scenario(rosters, {"season": _SEASON, "team": _TEAM}),
        _Scenario(team_seasons, {"season": _SEASON, "team": _TEAM}),
        _Scenario(player_seasons, {"season": _SEASON, "team": _TEAM}),
        _Scenario(poll_rankings, {"season": _SEASON}),
        _Scenario(betting_lines, {"season": _SEASON, "team": _TEAM}),
        _Scenario(recruiting_classes, {"class_year": _SEASON, "team": _TEAM}),
        _Scenario(coach_seasons, {"year": _SEASON, "team": _TEAM}),
        _Scenario(team_season_analysis, {"season": _SEASON, "team": _TEAM}),
        _Scenario(single_game_analysis, {"game_id": _GAME_ID}),
        _Scenario(
            program_history,
            {
                "team": _TEAM,
                "start_season": _SEASON,
                "end_season": _SEASON,
            },
        ),
    )


def _live_scenarios() -> tuple[_Scenario, ...]:
    """Return the bounded stable Penn State live acceptance matrix."""
    scenarios = _all_scenarios()
    selected = {
        "cfbd.team_seasons",
        "cfbd.single_game_analysis",
        "cfbd.program_history",
    }
    return tuple(scenario for scenario in scenarios if scenario.name in selected)


def _signatures(runs: Mapping[str, RecipeRun[object]]) -> dict[str, object]:
    """Return canonical content identities for each named output."""
    return {
        name: {
            output: artifact.descriptor.content_digest
            for output, artifact in sorted(run.artifacts.items())
        }
        for name, run in sorted(runs.items())
    }


def _plan_evidence(plans: Mapping[str, RecipePlan]) -> dict[str, object]:
    """Return redacted static-plan evidence for the live report."""
    return {
        name: {
            "node_count": len(plan.nodes),
            "source_nodes": sum(node.kind == "source" for node in plan.nodes),
            "worst_case_http_attempts": plan.worst_case_http_attempts,
            "outputs": list(plan.outputs),
            "fingerprint": plan.fingerprint,
        }
        for name, plan in sorted(plans.items())
    }


def _inspection_evidence(
    inspections: Mapping[str, RecipeInspection],
) -> dict[str, object]:
    """Return redacted non-mutating cache and checkpoint dispositions."""
    return {
        name: {
            "sources": dict(sorted(inspection.source_dispositions.items())),
            "checkpoints": dict(sorted(inspection.checkpoint_dispositions.items())),
        }
        for name, inspection in sorted(inspections.items())
    }


def _retrieval_evidence(stats: RetrievalStats) -> dict[str, object]:
    """Return aggregate and per-endpoint redacted retrieval counters."""
    snapshot = stats.snapshot()
    counters = (
        "endpoint_retrievals",
        "successful_retrievals",
        "failed_retrievals",
        "http_attempts",
        "retries",
        "fresh_cache_hits",
        "retained_cache_serves",
        "stale_fallbacks",
        "cache_misses",
        "stale_entries",
        "incompatible_entries",
        "corrupt_entries",
        "cache_served_retrievals",
        "network_free_successes",
        "rows_returned",
    )
    return {
        "totals": {name: getattr(snapshot, name) for name in counters},
        "by_endpoint": {
            endpoint: {name: getattr(values, name) for name in counters}
            for endpoint, values in snapshot.by_endpoint.items()
        },
    }


def _analytics_evidence(stats: AnalyticsStats) -> dict[str, object]:
    """Return bounded redacted analytics event counters."""
    snapshot = stats.snapshot()
    return {
        "total_events": snapshot.total_events,
        "dropped_events": snapshot.dropped_events,
        "by_type": {
            event_type.value: count
            for event_type, count in sorted(
                snapshot.by_type.items(), key=lambda item: item[0].value
            )
        },
        "by_outcome": {
            outcome.value: count
            for outcome, count in sorted(
                snapshot.by_outcome.items(), key=lambda item: item[0].value
            )
        },
    }


def _run_evidence(runs: Mapping[str, RecipeRun[object]]) -> dict[str, object]:
    """Return safe content, quality, coverage, and placement evidence."""
    return {
        name: {
            "run_id": run.run_id,
            "parent_run_id": run.parent_run_id,
            "actual_http_attempts": run.actual_http_attempts,
            "reused_nodes": run.reused_nodes,
            "outputs": {
                output: {
                    "digest": artifact.descriptor.content_digest,
                    "rows": artifact.descriptor.row_count,
                    "bytes": artifact.descriptor.byte_count,
                    "quality": [result.check for result in artifact.descriptor.quality],
                }
                for output, artifact in sorted(run.artifacts.items())
            },
            "coverage": [
                {
                    "operation": coverage.operation_id,
                    "state": coverage.state,
                    "rows": coverage.row_count,
                }
                for coverage in run.source_coverage
            ],
            "lineage": _lineage_evidence(run),
        }
        for name, run in sorted(runs.items())
    }


def _lineage_evidence(run: RecipeRun[object]) -> list[dict[str, object]]:
    """Return safe node placement and reuse evidence for one run."""
    return [
        {
            "node": node.node_id,
            "kind": node.node_kind,
            "output": node.output_name,
            "placement": node.placement,
            "reused": node.reused,
            "checkpoint_eligible": node.checkpoint_eligible,
            "digest": node.content_digest,
        }
        for node in run.lineage
    ]


def _environment_evidence() -> dict[str, str]:
    """Return non-secret runtime versions used by live acceptance."""
    packages = (
        "cfb-data",
        "dask",
        "distributed",
        "pandas",
        "polars",
        "pyarrow",
        "redis",
    )
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        **{package: version(package) for package in packages},
    }
