"""Execute pure transform steps through a managed Dask provider session."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from importlib import import_module
from typing import Literal, Protocol, Self, cast

from cfb_data._observability import _failure_category
from cfb_data.errors import CFBDOptionalDependencyError

from ._dask_transport import (
    _decode_output,
    _encode_parameters,
    _execute_transform_worker,
    _output_model,
    _recipe_identity,
    _validate_capabilities,
    _validate_diagnostics,
    _worker_capabilities,
    _WorkerResult,
)
from ._recipes import StepRecipe
from .errors import CFBDExecutorError


class _DaskTransformProvider:
    """Own one lazily started managed Dask executor session."""

    def __init__(
        self,
        *,
        max_workers: int,
        threads_per_worker: int,
        transfer_limit_bytes: int,
    ) -> None:
        """Initialize bounded settings without importing or starting Dask."""
        values = (max_workers, threads_per_worker, transfer_limit_bytes)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in values
        ):
            raise ValueError("Dask provider limits must be positive integers")
        self._max_workers = max_workers
        self._threads_per_worker = threads_per_worker
        self._transfer_limit_bytes = transfer_limit_bytes
        self._cluster: _DaskCluster | None = None
        self._client: _DaskClient | None = None
        self._futures: set[_DaskFuture] = set()
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False

    @property
    def placement(self) -> Literal["dask"]:
        """Return the Dask placement label."""
        return "dask"

    @property
    def started(self) -> bool:
        """Return whether this session started its managed provider resources."""
        return self._client is not None

    async def __aenter__(self) -> Self:
        """Enter without starting Dask before eligible work exists."""
        if self._closed:
            raise CFBDExecutorError(provider="dask", category="closed")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Cancel outstanding work and close all managed resources."""
        await self.aclose()

    async def execute(
        self,
        recipe: StepRecipe[..., object],
        parameters: Mapping[str, object],
    ) -> object:
        """Execute one synchronous Dask-eligible step through Arrow transport."""
        if self._closed:
            raise CFBDExecutorError(provider="dask", category="closed")
        if recipe._is_async or not recipe._declaration.dask_eligible:
            raise CFBDExecutorError(provider="dask", category="ineligible")
        output_model = _output_model(recipe)
        output_identity = _recipe_identity(recipe, label="output")
        encoded, input_bytes = await asyncio.to_thread(
            _encode_parameters,
            recipe,
            parameters,
        )
        self._require_transfer(input_bytes)
        await self._ensure_started()
        client = self._client
        if client is None:
            raise CFBDExecutorError(provider="dask", category="client_state")
        function = recipe._function
        future = client.submit(
            _execute_transform_worker,
            function,
            dict(encoded),
            output_model,
            output_identity,
            self._transfer_limit_bytes,
            key=None,
            pure=False,
            retries=0,
        )
        self._futures.add(future)
        try:
            payload, diagnostics = await future
        except asyncio.CancelledError:
            await _cancel_futures(client, (future,))
            await asyncio.gather(future, return_exceptions=True)
            raise
        except Exception as exc:
            raise CFBDExecutorError(
                provider="dask",
                category=_failure_category(exc),
            ) from exc
        finally:
            self._futures.discard(future)
        self._require_transfer(len(payload))
        _validate_diagnostics(diagnostics)
        return await asyncio.to_thread(
            _decode_output,
            payload,
            output_model,
            output_identity,
        )

    async def aclose(self) -> None:
        """Cancel and await futures, then close the client and cluster."""
        async with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            client_object = self._client
            cluster_object = self._cluster
            self._client = None
            self._cluster = None
            futures = tuple(self._futures)
            self._futures.clear()
        failures: list[BaseException] = []
        if client_object is not None and futures:
            try:
                await _cancel_futures(client_object, futures)
            except BaseException as exc:
                failures.append(exc)
            try:
                await asyncio.gather(*futures, return_exceptions=True)
            except BaseException as exc:
                failures.append(exc)
        failures.extend(await _close_dask_resources(client_object, cluster_object))
        if failures:
            failure = failures[0]
            if isinstance(failure, asyncio.CancelledError):
                raise failure
            raise CFBDExecutorError(provider="dask", category="cleanup") from failure

    async def _ensure_started(self) -> None:
        async with self._lifecycle_lock:
            if self._closed:
                raise CFBDExecutorError(provider="dask", category="closed")
            if self._client is not None:
                return
            cluster_factory, client_factory = _load_dask_factories()
            workers = min(self._max_workers, 4, os.cpu_count() or 1)
            cluster: _DaskCluster | None = None
            client: _DaskClient | None = None
            try:
                cluster = await cluster_factory(
                    n_workers=workers,
                    threads_per_worker=self._threads_per_worker,
                    processes=True,
                    asynchronous=True,
                    dashboard_address=None,
                    silence_logs=logging.ERROR,
                    scheduler_kwargs={"allowed_failures": 0},
                )
                client = await client_factory(
                    cluster,
                    asynchronous=True,
                    set_as_default=False,
                )
                await client.wait_for_workers(workers)
                capabilities = await client.run(_worker_capabilities)
                _validate_capabilities(capabilities, expected_workers=workers)
            except BaseException as exc:
                await _close_dask_resources(client, cluster)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, CFBDExecutorError):
                    raise
                raise CFBDExecutorError(
                    provider="dask",
                    category="startup",
                ) from exc
            self._cluster = cluster
            self._client = client

    def _require_transfer(self, actual_bytes: int) -> None:
        if actual_bytes > self._transfer_limit_bytes:
            raise CFBDExecutorError(provider="dask", category="transfer_limit")


