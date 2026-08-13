"""Provide the primary context-managed CollegeFootballData client."""

from __future__ import annotations

from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Literal,
    Self,
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
from cfb_data.adjusted_metrics.resource import AdjustedMetricsResource
from cfb_data.betting.resource import BettingResource
from cfb_data.coaches.resource import CoachesResource
from cfb_data.conferences.resource import ConferencesResource
from cfb_data.draft.resource import DraftResource
from cfb_data.drives.resource import DrivesResource
from cfb_data.errors import CFBDConfigurationError
from cfb_data.games.resource import GamesResource
from cfb_data.info.resource import InfoResource
from cfb_data.metrics.resource import MetricsResource
from cfb_data.players.resource import PlayersResource
from cfb_data.playoffs.resource import PlayoffsResource
from cfb_data.plays.resource import PlaysResource
from cfb_data.rankings.resource import RankingsResource
from cfb_data.ratings.resource import RatingsResource
from cfb_data.recruiting.resource import RecruitingResource
from cfb_data.retry import RetryPolicy
from cfb_data.stats.resource import StatsResource
from cfb_data.teams.resource import TeamsResource
from cfb_data.venues.resource import VenuesResource

if TYPE_CHECKING:
    import polars as pl

type DataFrameBackend = Literal["pandas", "polars"]


class CFBDClient[FrameT]:
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
        # The constructor overload ties this runtime literal branch to FrameT.
        adapter = cast(_DataFrameAdapter[FrameT], concrete_adapter)

        self._transport = transport
        self._games = GamesResource(executor, adapter)
        self._drives = DrivesResource(executor, adapter)
        self._plays = PlaysResource(executor, adapter)
        self._venues = VenuesResource(executor, adapter)
        self._conferences = ConferencesResource(executor, adapter)
        self._teams = TeamsResource(executor, adapter)
        self._stats = StatsResource(executor, adapter)
        self._metrics = MetricsResource(executor, adapter)
        self._ratings = RatingsResource(executor, adapter)
        self._players = PlayersResource(executor, adapter)
        self._rankings = RankingsResource(executor, adapter)
        self._betting = BettingResource(executor, adapter)
        self._recruiting = RecruitingResource(executor, adapter)
        self._coaches = CoachesResource(executor, adapter)
        self._draft = DraftResource(executor, adapter)
        self._playoffs = PlayoffsResource(executor, adapter)
        self._adjusted_metrics = AdjustedMetricsResource(executor, adapter)
        self._info = InfoResource(executor)

    @property
    def games(self) -> GamesResource[FrameT]:
        """Return the typed Games endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._games

    @property
    def drives(self) -> DrivesResource[FrameT]:
        """Return the typed Drives endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._drives

    @property
    def plays(self) -> PlaysResource[FrameT]:
        """Return the typed Plays endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._plays

    @property
    def venues(self) -> VenuesResource[FrameT]:
        """Return the typed Venues endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._venues

    @property
    def conferences(self) -> ConferencesResource[FrameT]:
        """Return the typed Conferences endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._conferences

    @property
    def teams(self) -> TeamsResource[FrameT]:
        """Return the typed Teams endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._teams

    @property
    def stats(self) -> StatsResource[FrameT]:
        """Return the typed Stats endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._stats

    @property
    def metrics(self) -> MetricsResource[FrameT]:
        """Return the typed Metrics endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._metrics

    @property
    def ratings(self) -> RatingsResource[FrameT]:
        """Return the typed Ratings endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._ratings

    @property
    def players(self) -> PlayersResource[FrameT]:
        """Return the typed Players endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._players

    @property
    def rankings(self) -> RankingsResource[FrameT]:
        """Return the typed Rankings endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._rankings

    @property
    def betting(self) -> BettingResource[FrameT]:
        """Return the typed Betting endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._betting

    @property
    def recruiting(self) -> RecruitingResource[FrameT]:
        """Return the typed Recruiting endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._recruiting

    @property
    def coaches(self) -> CoachesResource[FrameT]:
        """Return the typed Coaches endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._coaches

    @property
    def draft(self) -> DraftResource[FrameT]:
        """Return the typed Draft endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._draft

    @property
    def playoffs(self) -> PlayoffsResource[FrameT]:
        """Return the typed Playoffs endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._playoffs

    @property
    def adjusted_metrics(self) -> AdjustedMetricsResource[FrameT]:
        """Return the typed Adjusted Metrics endpoint namespace.

        :return: Resource bound to this client's session and DataFrame backend.
        """
        return self._adjusted_metrics

    @property
    def info(self) -> InfoResource:
        """Return the typed operational Info endpoint namespace.

        :return: Resource bound to this client's session.
        """
        return self._info

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
