"""Define immutable public contracts for datasets and workflows."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from pydantic import BaseModel

from cfb_data.base.types import JSONValue
from cfb_data.errors import CFBDConfigurationError, CFBDDefinitionError

_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")


class CheckpointMode(StrEnum):
    """Control which successful analytics steps are persisted."""

    all = "all"
    outputs_only = "outputs_only"
    off = "off"


class RecoverySourcePolicy(StrEnum):
    """Control source behavior when recovering an immutable run snapshot."""

    preserve_snapshot = "preserve_snapshot"
    normal_freshness = "normal_freshness"
    refresh = "refresh"


class EnrichmentFailurePolicy(StrEnum):
    """Control whether requested enrichment failures stop execution."""

    fail = "fail"
    record = "record"


class TransformBackend(StrEnum):
    """Identify the backend contract of one registered transform."""

    portable = "portable"
    pandas = "pandas"
    polars = "polars"


class CoverageState(StrEnum):
    """Describe the observed completeness state of one source or enrichment."""

    not_requested = "not_requested"
    unavailable_access = "unavailable_access"
    empty = "empty"
    partial = "partial"
    present = "present"
    failed = "failed"


@dataclass(frozen=True, slots=True)
class ColumnMetadata:
    """Describe analyst-facing meaning attached to one table column.

    :param description: Concise semantic description.
    :param units: Optional unit label such as ``points`` or ``probability``.
    :param semantic_type: Optional namespaced or built-in semantic category.
    """

    description: str
    units: str | None = None
    semantic_type: str | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise CFBDDefinitionError("Column descriptions must be non-empty")


@dataclass(frozen=True, slots=True)
class TableContract[RowT: BaseModel]:
    """Declare the authoritative row and cross-row contract for one table.

    :param id: Stable namespaced output identity.
    :param revision: Positive semantic contract revision.
    :param row_model: Authoritative Pydantic model for every row.
    :param grain: Human-readable declaration of one row's meaning.
    :param keys: Candidate-key fields that must be unique.
    :param order_by: Deterministic output ordering fields.
    :param partition_by: Optional deterministic physical partition fields.
    :param event_time: Optional column representing the row's event time.
    :param columns: Optional immutable analyst-facing column metadata.
    """

    id: str
    revision: int
    row_model: type[RowT]
    grain: str
    keys: tuple[str, ...]
    order_by: tuple[str, ...]
    partition_by: tuple[str, ...] = ()
    event_time: str | None = None
    columns: Mapping[str, ColumnMetadata] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_stable_id("table contract", self.id)
        if self.revision < 1:
            raise CFBDDefinitionError("Table contract revision must be positive")
        if not self.grain.strip():
            raise CFBDDefinitionError("Table contract grain must be non-empty")
        field_names = tuple(self.row_model.model_fields)
        if not self.keys:
            raise CFBDDefinitionError("Table contracts must declare a candidate key")
        for role, names in (
            ("key", self.keys),
            ("ordering", self.order_by),
            ("partition", self.partition_by),
        ):
            if len(names) != len(set(names)):
                raise CFBDDefinitionError(f"Duplicate {role} fields are not allowed")
            unknown = set(names).difference(field_names)
            if unknown:
                raise CFBDDefinitionError(
                    f"Unknown {role} fields for {self.id}: {sorted(unknown)!r}"
                )
        if self.event_time is not None and self.event_time not in field_names:
            raise CFBDDefinitionError(
                f"Unknown event-time field for {self.id}: {self.event_time}"
            )
        if (
            self.partition_by
            and self.order_by[: len(self.partition_by)] != self.partition_by
        ):
            raise CFBDDefinitionError(
                "Partition fields must be the leading deterministic ordering fields"
            )
        unknown_columns = set(self.columns).difference(field_names)
        if unknown_columns:
            raise CFBDDefinitionError(
                f"Unknown column metadata fields for {self.id}: "
                f"{sorted(unknown_columns)!r}"
            )
        object.__setattr__(self, "columns", MappingProxyType(dict(self.columns)))

    @property
    def schema_digest(self) -> str:
        """Return a stable digest of the ordered Pydantic schema.

        :return: SHA-256 hexadecimal digest of the canonical JSON schema.
        """
        encoded = json.dumps(
            self.row_model.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ParameterBinding:
    """Bind one source request field to a validated definition parameter."""

    parameter: str


@dataclass(frozen=True, slots=True)
class LiteralBinding:
    """Bind one source request field to a canonical JSON literal."""

    value: JSONValue


type ValueBinding = ParameterBinding | LiteralBinding


@dataclass(frozen=True, slots=True)
class SourceNode:
    """Declare one validated endpoint retrieval in an analytics graph."""

    id: str
    operation_id: str
    operation_revision: int
    bindings: Mapping[str, ValueBinding]
    output: TableContract[BaseModel]

    def __post_init__(self) -> None:
        _validate_node(self.id, self.operation_id, self.operation_revision)
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))


@dataclass(frozen=True, slots=True)
class TransformNode:
    """Declare one pure registered transformation in an analytics graph."""

    id: str
    operation_id: str
    operation_revision: int
    inputs: tuple[str, ...]
    output: TableContract[BaseModel]
    config: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_node(self.id, self.operation_id, self.operation_revision)
        if not self.inputs:
            raise CFBDDefinitionError("Transform nodes require at least one input")
        if len(self.inputs) != len(set(self.inputs)):
            raise CFBDDefinitionError("Transform inputs must not be duplicated")
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))


type DefinitionNode = SourceNode | TransformNode


@dataclass(frozen=True, slots=True)
class DatasetDefinition[ParamsT: BaseModel, RowT: BaseModel]:
    """Define one backend-neutral analytical table product."""

    id: str
    revision: int
    parameter_model: type[ParamsT]
    nodes: tuple[DefinitionNode, ...]
    output_node: str
    output: TableContract[RowT]
    description: str

    def __post_init__(self) -> None:
        _validate_definition_header(self.id, self.revision, self.description)
        _validate_graph(self.nodes, {"result": self.output_node})
        node = next(item for item in self.nodes if item.id == self.output_node)
        if node.output.id != self.output.id:
            raise CFBDDefinitionError(
                "Dataset output contract must match its output node contract"
            )


@dataclass(frozen=True, slots=True)
class WorkflowDefinition[ParamsT: BaseModel]:
    """Define one finite graph producing several named analytical tables."""

    id: str
    revision: int
    parameter_model: type[ParamsT]
    nodes: tuple[DefinitionNode, ...]
    outputs: Mapping[str, str]
    description: str

    def __post_init__(self) -> None:
        _validate_definition_header(self.id, self.revision, self.description)
        copied = dict(self.outputs)
        if not copied:
            raise CFBDDefinitionError("Workflows must declare named outputs")
        for name in copied:
            if not name or not name.replace("_", "").isalnum():
                raise CFBDDefinitionError(f"Invalid workflow output name: {name!r}")
        _validate_graph(self.nodes, copied)
        object.__setattr__(self, "outputs", MappingProxyType(copied))


type AnalyticsDefinition = (
    DatasetDefinition[BaseModel, BaseModel] | WorkflowDefinition[BaseModel]
)


class RecordTransform(Protocol):
    """Execute a pure transform over validated source and intermediate rows."""

    def __call__(
        self,
        inputs: Mapping[str, Sequence[BaseModel]],
        parameters: BaseModel,
        config: Mapping[str, JSONValue],
    ) -> Sequence[BaseModel]:
        """Return rows satisfying the transform's declared output contract."""


