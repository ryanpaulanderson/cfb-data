"""Derive stable table semantics for content-bound artifact manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)


class _ArtifactColumn(BaseModel):
    """Describe one ordered logical field without Python model identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1, max_length=256)
    nullable: bool
    description: str | None = Field(default=None, max_length=4_096)
    unit: str | None = Field(default=None, max_length=128)
    semantic_type: str | None = Field(default=None, max_length=128)


class _ArtifactQualityCheck(BaseModel):
    """Record one stable successful validation without retaining row values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    check: Literal[
        "row_contract",
        "candidate_key_uniqueness",
        "deterministic_order",
    ]
    outcome: Literal["passed"] = "passed"
    rows_checked: int = Field(ge=0)


class _TableArtifactContract(BaseModel):
    """Bind table semantics and quality evidence to immutable content."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    grain: str | None = Field(default=None, max_length=512)
    keys: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    partition_by: tuple[str, ...] = ()
    event_time: str | None = Field(default=None, max_length=256)
    columns: tuple[_ArtifactColumn, ...] = Field(min_length=1)
    quality: tuple[_ArtifactQualityCheck, ...] = Field(min_length=1)

    @field_validator("grain")
    @classmethod
    def validate_grain(cls, value: str | None) -> str | None:
        """Reject whitespace-only grain declarations."""
        if value is not None and not value.strip():
            raise ValueError("Artifact grain cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_references(self) -> _TableArtifactContract:
        """Require unique columns, checks, and valid field references."""
        column_names = tuple(column.name for column in self.columns)
        if len(set(column_names)) != len(column_names):
            raise ValueError("Artifact columns must be unique")
        available = frozenset(column_names)
        for label, names in (
            ("keys", self.keys),
            ("order_by", self.order_by),
            ("partition_by", self.partition_by),
        ):
            if len(set(names)) != len(names) or any(
                name not in available for name in names
            ):
                raise ValueError(f"Artifact {label} contains invalid fields")
        if self.event_time is not None and self.event_time not in available:
            raise ValueError("Artifact event_time is not a declared column")
        checks = tuple(result.check for result in self.quality)
        if len(set(checks)) != len(checks):
            raise ValueError("Artifact quality checks must be unique")
        return self


@dataclass(frozen=True, slots=True)
class _DatasetContractEvidence:
    """Carry one compiled dataset declaration into the table codec."""

    grain: str
    keys: tuple[str, ...]
    order_by: tuple[str, ...]
    partition_by: tuple[str, ...]
    event_time: str | None


def _table_artifact_contract(
    row_model: type[BaseModel],
    *,
    row_count: int,
    dataset: _DatasetContractEvidence | None,
) -> _TableArtifactContract:
    """Return deterministic semantic and quality metadata for one table."""
    quality = [
        _ArtifactQualityCheck(check="row_contract", rows_checked=row_count),
    ]
    if dataset is not None and dataset.keys:
        quality.append(
            _ArtifactQualityCheck(
                check="candidate_key_uniqueness",
                rows_checked=row_count,
            )
        )
    if dataset is not None and dataset.order_by:
        quality.append(
            _ArtifactQualityCheck(
                check="deterministic_order",
                rows_checked=row_count,
            )
        )
    return _TableArtifactContract(
        grain=None if dataset is None else dataset.grain,
        keys=() if dataset is None else dataset.keys,
        order_by=() if dataset is None else dataset.order_by,
        partition_by=() if dataset is None else dataset.partition_by,
        event_time=None if dataset is None else dataset.event_time,
        columns=_artifact_columns(row_model),
        quality=tuple(quality),
    )


def _artifact_columns(row_model: type[BaseModel]) -> tuple[_ArtifactColumn, ...]:
    """Project ordered Pydantic fields into safe analytical column metadata."""
    columns: list[_ArtifactColumn] = []
    for name, field in row_model.model_fields.items():
        extra = field.json_schema_extra
        semantic_type: str | None = None
        unit: str | None = None
        if isinstance(extra, dict):
            raw_semantic_type = extra.get("semantic_type")
            raw_unit = extra.get("unit")
            if isinstance(raw_semantic_type, str):
                semantic_type = raw_semantic_type
            if isinstance(raw_unit, str):
                unit = raw_unit
        columns.append(
            _ArtifactColumn(
                name=name,
                nullable=_annotation_accepts_none(field.annotation),
                description=field.description,
                unit=unit,
                semantic_type=semantic_type,
            )
        )
    return tuple(columns)


def _annotation_accepts_none(annotation: object) -> bool:
    """Return whether the authoritative field annotation accepts null."""
    try:
        TypeAdapter(annotation).validate_python(None)
    except ValidationError:
        return False
    return True


__all__: tuple[str, ...] = ()
