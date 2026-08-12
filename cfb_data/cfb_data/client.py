"""Provide the primary context-managed CollegeFootballData client."""

from __future__ import annotations

from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Generic,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
    cast,
    overload,
)

import pandas as pd

from cfb_data._dataframes import _DataFrameAdapter, _PandasAdapter, _PolarsAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._transport import (
    _HTTPTransport,
    _resolve_api_key,
    _validate_base_url,
    _validate_timeout,
)
from cfb_data.conferences.resource import ConferencesResource
from cfb_data.drives.resource import DrivesResource
from cfb_data.errors import CFBDConfigurationError
from cfb_data.games.resource import GamesResource
from cfb_data.plays.resource import PlaysResource
from cfb_data.retry import RetryPolicy
from cfb_data.teams.resource import TeamsResource
from cfb_data.venues.resource import VenuesResource

if TYPE_CHECKING:
    import polars as pl

DataFrameBackend: TypeAlias = Literal["pandas", "polars"]
_FrameT = TypeVar("_FrameT")


class CFBDClient(Generic[_FrameT]):
    """Access validated CFBD endpoint namespaces through one pooled session.

    The client is one-shot and must be used with ``async with``. Endpoint calls
    return eager pandas DataFrames by default or eager Polars DataFrames when
    ``dataframe_backend="polars"`` is selected.
    """

    @overload
    def __init__(
        self: CFBDClient[pd.DataFrame],
        api_key: str | None = None,
        *,
        dataframe_backend: Literal["pandas"] = "pandas",
        base_url: str = "https://api.collegefootballdata.com",
        timeout_seconds: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: CFBDClient[pl.DataFrame],
        api_key: str | None = None,
        *,
        dataframe_backend: Literal["polars"],
        base_url: str = "https://api.collegefootballdata.com",
        timeout_seconds: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: CFBDClient[pd.DataFrame | pl.DataFrame],
        api_key: str | None = None,
        *,
        dataframe_backend: DataFrameBackend,
        base_url: str = "https://api.collegefootballdata.com",
        timeout_seconds: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None: ...

    def __init__(
        self,
        api_key: str | None = None,
        *,
        dataframe_backend: DataFrameBackend = "pandas",
        base_url: str = "https://api.collegefootballdata.com",
        timeout_seconds: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Initialize a one-shot client without opening its HTTP session.

        :param api_key: Explicit API key, or ``None`` to use ``CFBD_API_KEY``.
        :param dataframe_backend: Eager DataFrame implementation to return.
        :param base_url: API origin and optional base path.
        :param timeout_seconds: Finite total timeout for each HTTP attempt.
        :param retry_policy: Custom retry behavior, or defaults when omitted.
        :raises CFBDConfigurationError: If client configuration is invalid.
        """
        if dataframe_backend not in {"pandas", "polars"}:
            raise CFBDConfigurationError(
                "dataframe_backend must be either 'pandas' or 'polars'"
            )

        transport = _HTTPTransport(
            api_key=_resolve_api_key(api_key),
            base_url=_validate_base_url(base_url),
            timeout_seconds=_validate_timeout(timeout_seconds),
            retry_policy=retry_policy or RetryPolicy(),
        )
        executor = _EndpointExecutor(transport)
        concrete_adapter = (
            _PandasAdapter() if dataframe_backend == "pandas" else _PolarsAdapter()
        )
        # The constructor overload ties this runtime literal branch to _FrameT.
        adapter = cast(_DataFrameAdapter[_FrameT], concrete_adapter)

        self._transport = transport
        self._games = GamesResource(executor, adapter)
        self._drives = DrivesResource(executor, adapter)
        self._plays = PlaysResource(executor, adapter)
        self._venues = VenuesResource(executor, adapter)
        self._conferences = ConferencesResource(executor, adapter)
        self._teams = TeamsResource(executor, adapter)

    @property
    def games(self) -> GamesResource[_FrameT]:
        """Return the typed Games endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._games

    @property
    def drives(self) -> DrivesResource[_FrameT]:
        """Return the typed Drives endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._drives

    @property
    def plays(self) -> PlaysResource[_FrameT]:
        """Return the typed Plays endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._plays

    @property
    def venues(self) -> VenuesResource[_FrameT]:
        """Return the typed Venues endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._venues

    @property
    def conferences(self) -> ConferencesResource[_FrameT]:
        """Return the typed Conferences endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._conferences

    @property
    def teams(self) -> TeamsResource[_FrameT]:
        """Return the typed Teams endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._teams

    async def __aenter__(self) -> Self:
        await self._transport.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._transport.close()


__all__ = ["CFBDClient", "DataFrameBackend"]
