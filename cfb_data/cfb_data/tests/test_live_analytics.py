"""Exercise durable analytics against bounded live API and persistent Redis data."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import aiohttp
import pytest
from cfb_data._transport import _HTTPTransport, _ResponseEnvelope, _RetryDecision
from cfb_data.base.types import JSONValue, QueryParameters
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.tests._live_budget import LiveCallLedger
from pydantic import BaseModel, ConfigDict, Field

from cfb_data import (
    AnalyticsConfig,
    AnalyticsStats,
    CFBDClient,
    CFBDRunError,
    DatasetCatalog,
    DatasetDefinition,
    ParameterBinding,
    RedisCacheConfig,
    RegisteredTransform,
    RetrievalStats,
    TableContract,
    TransformBackend,
    TransformNode,
    TransformRegistry,
    registered_source,
)

_REDIS_PREFIX = "cfb-data:penn-state-atlas"
_GAME_ID = 401628515


@dataclass(slots=True)
class _Pacer:
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
async def test_live_redis_analytics_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify warm, local-only, parity, checkpoint, and recovery behavior."""
    if os.getenv("CFB_DATA_RUN_LIVE_ANALYTICS") != "1":
        pytest.skip("set CFB_DATA_RUN_LIVE_ANALYTICS=1 for live analytics testing")
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        pytest.skip("set CFBD_API_KEY for live analytics testing")
    redis_url = os.getenv("CFB_DATA_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")
    ledger = LiveCallLedger(
        Path(os.getenv("CFB_DATA_LIVE_LEDGER", ".cfb-data-live/call-ledger.json"))
    )
    initial_spent = ledger.snapshot().spent
    cache = RedisCacheConfig(url=redis_url, key_prefix=_REDIS_PREFIX)
    scenarios = _scenarios()

    preflight = CFBDClient(
        api_key,
        cache=cache,
        analytics=AnalyticsConfig(path=tmp_path / "preflight"),
    )
    plans = []
    for name, kind, parameters in scenarios:
        if kind == "dataset":
            plans.append(await preflight.datasets.plan(name, params=parameters))
        else:
            plans.append(await preflight.workflows.plan(name, params=parameters))
    assert not (tmp_path / "preflight").exists()
    assert ledger.snapshot().spent == initial_spent
    planned_worst_case = sum(plan.worst_case_http_attempts for plan in plans)
    assert planned_worst_case <= 135
    if initial_spent + planned_worst_case > 770:
        pytest.skip("live ledger advanced beyond the bounded analytics matrix")

    pacer = _Pacer()
    original_request = _HTTPTransport._request_once

    async def budgeted_request(
        transport: _HTTPTransport,
        *,
        session: aiohttp.ClientSession,
        url: str,
        endpoint: str,
        params: QueryParameters,
        attempt: int,
        conditional_headers: Mapping[str, str] | None,
    ) -> _ResponseEnvelope | _RetryDecision:
        await pacer.wait()
        ledger.reserve(endpoint)
        return await original_request(
            transport,
            session=session,
            url=url,
            endpoint=endpoint,
            params=params,
            attempt=attempt,
            conditional_headers=conditional_headers,
        )

    monkeypatch.setattr(_HTTPTransport, "_request_once", budgeted_request)
    report_path = Path(".cfb-data-live/live-analytics-report.json")
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "redis_prefix": _REDIS_PREFIX,
        "initial_ledger_spent": initial_spent,
        "planned_worst_case_attempts": planned_worst_case,
        "scenarios": [name for name, _, _ in scenarios],
        "persistent_cache_cleanup": "not performed",
    }
    try:
        warm_retrieval = RetrievalStats()
        warm_analytics = AnalyticsStats()
        async with CFBDClient(
            api_key,
            cache=cache,
            observer=warm_retrieval,
            analytics=AnalyticsConfig(
                path=tmp_path / "warm",
                observer=warm_analytics,
            ),
        ) as client:
            warm_signatures, _ = await _exercise(client, scenarios)

        pandas_retrieval = RetrievalStats()
        pandas_analytics = AnalyticsStats()
        async with CFBDClient(
            api_key,
            cache=cache,
            observer=pandas_retrieval,
            analytics=AnalyticsConfig(
                path=tmp_path / "pandas-local",
                observer=pandas_analytics,
            ),
        ) as client:
            with client.cache_mode("local_only"):
                pandas_signatures, _ = await _exercise(client, scenarios)

        polars_retrieval = RetrievalStats()
        polars_analytics = AnalyticsStats()
        async with CFBDClient(
            api_key,
            dataframe_backend="polars",
            cache=cache,
            observer=polars_retrieval,
            analytics=AnalyticsConfig(
                path=tmp_path / "polars-local",
                observer=polars_analytics,
            ),
        ) as client:
            with client.cache_mode("local_only"):
                polars_signatures, first_runs = await _exercise(client, scenarios)
                _, replay_runs = await _exercise(client, scenarios)

        assert warm_signatures == pandas_signatures == polars_signatures
        assert pandas_retrieval.snapshot().http_attempts == 0
        assert polars_retrieval.snapshot().http_attempts == 0
        assert any(run.reused_steps for run in replay_runs)
        assert all(run.parent_run_id is None for run in first_runs)

        recovery = await _exercise_recovery(
            api_key=api_key,
            cache=cache,
            root=tmp_path / "recovery",
        )
        assert recovery["parent_run_id"] == recovery["failed_run_id"]
        assert recovery["reused_steps"] == ["games"]

        fresh_retrieval = RetrievalStats()
        async with CFBDClient(
            api_key,
            cache=cache,
            observer=fresh_retrieval,
            analytics=AnalyticsConfig(path=tmp_path / "polars-local"),
        ) as client:
            new_run = await client.datasets.run(
                "cfbd.team_seasons",
                params={"season": None, "team": "Penn State"},
            )
        fresh_snapshot = fresh_retrieval.snapshot()
        assert new_run.parent_run_id is None
        assert fresh_snapshot.endpoint_retrievals > 0
        assert fresh_snapshot.cache_served_retrievals > 0

        report.update(
            {
                "status": "passed",
                "attempt_delta": ledger.snapshot().spent - initial_spent,
                "warm_retrieval": _retrieval_evidence(warm_retrieval),
                "warm_analytics": _analytics_evidence(warm_analytics),
                "pandas_local_retrieval": _retrieval_evidence(pandas_retrieval),
                "pandas_local_analytics": _analytics_evidence(pandas_analytics),
                "polars_local_retrieval": _retrieval_evidence(polars_retrieval),
                "polars_local_analytics": _analytics_evidence(polars_analytics),
                "fresh_run_retrieval": _retrieval_evidence(fresh_retrieval),
                "recovery": recovery,
                "signatures": pandas_signatures,
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "failed",
                "failure_category": type(exc).__name__,
                "attempt_delta": ledger.snapshot().spent - initial_spent,
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


def _scenarios() -> tuple[tuple[str, str, Mapping[str, object]], ...]:
    """Return the bounded stable Penn State live acceptance matrix."""
    return (
        (
            "cfbd.team_seasons",
            "dataset",
            {"season": None, "team": "Penn State"},
        ),
        (
            "cfbd.single_game_analysis",
            "workflow",
            {"game_id": _GAME_ID},
        ),
        (
            "cfbd.program_history",
            "workflow",
            {"team": "Penn State", "start_year": 2024, "end_year": 2024},
        ),
    )


async def _exercise(
    client: CFBDClient[object],
    scenarios: Sequence[tuple[str, str, Mapping[str, object]]],
) -> tuple[dict[str, object], list[object]]:
    """Run the matrix and return only content digests and run evidence."""
    signatures: dict[str, object] = {}
    runs: list[object] = []
    for name, kind, parameters in scenarios:
        if kind == "dataset":
            run = await client.datasets.run(name, params=parameters)
            signatures[name] = run.artifact.descriptor.content_digest
        else:
            run = await client.workflows.run(name, params=parameters)
            signatures[name] = {
                output: [ref.descriptor.content_digest for ref in refs]
                for output, refs in sorted(run.artifacts.items())
            }
        runs.append(run)
    return signatures, runs


class _RecoveryParams(BaseModel):
    """Validate the one-selector live recovery graph."""

    model_config = ConfigDict(extra="forbid")
    game_id: int = Field(gt=0)


def _recovery_definition(revision: int) -> DatasetDefinition[BaseModel, BaseModel]:
    """Build a graph whose transform revision can be repaired."""
    contract = TableContract(
        id="test.live.recovery_rows",
        revision=1,
        row_model=Game,
        grain="one live cached game",
        keys=("id",),
        order_by=("id",),
    )
    return DatasetDefinition(
        id="test.live_recovery",
        revision=revision,
        parameter_model=_RecoveryParams,
        nodes=(
            registered_source(
                "games",
                "cfbd.games.list",
                bindings={"game_id": ParameterBinding("game_id")},
            ),
            TransformNode(
                id="clean",
                operation_id="test.live.clean",
                operation_revision=revision,
                inputs=("games",),
                output=contract,
            ),
        ),
        output_node="clean",
        output=contract,
        description="Prove zero-transport child-run recovery against Redis.",
    )


def _fail_transform(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Fail after the source checkpoint has committed."""
    del inputs, parameters, config
    raise RuntimeError("intentional live analytics recovery failure")


def _pass_transform(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Return the validated source rows after a revision fix."""
    del parameters, config
    return inputs["games"]


async def _exercise_recovery(
    *,
    api_key: str,
    cache: RedisCacheConfig,
    root: Path,
) -> dict[str, object]:
    """Fail then repair a downstream node using only retained Redis data."""
    failed_definition = _recovery_definition(1)
    failed_config = AnalyticsConfig(
        path=root,
        catalog=DatasetCatalog({failed_definition.id: failed_definition}),
        transforms=TransformRegistry(
            {
                "test.live.clean": RegisteredTransform(
                    id="test.live.clean",
                    revision=1,
                    backend=TransformBackend.portable,
                    deterministic=True,
                    callable=_fail_transform,
                )
            }
        ),
    )
    with pytest.raises(CFBDRunError) as failed:
        async with CFBDClient(api_key, cache=cache, analytics=failed_config) as client:
            with client.cache_mode("local_only"):
                await client.datasets.run(
                    "test.live_recovery", params={"game_id": _GAME_ID}
                )

    repaired_definition = _recovery_definition(2)
    repaired_config = AnalyticsConfig(
        path=root,
        catalog=DatasetCatalog({repaired_definition.id: repaired_definition}),
        transforms=TransformRegistry(
            {
                "test.live.clean": RegisteredTransform(
                    id="test.live.clean",
                    revision=2,
                    backend=TransformBackend.portable,
                    deterministic=True,
                    callable=_pass_transform,
                )
            }
        ),
    )
    retrieval = RetrievalStats()
    async with CFBDClient(
        api_key,
        cache=cache,
        observer=retrieval,
        analytics=repaired_config,
    ) as client:
        with client.cache_mode("local_only"):
            repaired = await client.datasets.run(
                "test.live_recovery", params={"game_id": _GAME_ID}
            )
    assert retrieval.snapshot().http_attempts == 0
    return {
        "failed_run_id": failed.value.run_id,
        "parent_run_id": repaired.parent_run_id,
        "reused_steps": list(repaired.reused_steps),
        "http_attempts": retrieval.snapshot().http_attempts,
    }


def _retrieval_evidence(stats: RetrievalStats) -> dict[str, int]:
    """Return bounded aggregate retrieval counters for the redacted report."""
    snapshot = stats.snapshot()
    return {
        "retrievals": snapshot.endpoint_retrievals,
        "http_attempts": snapshot.http_attempts,
        "retries": snapshot.retries,
        "fresh_cache_hits": snapshot.fresh_cache_hits,
        "retained_cache_serves": snapshot.retained_cache_serves,
        "cache_served_retrievals": snapshot.cache_served_retrievals,
    }


def _analytics_evidence(stats: AnalyticsStats) -> dict[str, int]:
    """Return bounded aggregate analytics counters for the redacted report."""
    snapshot = stats.snapshot()
    return {
        "runs": snapshot.runs,
        "successful_runs": snapshot.successful_runs,
        "failed_runs": snapshot.failed_runs,
        "steps": snapshot.steps,
        "reused_steps": snapshot.reused_steps,
        "artifacts_committed": snapshot.artifacts_committed,
        "rows_materialized": snapshot.rows_materialized,
        "bytes_committed": snapshot.bytes_committed,
    }
