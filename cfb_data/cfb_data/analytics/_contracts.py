"""Classify executable output contracts without coupling them to placement."""

from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from pydantic import BaseModel

from ._graph import _CompiledNode
from ._recipes import StepRecipe
from .errors import CFBDRecipeCompilationError


def _table_row_model(
    node: _CompiledNode,
    *,
    required: bool,
) -> type[BaseModel] | None:
    """Return the declared table row model for a dataset or table step.

    A step is tabular only when its return contract is ``list[Model]`` and its
    decorator names that same model. Other step outputs are modeled JSON
    controls and remain eligible for coordinator-local execution.
    """
    output_type = node.declaration.output_type
    if node.kind == "dataset":
        return _require_model(output_type)
    if node.kind != "step":
        if required:
            raise CFBDRecipeCompilationError(
                "Only steps and datasets have transform output contracts"
            )
        return None
    recipe = node.recipe
    if not isinstance(recipe, StepRecipe):
        raise CFBDRecipeCompilationError("Compiled step has an invalid recipe")
    return_type = get_type_hints(recipe._function, include_extras=True)["return"]
    arguments = get_args(return_type)
    if get_origin(return_type) is list and len(arguments) == 1:
        row_type = arguments[0]
        declared = _require_model(output_type)
        if row_type is not declared:
            raise CFBDRecipeCompilationError(
                "Table step return annotation and declared row model differ"
            )
        return _require_model(output_type)
    if required:
        raise CFBDRecipeCompilationError(
            "This transform boundary does not produce a table"
        )
    return None


def _require_model(output_type: type[object] | None) -> type[BaseModel]:
    if not isinstance(output_type, type) or not issubclass(output_type, BaseModel):
        raise CFBDRecipeCompilationError(
            "Table steps and datasets require a declared Pydantic row model"
        )
    return output_type


__all__: tuple[str, ...] = ()
