"""Verify native partitioned recipe execution through public interfaces."""

from __future__ import annotations

import asyncio
from pathlib import Path

import narwhals.stable.v2 as nw
import pandas as pd
import pytest
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
    source,
    step,
    workflow,
)
from pydantic import BaseModel, Field

from cfb_data import CFBDClient


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
