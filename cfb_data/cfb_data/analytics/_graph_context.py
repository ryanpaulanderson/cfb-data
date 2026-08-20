"""Provide the context hook used by callable recipe wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, cast

from .errors import CFBDRecipeUsageError
from .types import RecipeRef

R = TypeVar("R")


def _active_build_context() -> object | None:
    """Return the task-local graph builder."""
    from ._compiler import _current_builder

    return _current_builder()


def _call_in_build_context(
    recipe: object, args: tuple[object, ...], kwargs: Mapping[str, object]
) -> RecipeRef[R]:
    """Add an ordinary recipe call to the task-local graph builder."""
    from ._compiler import _CompilableRecipe, _current_builder

    builder = _current_builder()
    if builder is None:
        raise CFBDRecipeUsageError(
            "Sources and steps may only be called while a dataset or workflow is built"
        )
    return cast(
        RecipeRef[R], builder.call(cast(_CompilableRecipe, recipe), args, kwargs)
    )
