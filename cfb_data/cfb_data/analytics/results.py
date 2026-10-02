"""Expose immutable recipe results and opaque artifact references."""

from __future__ import annotations

import os
import types
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, TypeVar, cast, overload

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _PandasAdapter, _PolarsAdapter
from cfb_data._tabular import (
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
)

from ._artifacts import _ArtifactManifest, _ArtifactPart, _TableArtifactCodec
from ._persistence import _ArtifactObjectStore, _StoredArtifact
from .errors import CFBDArtifactCodecError
from .tables import Table

if TYPE_CHECKING:
    import polars as pl

OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class ArtifactColumn:
    """Describe one ordered analytical column without Python model identity."""

    name: str
    nullable: bool
    description: str | None
    unit: str | None
    semantic_type: str | None


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """Report one stable successful artifact validation."""

    check: Literal[
        "row_contract",
        "candidate_key_uniqueness",
        "deterministic_order",
    ]
    outcome: Literal["passed"]
    rows_checked: int


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Describe stable validated artifact content without exposing its path."""

    content_digest: str
    kind: str
    codec_id: str
    codec_version: int
    media_type: str
    output_id: str
    output_revision: int
    schema_digest: str
    row_count: int | None
    byte_count: int
    grain: str | None
    keys: tuple[str, ...]
    order_by: tuple[str, ...]
    partition_by: tuple[str, ...]
    event_time: str | None
    columns: tuple[ArtifactColumn, ...]
    quality: tuple[QualityCheck, ...]


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Load or export one immutable artifact after its client has closed."""

    descriptor: ArtifactDescriptor
    _root: Path = field(repr=False, compare=False)
    _manifest: _ArtifactManifest = field(repr=False, compare=False)
    _row_model: type[BaseModel] = field(repr=False, compare=False)

    @classmethod
    def _from_stored(
        cls,
        *,
        root: Path,
        artifact: _StoredArtifact,
        row_model: type[BaseModel],
    ) -> ArtifactRef:
        return cls(
            descriptor=_artifact_descriptor(artifact.manifest),
            _root=root,
            _manifest=artifact.manifest,
            _row_model=row_model,
        )

    @overload
    def load(self, *, backend: Literal["pandas"] = "pandas") -> pd.DataFrame: ...

    @overload
    def load(self, *, backend: Literal["polars"]) -> pl.DataFrame: ...

    def load(self, *, backend: Literal["pandas", "polars"] = "pandas") -> object:
        """Return a fully validated eager frame from durable content.

        :param backend: Eager DataFrame implementation to materialize.
        :return: Validated pandas or Polars DataFrame.
        :raises CFBDArtifactCodecError: If this reference is not a table artifact.
        :raises CFBDArtifactCorruptionError: If durable content fails validation.
        """
        rows = self._load_rows()
        adapter = _PandasAdapter() if backend == "pandas" else _PolarsAdapter()
        return adapter.from_models(
            endpoint=self.descriptor.output_id,
            row_model=self._row_model,
            models=rows,
        )

    def batches(self, *, batch_rows: int = 16_384) -> Iterator[pd.DataFrame]:
        """Read validated pandas batches without collecting the whole artifact.

        :param batch_rows: Positive maximum rows returned in each batch.
        :return: Owned pandas batches in declared artifact order.
        :raises CFBDArtifactCodecError: If the artifact is not a table.
        :raises CFBDArtifactCorruptionError: If a part fails validation.
        :raises ValueError: If the batch row bound is invalid.
        """
        if (
            isinstance(batch_rows, bool)
            or not isinstance(batch_rows, int)
            or batch_rows < 1
        ):
            raise ValueError("batch_rows must be a positive integer")
        identity = _AnalyticsTableIdentity(
            self.descriptor.output_id, self.descriptor.output_revision
        )
        store = _ArtifactObjectStore(self._root, create=False)
        for table in _TableArtifactCodec().iter_tables(
            directory=store.directory(self.descriptor.content_digest),
            manifest=self._manifest,
            row_model=self._row_model,
            identity=identity,
        ):
            for offset in range(0, max(1, table.num_rows), batch_rows):
                yield _part_frame(
                    table.slice(offset, batch_rows), self._row_model, identity
                )

    def scan(
        self, *, partition_rows: int = 16_384, source_ordinal: bool = False
    ) -> Table:
        """Build a lazy native Dask scan from immutable validated parts.

        :param partition_rows: Positive target rows in compute partitions.
        :param source_ordinal: Include internal global source ordering evidence.
        :return: Lazy table independent of the original client and cluster.
        :raises CFBDArtifactCorruptionError: If manifest or computed parts fail validation.
        :raises ValueError: If partition sizing is invalid.
        """
        import dask
        import dask.dataframe as dd
        import narwhals.stable.v2 as nw
        from dask.delayed import Delayed, delayed
        from narwhals.stable.v2.typing import IntoLazyFrame

        from .tables import SOURCE_ORDINAL

        if (
            isinstance(partition_rows, bool)
            or not isinstance(partition_rows, int)
            or partition_rows < 1
        ):
            raise ValueError("partition_rows must be a positive integer")
        identity = _AnalyticsTableIdentity(
            self.descriptor.output_id, self.descriptor.output_revision
        )
        store = _ArtifactObjectStore(self._root, create=False)
        directory = store.directory(self.descriptor.content_digest)
        checked = _TableArtifactCodec().inspect(
            directory=directory,
            manifest=self._manifest,
            row_model=self._row_model,
            identity=identity,
        )
        meta = _PandasAdapter().from_models(
            endpoint=identity.output_id,
            row_model=self._row_model,
            models=[],
        )
        if source_ordinal:
            meta[SOURCE_ORDINAL] = pd.Series(dtype="int64")
        tasks: list[Delayed] = []
        offset = 0
        for part in checked.body.parts:
            tasks.append(
                delayed(_read_native_part)(
                    directory,
                    part,
                    self._row_model,
                    identity,
                    checked.content_digest,
                    offset if source_ordinal else None,
                )
            )
            offset += part.row_count or 0
        with dask.config.set({"dataframe.convert-string": False}):
            native = dd.from_delayed(tasks, meta=meta, verify_meta=True)
            desired = max(1, (offset + partition_rows - 1) // partition_rows)
            native = native.repartition(npartitions=desired)
        wrapped: object = nw.from_native(native)
        if not isinstance(wrapped, nw.LazyFrame):
            raise TypeError("Artifact scan did not produce a lazy dataframe")
        return Table(
            cast(nw.LazyFrame[IntoLazyFrame], wrapped),
            _known_empty=checked.body.row_count == 0,
        )

    def export_parquet(self, destination: Path | str) -> Path:
        """Atomically export one validated table as a standalone Parquet file.

        :param destination: Explicit output file, including its filename.
        :return: Resolved destination path.
        :raises CFBDArtifactCodecError: If this reference is not a table artifact.
        :raises CFBDArtifactCorruptionError: If durable content fails validation.
        """
        identity = _AnalyticsTableIdentity(
            self.descriptor.output_id, self.descriptor.output_revision
        )
        store = _ArtifactObjectStore(self._root, create=False)
        parts = _TableArtifactCodec().iter_tables(
            directory=store.directory(self.descriptor.content_digest),
            manifest=self._manifest,
            row_model=self._row_model,
            identity=identity,
        )
        first = next(parts)
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.parent / f".{target.name}.stage-{uuid.uuid4().hex}"
        try:
            with pq.ParquetWriter(
                temporary,
                first.schema,
                version="2.6",
                compression="zstd",
                write_statistics=True,
                use_compliant_nested_type=True,
                store_schema=True,
            ) as writer:
                writer.write_table(first)
                for part in parts:
                    writer.write_table(part)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def _load_table(self) -> pa.Table:
        if self.descriptor.kind != "table":
            raise CFBDArtifactCodecError(
                codec_id=self.descriptor.codec_id,
                category="artifact_kind",
            )
        identity = _AnalyticsTableIdentity(
            output_id=self.descriptor.output_id,
            revision=self.descriptor.output_revision,
        )
        store = _ArtifactObjectStore(self._root, create=False)
        return _TableArtifactCodec().load(
            directory=store.directory(self.descriptor.content_digest),
            manifest=self._manifest,
            row_model=self._row_model,
            identity=identity,
        )

    def _load_rows(self) -> list[BaseModel]:
        identity = _AnalyticsTableIdentity(
            output_id=self.descriptor.output_id,
            revision=self.descriptor.output_revision,
        )
        table = self._load_table()
        annotation = types.GenericAlias(list, self._row_model)
        adapter = cast(TypeAdapter[list[BaseModel]], TypeAdapter(annotation))
        return _analytics_models_from_arrow_table(
            row_model=self._row_model,
            response_adapter=adapter,
            table=table,
            identity=identity,
        )


def _part_frame(
    table: pa.Table,
    row_model: type[BaseModel],
    identity: _AnalyticsTableIdentity,
) -> pd.DataFrame:
    """Decode and validate one bounded canonical partition into pandas."""
    adapter = cast(
        TypeAdapter[list[BaseModel]], TypeAdapter(types.GenericAlias(list, row_model))
    )
    rows = _analytics_models_from_arrow_table(
        row_model=row_model,
        response_adapter=adapter,
        table=table,
        identity=identity,
    )
    return _PandasAdapter().from_models(
        endpoint=identity.output_id,
        row_model=row_model,
        models=rows,
    )


def _read_native_part(
    directory: Path,
    part: _ArtifactPart,
    row_model: type[BaseModel],
    identity: _AnalyticsTableIdentity,
    content_digest: str,
    source_offset: int | None,
) -> pd.DataFrame:
    """Validate one native scan partition with optional source-order evidence."""
    from .tables import SOURCE_ORDINAL

    table = _TableArtifactCodec().read_part(
        directory=directory,
        part=part,
        row_model=row_model,
        identity=identity,
        content_digest=content_digest,
    )
    frame = _part_frame(table, row_model, identity)
    if source_offset is not None:
        frame[SOURCE_ORDINAL] = range(source_offset, source_offset + len(frame))
    return frame


def _artifact_descriptor(manifest: _ArtifactManifest) -> ArtifactDescriptor:
    """Project a validated private manifest into its safe public descriptor."""
    body = manifest.body
    table = body.table
    return ArtifactDescriptor(
        content_digest=manifest.content_digest,
        kind=body.kind,
        codec_id=body.codec_id,
        codec_version=body.codec_version,
        media_type=body.media_type,
        output_id=body.output_id,
        output_revision=body.output_revision,
        schema_digest=body.schema_digest,
        row_count=body.row_count,
        byte_count=sum(part.size_bytes for part in body.parts),
        grain=None if table is None else table.grain,
        keys=() if table is None else table.keys,
        order_by=() if table is None else table.order_by,
        partition_by=() if table is None else table.partition_by,
        event_time=None if table is None else table.event_time,
        columns=(
            ()
            if table is None
            else tuple(
                ArtifactColumn(
                    name=column.name,
                    nullable=column.nullable,
                    description=column.description,
                    unit=column.unit,
                    semantic_type=column.semantic_type,
                )
                for column in table.columns
            )
        ),
        quality=(
            ()
            if table is None
            else tuple(
                QualityCheck(
                    check=result.check,
                    outcome=result.outcome,
                    rows_checked=result.rows_checked,
                )
                for result in table.quality
            )
        ),
    )


class WorkflowOutputs[OutputT](Mapping[str, OutputT]):
    """Expose immutable named workflow outputs in declaration order."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, OutputT]) -> None:
        """Freeze validated named outputs.

        :param values: Outputs in workflow declaration order.
        """
        self._values = MappingProxyType(dict(values))

    def __getitem__(self, name: str) -> OutputT:
        """Return one named workflow output."""
        return self._values[name]

    def __iter__(self) -> Iterator[str]:
        """Iterate output names in declared order."""
        return iter(self._values)

    def __len__(self) -> int:
        """Return the number of named workflow outputs."""
        return len(self._values)


@dataclass(frozen=True, slots=True)
class RecipeSourceCoverage:
    """Report source availability and known partial coverage."""

    node_id: str
    operation_id: str
    access_tier: Literal["free", "tier_1", "tier_2", "custom"]
    state: Literal["empty", "present", "partial"]
    row_count: int


@dataclass(frozen=True, slots=True)
class RunNodeEvidence:
    """Report one successful node binding without paths or parameters."""

    node_id: str
    node_kind: Literal["source", "step", "dataset", "workflow"]
    output_name: str
    content_digest: str
    placement: Literal["coordinator", "local", "dask"]
    checkpoint_eligible: bool
    reused: bool


@dataclass(frozen=True, slots=True)
class RecipeRun[OutputT]:
    """Return one immutable recipe result with durable execution evidence."""

    run_id: str
    parent_run_id: str | None
    value: OutputT
    artifacts: Mapping[str, ArtifactRef]
    source_coverage: tuple[RecipeSourceCoverage, ...]
    warnings: tuple[str, ...]
    quality: Mapping[str, tuple[QualityCheck, ...]]
    lineage: tuple[RunNodeEvidence, ...]
    actual_http_attempts: int
    reused_nodes: int

    @property
    def artifact(self) -> ArtifactRef:
        """Return the sole dataset artifact.

        :return: Dataset output artifact.
        :raises ValueError: If this run has multiple named workflow outputs.
        """
        if tuple(self.artifacts) != ("value",):
            raise ValueError("Workflow runs expose artifacts by output name")
        return self.artifacts["value"]


__all__ = [
    "ArtifactColumn",
    "ArtifactDescriptor",
    "ArtifactRef",
    "QualityCheck",
    "RecipeRun",
    "RecipeSourceCoverage",
    "RunNodeEvidence",
    "WorkflowOutputs",
]
