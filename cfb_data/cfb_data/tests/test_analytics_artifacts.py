"""Test multipart table and bounded model artifacts at the public store boundary."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest
from cfb_data._tabular import _arrow_table_from_models
from pydantic import BaseModel, ConfigDict

from cfb_data import LocalArtifactStore, TableContract


class _PartitionRow(BaseModel):
    """Represent one row in a deterministic season partition."""

    model_config = ConfigDict(extra="forbid")
    season: int
    item_id: int
    value: str | None


class _ControlModel(BaseModel):
    """Represent one bounded workflow control artifact."""

    model_config = ConfigDict(extra="forbid")
    state: str
    count: int


@pytest.mark.asyncio
async def test_partitioned_table_round_trip_and_consolidated_export(
    tmp_path: Path,
) -> None:
    """Publish ordered immutable parts and export them as one validated file."""
    store = await LocalArtifactStore(tmp_path / "store").open()
    contract = TableContract(
        id="test.dataset.partitioned",
        revision=1,
        row_model=_PartitionRow,
        grain="one item in one season",
        keys=("season", "item_id"),
        order_by=("season", "item_id"),
        partition_by=("season",),
    )
    rows = [
        _PartitionRow(season=2023, item_id=2, value=None),
        _PartitionRow(season=2024, item_id=1, value="x"),
    ]
    await store.begin_run(
        run_id="run",
        definition_id="test.partitioned",
        definition_revision=1,
        parameter_fingerprint="parameters",
        parent_run_id=None,
    )
    artifact = await store.write_table(
        run_id="run",
        step_id="result",
        fingerprint="node",
        definition_id="test.partitioned",
        definition_revision=1,
        contract=contract,
        table=_arrow_table_from_models(row_model=_PartitionRow, models=rows),
        upstream_digests=(),
        source_fetched_at=None,
        source_validated_at=None,
        quality=(),
        coverage=(),
    )
    await store.finish_run("run", status="success")
    await store.close()

    assert len(artifact.descriptor.parts) == 2
    assert artifact.descriptor.partition_by == ("season",)
    assert artifact.load_table().num_rows == 2
    destination = artifact.export_parquet(tmp_path / "export.parquet")
    assert pq.read_table(destination).num_rows == 2


@pytest.mark.asyncio
async def test_bounded_json_model_round_trip(tmp_path: Path) -> None:
    """Load canonical JSON only through its explicitly supplied model contract."""
    store = await LocalArtifactStore(tmp_path / "store").open()
    await store.begin_run(
        run_id="run",
        definition_id="test.control",
        definition_revision=1,
        parameter_fingerprint="parameters",
        parent_run_id=None,
    )
    artifact = await store.write_json(
        run_id="run",
        step_id="control",
        fingerprint="node",
        definition_id="test.control",
        definition_revision=1,
        contract_id="test.control.output",
        contract_revision=1,
        model=_ControlModel(state="ready", count=2),
    )
    await store.finish_run("run", status="success")
    await store.close()

    assert artifact.load_model(_ControlModel) == _ControlModel(state="ready", count=2)
