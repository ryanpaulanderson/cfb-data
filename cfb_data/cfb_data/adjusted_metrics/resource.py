"""Expose typed Adjusted Metrics endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.adjusted_metrics.models.pydantic.requests import (
    AdjustedPlayerPassingRequest,
    AdjustedPlayerRushingRequest,
    AdjustedTeamMetricsRequest,
    KickerPAARRequest,
)
from cfb_data.adjusted_metrics.models.pydantic.responses import (
    AdjustedTeamMetrics,
    KickerPAAR,
    PlayerWeightedEPA,
)

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)

_ADJUSTED_TEAM_ROWS = TypeAdapter(list[AdjustedTeamMetrics])
_PLAYER_WEIGHTED_EPA_ROWS = TypeAdapter(list[PlayerWeightedEPA])
_KICKER_PAAR_ROWS = TypeAdapter(list[KickerPAAR])


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
        return await self._fetch_many(
            endpoint="/wepa/team/season",
            request_type=AdjustedTeamMetricsRequest,
            request=request,
            filters=filters,
            response_adapter=_ADJUSTED_TEAM_ROWS,
            row_model=AdjustedTeamMetrics,
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
        return await self._fetch_many(
            endpoint="/wepa/players/passing",
            request_type=AdjustedPlayerPassingRequest,
            request=request,
            filters=filters,
            response_adapter=_PLAYER_WEIGHTED_EPA_ROWS,
            row_model=PlayerWeightedEPA,
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
        return await self._fetch_many(
            endpoint="/wepa/players/rushing",
            request_type=AdjustedPlayerRushingRequest,
            request=request,
            filters=filters,
            response_adapter=_PLAYER_WEIGHTED_EPA_ROWS,
            row_model=PlayerWeightedEPA,
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
        return await self._fetch_many(
            endpoint="/wepa/players/kicking",
            request_type=KickerPAARRequest,
            request=request,
            filters=filters,
            response_adapter=_KICKER_PAAR_ROWS,
            row_model=KickerPAAR,
        )

    async def _fetch_many(
        self,
        *,
        endpoint: str,
        request_type: type[_RequestT],
        request: _RequestT | None,
        filters: Mapping[str, object],
        response_adapter: TypeAdapter[list[_RowT]],
        row_model: type[_RowT],
    ) -> FrameT:
        """Resolve, validate, fetch, and tabularize one list endpoint."""
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=request_type,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=response_adapter,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=row_model, models=rows
        )


__all__ = ["AdjustedMetricsResource"]
