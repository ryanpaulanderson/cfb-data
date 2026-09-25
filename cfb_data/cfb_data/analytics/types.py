"""Define the small public protocols consumed by recipe authors."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from cfb_data._operation import _EndpointOperation

RowT = TypeVar("RowT")
OutputT_co = TypeVar("OutputT_co", covariant=True)
ValueT_co = TypeVar("ValueT_co", covariant=True)


@runtime_checkable
class _CoverageAwareRow(Protocol):
    """Expose durable row coverage for recipe result evidence."""

    coverage_state: Literal["complete", "partial"]
    coverage_warning: str | None


class SourceContext[RowT](Protocol):
    """Retrieve one validated endpoint-backed source in the coordinator."""

    async def retrieve(self, **parameters: object) -> list[RowT]:
        """Return validated source rows for the compiled request."""
        ...


class AdaptiveSourceContext(Protocol):
    """Retrieve declared endpoint operations within a hard run attempt budget."""

    async def retrieve[RequestT: BaseModel, RowT: BaseModel](
        self,
        operation: _EndpointOperation[RequestT, RowT],
        **parameters: object,
    ) -> list[RowT]:
        """Return validated rows from one declared endpoint operation.

        :param operation: Allowlisted typed endpoint descriptor.
        :param parameters: Validated snake-case request parameters.
        :return: Source-shaped rows from the shared retrieval coordinator.
        :raises CFBDRecipeUsageError: If the operation was not declared.
        """
        ...


if TYPE_CHECKING:
    type RecipeRef[OutputT] = OutputT
    type ValueRef[ValueT] = ValueT
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


__all__ = [
    "AdaptiveSourceContext",
    "RecipeRef",
    "SourceContext",
    "ValueRef",
    "WorkflowOutputs",
]
