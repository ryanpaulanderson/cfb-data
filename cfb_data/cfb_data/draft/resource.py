"""Expose typed Draft endpoints through the primary client."""

from __future__ import annotations

from typing import Generic, TypeVar, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.draft.models.pydantic.requests import DraftPicksRequest
from cfb_data.draft.models.pydantic.responses import (
    DraftPick,
    DraftPosition,
    DraftTeam,
)

_FrameT = TypeVar("_FrameT")
_RowT = TypeVar("_RowT", bound=BaseModel)

_DRAFT_TEAM_ROWS = TypeAdapter(list[DraftTeam])
_DRAFT_POSITION_ROWS = TypeAdapter(list[DraftPosition])
_DRAFT_PICK_ROWS = TypeAdapter(list[DraftPick])


class _EmptyRequest(BaseModel):
    """Represent an endpoint that accepts no filters."""

    model_config = ConfigDict(extra="forbid")


_EMPTY_REQUEST = _EmptyRequest()


class DraftResource(Generic[_FrameT]):
    """Provide validated Draft endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    async def teams(self) -> _FrameT:
        """Return NFL teams represented in historical draft data.

        :return: Eager frame containing validated NFL team rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        return await self._fetch_without_filters(
            endpoint="/draft/teams",
            response_adapter=_DRAFT_TEAM_ROWS,
            row_model=DraftTeam,
        )

    async def positions(self) -> _FrameT:
        """Return position categories used in NFL Draft data.

        :return: Eager frame containing validated position rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        return await self._fetch_without_filters(
            endpoint="/draft/positions",
            response_adapter=_DRAFT_POSITION_ROWS,
            row_model=DraftPosition,
        )

    @overload
    async def picks(self, request: DraftPicksRequest, /) -> _FrameT: ...

    @overload
    async def picks(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        school: str | None = None,
        conference: str | None = None,
        position: str | None = None,
    ) -> _FrameT: ...

    async def picks(
        self, request: DraftPicksRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return historical NFL Draft picks.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated draft-pick rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/draft/picks"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=DraftPicksRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_DRAFT_PICK_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=DraftPick, models=rows
        )

    async def _fetch_without_filters(
        self,
        *,
        endpoint: str,
        response_adapter: TypeAdapter[list[_RowT]],
        row_model: type[_RowT],
    ) -> _FrameT:
        """Fetch and tabularize one filterless Draft endpoint."""
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=_EMPTY_REQUEST,
            response_adapter=response_adapter,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=row_model, models=rows
        )


__all__ = ["DraftResource"]