class FrameTransform(Protocol):
    """Execute a user transform over isolated backend DataFrame inputs."""

    def __call__(
        self,
        inputs: Mapping[str, object],
        parameters: BaseModel,
        config: Mapping[str, JSONValue],
    ) -> object:
        """Return one backend DataFrame matching the declared output contract."""


@dataclass(frozen=True, slots=True)
class RegisteredTransform:
    """Bind a stable transform identity to one pure callable."""

    id: str
    revision: int
    backend: TransformBackend
    deterministic: bool
    callable: RecordTransform | FrameTransform = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_stable_id("transform", self.id)
        if self.revision < 1:
            raise CFBDDefinitionError("Transform revision must be positive")


@dataclass(frozen=True, slots=True)
class TransformRegistry(Mapping[str, RegisteredTransform]):
    """Provide an immutable explicit transform registry without global state."""

    _items: Mapping[str, RegisteredTransform] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied = dict(self._items)
        for key, transform in copied.items():
            if key != transform.id:
                raise CFBDDefinitionError("Transform registry keys must match IDs")
        object.__setattr__(self, "_items", MappingProxyType(copied))

    def __getitem__(self, key: str) -> RegisteredTransform:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def extended(self, transforms: Sequence[RegisteredTransform]) -> TransformRegistry:
        """Return a new registry containing non-conflicting additions.

        :param transforms: Explicit transforms to register.
        :return: New immutable registry.
        :raises CFBDDefinitionError: If an ID is already registered.
        """
        copied = dict(self._items)
        for transform in transforms:
            if transform.id in copied:
                raise CFBDDefinitionError(
                    f"Transform is already registered: {transform.id}"
                )
            copied[transform.id] = transform
        return TransformRegistry(copied)