class _DaskFuture(Awaitable[_WorkerResult], Protocol):
    """Describe the awaitable subset used from a distributed future."""


class _DaskClient(Protocol):
    """Describe the managed asynchronous distributed client boundary."""

    def submit(
        self,
        function: Callable[..., _WorkerResult],
        *args: object,
        **kwargs: object,
    ) -> _DaskFuture: ...

    async def cancel(
        self,
        futures: tuple[_DaskFuture, ...],
        *,
        force: bool,
        reason: str,
    ) -> None: ...

    async def wait_for_workers(self, workers: int) -> None: ...

    async def run(self, function: Callable[[], bytes]) -> Mapping[str, bytes]: ...

    async def close(self) -> None: ...


class _DaskCluster(Protocol):
    """Describe the asynchronous cluster closure boundary."""

    async def close(self) -> None: ...


class _DaskClusterFactory(Protocol):
    """Construct one awaitable managed cluster through the untyped boundary."""

    def __call__(
        self,
        *,
        n_workers: int,
        threads_per_worker: int,
        processes: bool,
        asynchronous: bool,
        dashboard_address: None,
        silence_logs: int,
        scheduler_kwargs: Mapping[str, object],
    ) -> Awaitable[_DaskCluster]: ...


class _DaskClientFactory(Protocol):
    """Construct one awaitable asynchronous client through the untyped boundary."""

    def __call__(
        self,
        cluster: _DaskCluster,
        *,
        asynchronous: bool,
        set_as_default: bool,
    ) -> Awaitable[_DaskClient]: ...


def _load_dask_factories() -> tuple[_DaskClusterFactory, _DaskClientFactory]:
    """Load and narrow the optional untyped Dask constructor boundary."""
    try:
        module = import_module("distributed")
    except ModuleNotFoundError as exc:
        if exc.name in {"dask", "distributed"}:
            raise CFBDOptionalDependencyError(
                'Dask execution requires pip install "cfb-data[dask]"'
            ) from exc
        raise
    cluster_factory = getattr(module, "LocalCluster", None)
    client_factory = getattr(module, "Client", None)
    if not callable(cluster_factory) or not callable(client_factory):
        raise CFBDExecutorError(provider="dask", category="dependency_contract")
    # distributed does not ship typing metadata. Keep that untyped boundary
    # isolated here and validate capabilities before any transform is admitted.
    return cast(_DaskClusterFactory, cluster_factory), cast(
        _DaskClientFactory,
        client_factory,
    )


async def _cancel_futures(
    client: _DaskClient,
    futures: tuple[_DaskFuture, ...],
) -> None:
    await client.cancel(futures, force=True, reason="cfb-data analytics cancellation")


async def _close_dask_resources(
    client: _DaskClient | None,
    cluster: _DaskCluster | None,
) -> list[BaseException]:
    """Attempt every owned close and return failures without short-circuiting."""
    failures: list[BaseException] = []
    if client is not None:
        try:
            await client.close()
        except BaseException as exc:
            failures.append(exc)
    if cluster is not None:
        try:
            await cluster.close()
        except BaseException as exc:
            failures.append(exc)
    return failures


__all__: tuple[str, ...] = ()
