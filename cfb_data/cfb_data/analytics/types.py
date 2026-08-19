"""Define the small public protocols consumed by recipe authors."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Protocol, TypeVar

RowT = TypeVar("RowT")
OutputT_co = TypeVar("OutputT_co", covariant=True)
ValueT_co = TypeVar("ValueT_co", covariant=True)


class SourceContext[RowT](Protocol):
    """Retrieve one validated endpoint-backed source in the coordinator."""

    async def retrieve(self, **parameters: object) -> list[RowT]:
        """Return validated source rows for the compiled request."""
        ...


if TYPE_CHECKING:
    type RecipeRef[OutputT] = OutputT
else:

    class RecipeRef[OutputT_co](Protocol):
        """Represent a typed recipe output while a graph is being built."""


class ValueRef[ValueT_co](Protocol):
    """Represent a validated scalar bound from an upstream recipe output."""


class WorkflowOutputs[OutputT_co](Protocol):
    """Expose immutable explicitly named workflow outputs."""

    def __getitem__(self, name: str) -> OutputT_co:
        """Return one named workflow output."""
        ...

    def __iter__(self) -> Iterator[str]:
        """Iterate output names in declared order."""
        ...

    def __len__(self) -> int:
        """Return the number of named outputs."""
        ...


__all__ = ["RecipeRef", "SourceContext", "ValueRef", "WorkflowOutputs"]
