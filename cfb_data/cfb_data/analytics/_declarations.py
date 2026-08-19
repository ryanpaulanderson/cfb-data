"""Own immutable declarations produced by public recipe decorators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

type RecipeKind = Literal["source", "step", "dataset", "workflow"]


@dataclass(frozen=True, slots=True)
class _RecipeDeclaration:
    """Describe one decorated boundary without exposing graph internals."""

    kind: RecipeKind
    recipe_id: str | None
    revision: int | None
    output_type: type[object] | None
    deterministic: bool
    supported_backends: frozenset[str]
    dask_eligible: bool
    grain: str | None = None
    keys: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    partition_by: tuple[str, ...] = ()
    event_time: str | None = None
    operation: object | None = None
    source_cost: int | None = None

    @property
    def durable(self) -> bool:
        """Return whether the boundary has stable cross-run identity."""
        return self.recipe_id is not None and self.revision is not None


def _validate_row_type(row: type[BaseModel]) -> type[object]:
    """Narrow a dataset row model to the declaration's runtime type."""
    return row
