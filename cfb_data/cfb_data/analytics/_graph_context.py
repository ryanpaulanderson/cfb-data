"""Provide the context hook used by callable recipe wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from .errors import CFBDRecipeUsageError
from .types import RecipeRef

R = TypeVar("R")


def _active_build_context() -> object | None:
    """Return the active graph builder once graph compilation is available."""
    return None


def _call_in_build_context(
    recipe: object, args: tuple[object, ...], kwargs: Mapping[str, object]
) -> RecipeRef[R]:
    """Reject build-only calls until an engine-owned build context is active."""
    del recipe, args, kwargs
    raise CFBDRecipeUsageError(
        "Sources and steps may only be called while a dataset or workflow is built"
    )
