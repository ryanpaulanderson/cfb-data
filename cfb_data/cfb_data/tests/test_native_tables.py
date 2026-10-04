"""Verify native partitioned recipe execution through public interfaces."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager
from enum import StrEnum
from pathlib import Path
from typing import Literal

import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import (
    AnalyticsConfig,
    AnalyticsEvent,
    AnalyticsEventType,
    CFBDRecipeParameterError,
    CFBDRunError,
    CFBDTransformError,
    ExecutionPolicy,
    RecipeRef,
    SourceContext,
    Table,
    dataset,
    require_one,
    source,
    step,
    value,
    workflow,
)
from cfb_data.games.sources import games
from pydantic import BaseModel, Field

from cfb_data import CFBDClient, RetryPolicy

type _ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def test_owned_native_tables_compose_and_enforce_bounded_collection() -> None:
    source = pd.DataFrame(
        {"id": [1, 2, 3, 4], "group": ["a", "b", "a", "b"], "value": [1, 2, 3, 4]}
    )
    table = Table.from_pandas(source, partition_rows=1)
    source.loc[0, "value"] = 999
    totals = table.aggregate(
        keys=("group",), expressions=(nw.col("value").sum().alias("total"),)
    )
    labels = Table.from_pandas(
        pd.DataFrame({"group": ["a", "b"], "label": ["A", "B"]}), partition_rows=1
    )
    result = totals.join(labels, on=("group",), cardinality="one_to_one").sort("group")
    assert result.collect_bounded(max_rows=2).to_dict("records") == [
        {"group": "a", "total": 4, "label": "A"},
        {"group": "b", "total": 6, "label": "B"},
    ]
    with pytest.raises(CFBDTransformError, match="row bound"):
        table.collect_bounded(max_rows=3)
    with pytest.raises(CFBDTransformError, match="positive values"):
        table.require(nw.col("value") > 1, message="positive values").collect_bounded(
            max_rows=4
        )
    with pytest.raises(ValueError, match="positive integer"):
        Table.from_pandas(source, partition_rows=0)


def test_concurrent_native_construction_preserves_structs_and_caller_settings() -> None:
    import dask

    before = dict(dask.config.get("dataframe"))

    def project(number: int) -> dict[str, object]:
        table = Table.from_pandas(
            pd.DataFrame(
                {"id": [number], "clock": [{"minutes": number, "seconds": 0}]}
            ),
            partition_rows=1,
        )
        return (
            table.nested(
                "clock", fields={"minutes": "minutes"}, dtypes={"minutes": "Int64"}
            )
            .collect_bounded(max_rows=1)
            .iloc[0]
            .to_dict()
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(pool.map(project, range(16)))
    for number, record in enumerate(results):
        assert record == {
            "id": number,
            "clock": {"minutes": number, "seconds": 0},
            "minutes": number,
        }
    assert dict(dask.config.get("dataframe")) == before


class _Input(BaseModel):
    """Carry a bounded fixture whose final constraint is deliberately stricter."""

    id: int
    value: int | None


class _Output(BaseModel):
    """Require nonnegative values while retaining structural nulls."""

    id: int
    value: int | None = Field(ge=0)


@source(id="tests.native.input", revision=1, output=_Input, cost=0)
async def _input(
    context: SourceContext[_Input],
    *,
    duplicate: bool = False,
    invalid: bool = False,
    empty: bool = False,
) -> list[_Input]:
    """Return six controlled rows without an HTTP request."""
    del context
    if empty:
        return []
    return [
        _Input(id=5, value=None),
        _Input(id=4, value=4),
        _Input(id=3, value=3),
        _Input(id=2, value=2),
        _Input(id=1, value=1),
        _Input(id=5 if duplicate else 0, value=-1 if invalid else 0),
    ]


@step(id="tests.native.compose", revision=1, output=_Output)
def _compose(rows: Table, *, branches: int) -> Table:
    """Rejoin shared contracts repeatedly without reconstructing observations."""
    base = rows.require_unique(("id",), message="Duplicate native IDs")
    for ordinal in range(branches):
        base = base.join(
            base.select("id", nw.lit(True).alias(f"branch_{ordinal}")),
            on=("id",),
            cardinality="one_to_one",
        )
    return base.select("id", "value").sort("id")


@dataset(
    id="tests.native.dataset",
    revision=1,
    row=_Output,
    grain="one fixture identifier",
    keys=("id",),
    order_by=("id",),
)
def _native_dataset(
    *, duplicate: bool = False, invalid: bool = False, branches: int = 0
) -> RecipeRef[Table]:
    """Declare a fully native fixture with explicit final keys and order."""
    return _compose(_input(duplicate=duplicate, invalid=invalid), branches=branches)


@pytest.mark.asyncio
async def test_native_scan_and_batches_survive_client_cleanup(tmp_path: Path) -> None:
    """Retain lazy dataframe output and bounded durable reads after cleanup."""
    async with CFBDClient(
        "offline-native", analytics=AnalyticsConfig(root=tmp_path / "analytics")
    ) as client:
        run = await _native_dataset.run(
            client,
            policy=ExecutionPolicy(result_mode="lazy", table_partition_rows=1),
            branches=8,
        )
    assert isinstance(run.value, Table)
    assert run.actual_http_attempts == 0
    expected = [{"id": i, "value": i if i < 5 else None} for i in range(6)]
    frame = run.value.collect()
    assert (
        frame.astype(object).where(frame.notna(), None).to_dict("records") == expected
    )
    assert [len(batch) for batch in run.artifact.batches(batch_rows=1)] == [1] * 6
    assert run.artifact.descriptor.row_count == 6
    assert isinstance(run.artifact.scan().collect(), pd.DataFrame)
    target = run.artifact.export_parquet(tmp_path / "fixture.parquet")
    assert len(pd.read_parquet(target)) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("duplicate", "invalid"))
async def test_late_partition_failure_cannot_publish_dataset(
    tmp_path: Path, failure: str
) -> None:
    """Reject a duplicate across partitions and malformed final-part values."""
    events: list[AnalyticsEvent] = []
    root = tmp_path / "analytics"
    async with CFBDClient(
        "offline-native", analytics=AnalyticsConfig(root=root, observer=events.append)
    ) as client:
        with pytest.raises(CFBDRunError):
            await _native_dataset.run(
                client,
                duplicate=failure == "duplicate",
                invalid=failure == "invalid",
                policy=ExecutionPolicy(table_partition_rows=1, checkpoint_mode="off"),
            )
    assert not any(
        event.event_type == AnalyticsEventType.artifact_committed
        and event.node_id is not None
        and event.node_id.startswith("dataset:tests.native.dataset@")
        for event in events
    )


@pytest.mark.asyncio
async def test_distributed_partitions_execute_on_multiple_workers(
    tmp_path: Path,
) -> None:
    """Execute several real partitions and retain worker evidence and parity."""
    pytest.importorskip("distributed")
    events: list[AnalyticsEvent] = []
    async with CFBDClient(
        "offline-native",
        analytics=AnalyticsConfig(root=tmp_path / "analytics", observer=events.append),
    ) as client:
        run = await _native_dataset.run(
            client,
            policy=ExecutionPolicy(
                executor="dask",
                dask_max_workers=2,
                table_partition_rows=1,
                result_mode="lazy",
                checkpoint_mode="off",
            ),
        )
    parts = [
        event
        for event in events
        if event.event_type == AnalyticsEventType.partition_completed
    ]
    assert len(parts) >= 2
    assert len({event.worker_pid for event in parts}) == 2
    assert all(event.row_count is not None and event.row_count >= 0 for event in parts)
    assert run.value.collect()["id"].tolist() == list(range(6))


def test_global_contract_is_checked_before_explicit_collection() -> None:
    """Reject a null predicate through the public table contract."""
    frame = nw.from_native(pd.DataFrame({"id": [1, 2], "valid": [True, None]})).lazy()
    with pytest.raises(CFBDTransformError, match="Invalid fixture"):
        Table(frame).require(nw.col("valid"), message="Invalid fixture").collect()


@pytest.mark.parametrize(
    ("identifiers", "values", "message"),
    (
        ([1, 2, 3, 4], [1, 2, 3, 4], None),
        ([1, 2, 3, 1], [1, 2, 3, 4], "Duplicate identifiers"),
        ([1, 2, 3, 1], [1, 2, None, 4], "Invalid values"),
    ),
)
def test_shared_global_checks_preserve_contract_order(
    identifiers: list[int], values: list[int | None], message: str | None
) -> None:
    """Retain each contract and its failure priority when lowering shared graphs."""
    import dask.dataframe as dd

    frame = pd.DataFrame({"id": identifiers, "value": values})
    table = (
        Table(nw.from_native(dd.from_pandas(frame, npartitions=2, sort=False)))
        .require(nw.col("value") > 0, message="Invalid values")
        .require_unique(("id",), message="Duplicate identifiers")
    )
    if message is not None:
        with pytest.raises(CFBDTransformError, match=message):
            table.collect()
    else:
        assert table.collect()["id"].tolist() == identifiers


class _CoverageStatus(StrEnum):
    """Describe complete or partial source evidence in the canonical row schema."""

    complete = "complete"
    partial = "partial"


class _CoverageRow(BaseModel):
    """Retain partial evidence with an optional known explanation."""

    id: int
    coverage_state: _CoverageStatus
    coverage_warning: str | None


class _PropertyCoverageRow(BaseModel):
    """Derive coverage evidence from persisted source fields."""

    id: int
    status: _CoverageStatus
    reason: str | None

    @property
    def coverage_state(self) -> Literal["complete", "partial"]:
        """Return the source completeness carried by the persisted status."""
        return "partial" if self.status == _CoverageStatus.partial else "complete"

    @property
    def coverage_warning(self) -> str | None:
        """Return the explanation carried by the persisted reason."""
        return self.reason


class _MixedCoverageRow(BaseModel):
    """Expose state as a field and its explanation as a model property."""

    id: int
    coverage_state: _CoverageStatus
    reason: str | None

    @property
    def coverage_warning(self) -> str | None:
        """Return the explanation carried by the persisted reason."""
        return self.reason


@source(id="tests.native.coverage_input", revision=1, output=_CoverageRow, cost=0)
async def _coverage_input(
    context: SourceContext[_CoverageRow], *, warning: str | None
) -> list[_CoverageRow]:
    """Provide coverage evidence before a dependent HTTP boundary."""
    del context
    return [
        _CoverageRow(
            id=401628347,
            coverage_state=_CoverageStatus.complete
            if warning is not None
            else _CoverageStatus.partial,
            coverage_warning=warning,
        )
    ]


@step(id="tests.native.coverage_finish", revision=1, output=_CoverageRow)
def _coverage_finish(rows: Table, gate: Table) -> Table:
    """Keep the partial rows after the dependent source succeeds."""
    del gate
    return rows.select(*_CoverageRow.model_fields)


@dataset(
    id="tests.native.coverage_recovery",
    revision=1,
    row=_CoverageRow,
    grain="one identifier",
    keys=("id",),
)
def _coverage_recovery(*, warning: str | None) -> RecipeRef[Table]:
    """Retrieve a partial snapshot before an independently recoverable HTTP failure."""
    rows = _coverage_input(warning=warning)
    identity = require_one(rows)
    return _coverage_finish(
        rows, games(game_id=value(identity, path=("id",), expected_type=int))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("warning", ("Coverage caveat", None))
async def test_source_coverage_survives_recovery(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    warning: str | None,
) -> None:
    """Retain reusable warnings and refresh partial sources with unknown reasons."""
    corrected = False

    async def handler(request: web.Request) -> web.Response:
        del request
        return (
            web.json_response([game_response])
            if corrected
            else web.Response(status=400)
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "coverage-fixture",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as failure:
                await _coverage_recovery.run(client, warning=warning)
            corrected = True
            recovered = await _coverage_recovery.run(
                client,
                warning=warning,
                resume_from=failure.value.run_id,
            )
    coverage = next(
        item
        for item in recovered.source_coverage
        if item.operation_id == "tests.native.coverage_input"
    )
    assert coverage.state == "partial"
    assert recovered.warnings == (() if warning is None else (warning,))
    evidence = next(
        node
        for node in recovered.lineage
        if "source:tests.native.coverage_input@1" in node.node_id
    )
    assert evidence.reused is (warning is not None)
    assert recovered.value["coverage_state"].tolist() == [
        "complete" if warning is not None else "partial"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("row_model", (_PropertyCoverageRow, _MixedCoverageRow))
async def test_model_coverage_properties_survive_recovery(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
    row_model: type[BaseModel],
) -> None:
    """Preserve derived evidence through successive resumed snapshots."""
    corrected = False
    executions = 0

    @source(id="tests.native.property_input", revision=1, output=row_model, cost=0)
    async def property_input(context: SourceContext[BaseModel]) -> list[BaseModel]:
        """Return one reusable source with a coverage explanation."""
        nonlocal executions
        del context
        executions += 1
        state_field = (
            "status" if row_model is _PropertyCoverageRow else "coverage_state"
        )
        return [
            row_model.model_validate(
                {"id": 401628347, state_field: "complete", "reason": "Derived warning"}
            )
        ]

    @step(id="tests.native.property_finish", revision=1, output=row_model)
    def property_finish(rows: Table, gate: Table) -> Table:
        """Return the persisted source fields after its dependent source succeeds."""
        del gate
        return rows.select(*row_model.model_fields)

    @dataset(
        id="tests.native.property_recovery",
        revision=1,
        row=row_model,
        grain="one identifier",
        keys=("id",),
    )
    def property_recovery() -> RecipeRef[Table]:
        """Wait for source evidence before attempting the recoverable request."""
        rows = property_input()
        identity = require_one(rows)
        return property_finish(
            rows, games(game_id=value(identity, path=("id",), expected_type=int))
        )

    async def handler(request: web.Request) -> web.Response:
        del request
        return (
            web.json_response([game_response])
            if corrected
            else web.Response(status=400)
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "coverage-properties",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as failure:
                await property_recovery.run(
                    client, policy=ExecutionPolicy(table_partition_rows=1)
                )
            with pytest.raises(CFBDRunError) as second_failure:
                await property_recovery.run(
                    client,
                    resume_from=failure.value.run_id,
                    policy=ExecutionPolicy(table_partition_rows=1),
                )
            corrected = True
            recovered = await property_recovery.run(
                client,
                resume_from=second_failure.value.run_id,
                policy=ExecutionPolicy(table_partition_rows=1),
            )
    assert recovered.warnings == ("Derived warning",)
    coverage = next(
        item
        for item in recovered.source_coverage
        if item.operation_id == "tests.native.property_input"
    )
    assert coverage.state == "partial"
    assert recovered.value["reason"].tolist() == ["Derived warning"]
    assert next(
        node
        for node in recovered.lineage
        if "source:tests.native.property_input@1" in node.node_id
    ).reused
    assert executions == 1


@pytest.mark.asyncio
async def test_partial_checkpoint_with_stale_eligibility_is_refetched(
    api_server: _ServerFactory,
    game_response: dict[str, object],
    tmp_path: Path,
) -> None:
    """Reject partial content despite stale persisted eligibility metadata."""
    corrected = False
    root = tmp_path / "analytics"

    async def handler(request: web.Request) -> web.Response:
        del request
        return (
            web.json_response([game_response])
            if corrected
            else web.Response(status=400)
        )

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "coverage-stale-eligibility",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=root),
        ) as client:
            with pytest.raises(CFBDRunError) as failure:
                await _coverage_recovery.run(client, warning=None)
            # Emulate a restored binding with stale eligibility metadata.
            # Preserve the original immutable binding and artifact content.
            with sqlite3.connect(root / "runs.sqlite3") as connection:
                cursor = connection.execute(
                    "INSERT INTO node_artifact_bindings "
                    "(run_id, node_id, output_name, node_fingerprint, content_digest, "
                    "placement, checkpoint_eligible, committed_at) "
                    "SELECT run_id, node_id || ':restored', output_name, "
                    "node_fingerprint, content_digest, placement, 1, committed_at "
                    "FROM node_artifact_bindings "
                    "WHERE run_id = ? AND node_id LIKE ? AND checkpoint_eligible = 0",
                    (failure.value.run_id, "%source:tests.native.coverage_input@1%"),
                )
                assert cursor.rowcount == 1
            with pytest.raises(CFBDRunError) as second_failure:
                await _coverage_recovery.run(
                    client, warning=None, resume_from=failure.value.run_id
                )
            corrected = True
            recovered = await _coverage_recovery.run(
                client, warning=None, resume_from=second_failure.value.run_id
            )
    assert (
        next(
            item
            for item in recovered.source_coverage
            if item.operation_id == "tests.native.coverage_input"
        ).state
        == "partial"
    )
    assert not next(
        node
        for node in recovered.lineage
        if "source:tests.native.coverage_input@1" in node.node_id
    ).reused


@pytest.mark.parametrize("backend", ("pandas", "dask"))
def test_ordered_records_accept_numpy_integer_ordinals(
    backend: Literal["pandas", "dask"],
) -> None:
    """Order valid native integer record positions across groups and partitions."""
    frame = pd.DataFrame(
        {
            "id": [1, 1],
            "record": [
                {"ordinal": np.int64(2), "label": "second"},
                {"ordinal": np.uint32(1), "label": "first"},
            ],
        }
    )
    native: object = frame
    if backend == "dask":
        import dask
        import dask.dataframe as dd

        with dask.config.set({"dataframe.convert-string": False}):
            native = dd.from_pandas(frame, npartitions=2, sort=False)
    wrapped = nw.from_native(native)
    lazy = wrapped.lazy() if isinstance(wrapped, nw.DataFrame) else wrapped
    result = (
        Table(lazy)
        .ordered_records(
            keys=("id",),
            column="record",
            into="records",
            ordinal_field="ordinal",
        )
        .collect()
    )
    assert result["records"].tolist() == [[{"label": "first"}, {"label": "second"}]]


@pytest.mark.parametrize("ordinal", (True, np.bool_(False), 1.5, "2", None))
def test_ordered_records_reject_noninteger_ordinals(ordinal: object) -> None:
    """Reject booleans and malformed positions without weakening nested ordering."""
    table = Table(
        nw.from_native(
            pd.DataFrame({"id": [1], "record": [{"ordinal": ordinal}]})
        ).lazy()
    )
    with pytest.raises(CFBDTransformError, match="integer ordinal"):
        table.ordered_records(
            keys=("id",), column="record", into="records", ordinal_field="ordinal"
        ).collect()


@step(id="tests.native.invalid_fields", revision=1, output=_Output)
def _invalid_fields(base: Table, empty: Table) -> Table:
    """Reject an invalid source projection even when the source has no rows."""
    return base.enrich(
        empty,
        on=("id",),
        output="extra",
        coverage="extra_coverage",
        fields={"misspelled": "value"},
        message="Invalid fixture",
    ).select("id", "value")


@dataset(
    id="tests.native.invalid_fields_dataset",
    revision=1,
    row=_Output,
    grain="one fixture identifier",
    keys=("id",),
    order_by=("id",),
)
def _invalid_fields_dataset() -> RecipeRef[Table]:
    """Declare separate populated and validated empty source boundaries."""
    return _invalid_fields(_input(), _input.as_("empty")(empty=True))


@workflow(id="tests.native.null_list", revision=1)
def _null_list(*, values: list[None]) -> dict[str, RecipeRef[Table]]:
    """Retain a literal list annotation without treating it as an optional value."""
    del values
    return {"rows": _native_dataset()}


@pytest.mark.asyncio
async def test_empty_source_still_validates_requested_fields(tmp_path: Path) -> None:
    """Reject a misspelled enrichment column instead of silently returning nulls."""
    async with CFBDClient(
        "offline-native", analytics=AnalyticsConfig(root=tmp_path / "analytics")
    ) as client:
        with pytest.raises(CFBDRunError) as failure:
            await _invalid_fields_dataset.run(client)
    assert failure.value.category == "CFBDTransformError"


@pytest.mark.asyncio
async def test_none_is_not_accepted_as_a_literal_list() -> None:
    """Validate nullable container elements independently from nullable containers."""
    async with CFBDClient("offline-native") as client:
        with pytest.raises(CFBDRecipeParameterError):
            await _null_list.plan(client, values=None)


def test_native_group_ordinals_restart_across_partitions() -> None:
    """Retain zero-based order independently for groups spanning partitions."""
    import dask.dataframe as dd

    frame = pd.DataFrame(
        {"season": [2024, 2024, 2024, 2025, 2025, 2025], "rank": [3, 1, 2, 2, 3, 1]}
    )
    table = Table(nw.from_native(dd.from_pandas(frame, npartitions=3)))
    rows = (
        table.sort("season", "rank")
        .with_group_index("ordinal", keys=("season",))
        .collect()
    )
    assert rows["season"].tolist() == [2024] * 3 + [2025] * 3
    assert rows["ordinal"].tolist() == [0, 1, 2, 0, 1, 2]


@pytest.mark.asyncio
async def test_cancelled_native_partitions_cleanup_without_publication(
    tmp_path: Path,
) -> None:
    """Cancel after real worker output and keep the dataset unpublished."""
    pytest.importorskip("distributed")
    progress = asyncio.Event()
    events: list[AnalyticsEvent] = []

    def observe(event: AnalyticsEvent) -> None:
        events.append(event)
        if event.event_type == AnalyticsEventType.partition_completed:
            progress.set()

    root = tmp_path / "analytics"
    async with CFBDClient(
        "offline-native", analytics=AnalyticsConfig(root=root, observer=observe)
    ) as client:
        task = asyncio.create_task(
            _native_dataset.run(
                client,
                policy=ExecutionPolicy(
                    executor="dask",
                    dask_max_workers=2,
                    table_partition_rows=1,
                    checkpoint_mode="off",
                ),
            )
        )
        await asyncio.wait_for(progress.wait(), timeout=20)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert any(event.event_type == AnalyticsEventType.run_cancelled for event in events)
    assert not any(
        event.event_type == AnalyticsEventType.artifact_committed
        and event.node_id is not None
        and event.node_id.startswith("dataset:tests.native.dataset@")
        for event in events
    )
    assert not any((root / "workers").iterdir())
