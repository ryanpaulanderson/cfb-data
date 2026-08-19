"""Expose typed Players endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.players._operations import PLAYER_USAGE, RETURNING_PRODUCTION
from cfb_data.players.models.pydantic.requests import (
    PlayerSearchRequest,
    PlayerSeasonOverviewRequest,
    PlayerUsageRequest,
    ReturningProductionRequest,
    TransferPortalRequest,
)
from cfb_data.players.models.pydantic.responses import (
    PlayerSearchResult,
    PlayerSeasonOverview,
    PlayerTransfer,
)

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)

_SEARCH_ROWS = TypeAdapter(list[PlayerSearchResult])
_SEASON_OVERVIEW = TypeAdapter(PlayerSeasonOverview)
_TRANSFER_ROWS = TypeAdapter(list[PlayerTransfer])


class PlayersResource[FrameT]:
    """Provide validated Players endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def search(self, request: PlayerSearchRequest, /) -> FrameT: ...

    @overload
    async def search(
        self,
        request: None = None,
        /,
        *,
        search_term: str,
        year: int | None = None,
        team: str | None = None,
        position: str | None = None,
    ) -> FrameT: ...

    async def search(
        self, request: PlayerSearchRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return up to 100 players whose names match a search term.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player search rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/player/search",
            request_type=PlayerSearchRequest,
            request=request,
            filters=filters,
            response_adapter=_SEARCH_ROWS,
            row_model=PlayerSearchResult,
        )

    @overload
    async def usage(self, request: PlayerUsageRequest, /) -> FrameT: ...

    @overload
    async def usage(
        self,
        request: None = None,
        /,
        *,
        year: int,
        conference: str | None = None,
        position: str | None = None,
        team: str | None = None,
        player_id: int | None = None,
        exclude_garbage_time: bool | None = None,
    ) -> FrameT: ...

    async def usage(
        self, request: PlayerUsageRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player usage metrics for a season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player usage rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_USAGE.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def season_overview(
        self, request: PlayerSeasonOverviewRequest, /
    ) -> FrameT: ...

    @overload
    async def season_overview(
        self, request: None = None, /, *, year: int, player_id: int
    ) -> FrameT: ...

    async def season_overview(
        self,
        request: PlayerSeasonOverviewRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return one nested player season overview as a one-row frame.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: One-row eager frame containing the validated season overview.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/player/season/overview"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=PlayerSeasonOverviewRequest,
            request=request,
            filters=filters,
        )
        overview = await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_SEASON_OVERVIEW,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=PlayerSeasonOverview,
            models=[overview],
        )

    @overload
    async def returning_production(
        self, request: ReturningProductionRequest, /
    ) -> FrameT: ...

    @overload
    async def returning_production(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def returning_production(
        self,
        request: ReturningProductionRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return team returning-production metrics by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated returning-production rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await RETURNING_PRODUCTION.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def transfer_portal(self, request: TransferPortalRequest, /) -> FrameT: ...

    @overload
    async def transfer_portal(
        self, request: None = None, /, *, year: int
    ) -> FrameT: ...

    async def transfer_portal(
        self, request: TransferPortalRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return transfer portal entries for a season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated transfer rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/player/portal",
            request_type=TransferPortalRequest,
            request=request,
            filters=filters,
            response_adapter=_TRANSFER_ROWS,
            row_model=PlayerTransfer,
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


__all__ = ["PlayersResource"]
