"""Provide reusable backend-neutral recipe operations."""

from __future__ import annotations

from typing import cast

from ._graph import _NodeRef, _ValueRef
from ._recipes import step
from .errors import CFBDRecipeCompilationError
from .types import RecipeRef, ValueRef


@step(id="cfb_data.operations.require_one", revision=1, deterministic=True, dask=True)
def require_one[RowT](rows: list[RowT]) -> RowT:
    """Return the only row after enforcing exact cardinality.

    :param rows: Validated source or dataset rows.
    :return: The sole row.
    :raises ValueError: If the input does not contain exactly one row.
    """
    if len(rows) != 1:
        raise ValueError("require_one expected exactly one row")
    return rows[0]


def value[ValueT](
    source: RecipeRef[object],
    *,
    path: tuple[str | int, ...],
    expected_type: type[ValueT],
) -> ValueRef[ValueT]:
    """Bind a validated scalar path from an upstream recipe output.

    :param source: Engine-created reference to an already declared node.
    :param path: Non-empty structured field/index token path.
    :param expected_type: Exact scalar type required after extraction.
    :return: Engine-owned typed scalar reference.
    :raises CFBDRecipeCompilationError: If the reference or path is invalid.
    """
    if not isinstance(source, _NodeRef):
        raise CFBDRecipeCompilationError(
            "value() accepts only engine-created recipe references"
        )
    if (
        not path
        or len(path) > 32
        or any(
            not isinstance(token, (str, int)) or isinstance(token, bool)
            for token in path
        )
    ):
        raise CFBDRecipeCompilationError(
            "value() paths require between one and 32 string/integer tokens"
        )
    if expected_type not in {str, int, float, bool}:
        raise CFBDRecipeCompilationError(
            "value() expected_type must be a supported scalar type"
        )
    return cast(
        ValueRef[ValueT],
        _ValueRef(
            node_id=source.node_id,
            path=path,
            expected_type=cast(type[object], expected_type),
        ),
    )


__all__ = ["require_one", "value"]
