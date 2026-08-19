"""Expose typed Adjusted Metrics endpoints through the primary client."""

from __future__ import annotations

from typing import overload

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.adjusted_metrics._operations import (
    KICKER_PAAR_METRICS,
    PLAYER_PASSING_METRICS,
    PLAYER_RUSHING_METRICS,
    TEAM_SEASON_METRICS,
)
from cfb_data.adjusted_metrics.models.pydantic.requests import (
    AdjustedPlayerPassingRequest,
    AdjustedPlayerRushingRequest,
    AdjustedTeamMetricsRequest,
    KickerPAARRequest,
)


class AdjustedMetricsResource[FrameT]:
    """Provide validated opponent-adjusted metrics as selected frames."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def team_season(self, request: AdjustedTeamMetricsRequest, /) -> FrameT: ...

    @overload
    async def team_season(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def team_season(
        self, request: AdjustedTeamMetricsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return opponent-adjusted team metrics by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated adjusted-team rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_SEASON_METRICS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_passing(
        self, request: AdjustedPlayerPassingRequest, /
    ) -> FrameT: ...

    @overload
    async def player_passing(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
        position: str | None = None,
    ) -> FrameT: ...

    async def player_passing(
        self,
        request: AdjustedPlayerPassingRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return opponent-adjusted player passing EPA.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player WEPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_PASSING_METRICS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_rushing(
        self, request: AdjustedPlayerRushingRequest, /
    ) -> FrameT: ...

    @overload
    async def player_rushing(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
        position: str | None = None,
    ) -> FrameT: ...

    async def player_rushing(
        self,
        request: AdjustedPlayerRushingRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return opponent-adjusted player rushing EPA.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player WEPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_RUSHING_METRICS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def kicker_paar(self, request: KickerPAARRequest, /) -> FrameT: ...

    @overload
    async def kicker_paar(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def kicker_paar(
        self, request: KickerPAARRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return Points Added Above Replacement ratings for kickers.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated kicker PAAR rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await KICKER_PAAR_METRICS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )


__all__ = ["AdjustedMetricsResource"]
