"""Reserve the execution entry point used by callable recipes."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping

from .errors import CFBDRecipeUsageError


def _execute_direct(
    recipe: object,
    client: object,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> Awaitable[object]:
    """Reject execution until the durable coordinator milestone is installed."""
    del recipe, client, args, kwargs
    raise CFBDRecipeUsageError("Recipe execution is not available yet")