@dataclass(frozen=True, slots=True)
class DatasetCatalog(Mapping[str, AnalyticsDefinition]):
    """Provide an immutable explicit dataset and workflow definition catalog."""

    _items: Mapping[str, AnalyticsDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied = dict(self._items)
        for key, definition in copied.items():
            if key != definition.id:
                raise CFBDDefinitionError("Catalog keys must match definition IDs")
        object.__setattr__(self, "_items", MappingProxyType(copied))

    def __getitem__(self, key: str) -> AnalyticsDefinition:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def extended(self, definitions: Sequence[AnalyticsDefinition]) -> DatasetCatalog:
        """Return a new catalog containing non-conflicting definitions."""
        copied = dict(self._items)
        for definition in definitions:
            if definition.id in copied:
                raise CFBDDefinitionError(
                    f"Analytics definition is already registered: {definition.id}"
                )
            copied[definition.id] = definition
        return DatasetCatalog(copied)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Configure safe scheduling without weakening analytical validation."""

    retrieval_concurrency: int = 4
    compute_concurrency: int = 1
    max_http_attempts: int = 100
    max_expanded_nodes: int = 10_000
    checkpoint: CheckpointMode = CheckpointMode.all
    source_policy: RecoverySourcePolicy = RecoverySourcePolicy.preserve_snapshot
    enrichment_failure: EnrichmentFailurePolicy = EnrichmentFailurePolicy.fail
    allow_partial: bool = False
    force_steps: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in (
            "retrieval_concurrency",
            "compute_concurrency",
            "max_http_attempts",
            "max_expanded_nodes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise CFBDConfigurationError(f"{name} must be a positive integer")
        if not isinstance(self.allow_partial, bool):
            raise CFBDConfigurationError("allow_partial must be a boolean")


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    """Configure the lazily opened local analytics subsystem.

    :param path: Explicit artifact-store directory, or the platform default.
    :param policy: Default immutable execution policy.
    :param catalog: Optional explicit user definitions added to built-ins.
    :param transforms: Optional explicit user transforms added to built-ins.
    :param observer: Optional synchronous analytics-event observer.
    """

    path: Path | None = None
    policy: ExecutionPolicy = ExecutionPolicy()
    catalog: DatasetCatalog = DatasetCatalog()
    transforms: TransformRegistry = TransformRegistry()
    observer: Callable[[object], None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.path is not None and not isinstance(self.path, Path):
            raise CFBDConfigurationError("Analytics path must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """Describe one safe, value-free step in an execution plan."""

    id: str
    kind: str
    dependencies: tuple[str, ...]
    operation_id: str
    checkpoint_candidate: bool


@dataclass(frozen=True, slots=True)
class DatasetPlan:
    """Describe a compiled dataset graph without performing HTTP I/O."""

    definition_id: str
    definition_revision: int
    parameter_fingerprint: str
    steps: tuple[PlannedStep, ...]
    logical_source_requests: int
    worst_case_http_attempts: int


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Describe a compiled workflow graph without performing HTTP I/O."""

    definition_id: str
    definition_revision: int
    parameter_fingerprint: str
    steps: tuple[PlannedStep, ...]
    outputs: tuple[str, ...]
    logical_source_requests: int
    worst_case_http_attempts: int


@dataclass(frozen=True, slots=True)
class QualityResult:
    """Report one bounded table-level validation outcome."""

    check: str
    passed: bool
    affected_rows: int


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    """Report the completeness state of one source without exposing selectors."""

    source_id: str
    state: CoverageState
    row_count: int


def parameter_fingerprint(parameters: BaseModel) -> str:
    """Return a stable SHA-256 fingerprint for validated parameters.

    :param parameters: Strictly validated definition parameters.
    :return: Hexadecimal digest preserving omitted/null/false/zero distinctions.
    """
    payload = parameters.model_dump_json(
        by_alias=True,
        exclude_none=False,
        exclude_unset=False,
        round_trip=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    """Encode a finite JSON value deterministically for fingerprints.

    :param value: JSON-compatible value.
    :return: Canonical UTF-8 JSON bytes.
    :raises CFBDDefinitionError: If a value is not finite or JSON-compatible.
    """
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CFBDDefinitionError("Definition values must be finite JSON") from exc
    return encoded.encode()


def _validate_stable_id(kind: str, value: str) -> None:
    if not _STABLE_ID.fullmatch(value):
        raise CFBDDefinitionError(
            f"{kind.capitalize()} IDs must be lowercase and namespaced: {value!r}"
        )


def _validate_node(node_id: str, operation_id: str, revision: int) -> None:
    if not node_id or not node_id.replace("_", "").isalnum():
        raise CFBDDefinitionError(f"Invalid node ID: {node_id!r}")
    _validate_stable_id("operation", operation_id)
    if revision < 1:
        raise CFBDDefinitionError("Operation revisions must be positive")


def _validate_definition_header(id: str, revision: int, description: str) -> None:
    _validate_stable_id("definition", id)
    if revision < 1:
        raise CFBDDefinitionError("Definition revision must be positive")
    if not description.strip():
        raise CFBDDefinitionError("Definition description must be non-empty")


def _validate_graph(
    nodes: tuple[DefinitionNode, ...], outputs: Mapping[str, str]
) -> None:
    if not nodes:
        raise CFBDDefinitionError("Definitions require at least one node")
    by_id = {node.id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise CFBDDefinitionError("Definition node IDs must be unique")
    unknown_outputs = set(outputs.values()).difference(by_id)
    if unknown_outputs:
        raise CFBDDefinitionError(f"Unknown output nodes: {sorted(unknown_outputs)!r}")
    for node in nodes:
        if isinstance(node, TransformNode):
            unknown = set(node.inputs).difference(by_id)
            if unknown:
                raise CFBDDefinitionError(
                    f"Node {node.id} has unknown inputs: {sorted(unknown)!r}"
                )

    state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        status = state.get(node_id, 0)
        if status == 1:
            raise CFBDDefinitionError("Definition graph contains a cycle")
        if status == 2:
            return
        state[node_id] = 1
        node = by_id[node_id]
        if isinstance(node, TransformNode):
            for dependency in node.inputs:
                visit(dependency)
        state[node_id] = 2

    for node_id in by_id:
        visit(node_id)


__all__ = [
    "AnalyticsConfig",
    "CheckpointMode",
    "ColumnMetadata",
    "CoverageState",
    "DatasetCatalog",
    "DatasetDefinition",
    "DatasetPlan",
    "EnrichmentFailurePolicy",
    "ExecutionPolicy",
    "FrameTransform",
    "LiteralBinding",
    "ParameterBinding",
    "PlannedStep",
    "QualityResult",
    "RecordTransform",
    "RecoverySourcePolicy",
    "RegisteredTransform",
    "SourceCoverage",
    "SourceNode",
    "TableContract",
    "TransformBackend",
    "TransformNode",
    "TransformRegistry",
    "WorkflowDefinition",
    "WorkflowPlan",
]
