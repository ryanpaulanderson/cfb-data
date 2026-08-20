"""Define topology-neutral transform executor sessions."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Literal, Protocol, Self

from ._recipes import StepRecipe

type _TransformPlacement = Literal["local", "dask"]


class _TransformExecutorSession(Protocol):
    """Execute pure transform tasks without owning coordinator state."""

    @property
    def placement(self) -> _TransformPlacement:
        """Return the stable placement label for audit evidence."""
        ...

    async def execute(
        self,
        recipe: StepRecipe[..., object],
        parameters: Mapping[str, object],
    ) -> object:
        """Execute one trusted pure step with validated parameters."""
        ...

    async def aclose(self) -> None:
        """Cancel owned work and release executor resources deterministically."""
        ...


class _LocalTransformProvider:
    """Run synchronous trusted transforms off-loop with bounded admission."""

    def __init__(self, *, concurrency: int) -> None:
        """Initialize a coordinator-local compute session."""
        if concurrency < 1:
            raise ValueError("Local compute concurrency must be positive")
        self._semaphore = asyncio.Semaphore(concurrency)

    @property
    def placement(self) -> _TransformPlacement:
        """Return the local placement label."""
        return "local"

    async def __aenter__(self) -> Self:
        """Enter the resource-neutral local session."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Close the local session after all admitted calls finish."""
        await self.aclose()

    async def execute(
        self,
        recipe: StepRecipe[..., object],
        parameters: Mapping[str, object],
    ) -> object:
        """Execute one step while deterministically owning background work."""
        if recipe._is_async:
            result = recipe._execute_step(parameters)
            if not inspect.isawaitable(result):
                raise TypeError("Async step did not return an awaitable")
            return await result
        async with self._semaphore:
            worker = asyncio.create_task(
                asyncio.to_thread(recipe._execute_step, parameters),
                name=f"cfb-data-local-transform:{recipe.id or recipe.__qualname__}",
            )
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                await asyncio.gather(worker, return_exceptions=True)
                raise

    async def aclose(self) -> None:
        """Release the resource-neutral local session."""


__all__: tuple[str, ...] = ()
