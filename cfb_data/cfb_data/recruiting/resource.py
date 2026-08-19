"""Expose typed Recruiting endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypeVar, cast, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import RecruitClassification
from cfb_data.recruiting.models.pydantic.requests import (
    RecruitingGroupsRequest,
    RecruitingPlayersRequest,
    RecruitingTeamsRequest,
)
from cfb_data.recruiting.models.pydantic.responses import (
    AggregatedTeamRecruiting,
    Recruit,
    TeamRecruitingRanking,
)

if TYPE_CHECKING:
    from cfb_data.analytics._sources import EndpointOperation

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
type _RecruitClassificationArgument = (
    RecruitClassification | Literal["JUCO", "PrepSchool", "HighSchool"]
)

_GROUP_ROWS = TypeAdapter(list[AggregatedTeamRecruiting])


class RecruitingResource[FrameT]:
    """Provide validated Recruiting endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def players(self, request: RecruitingPlayersRequest, /) -> FrameT: ...

    @overload
    async def players(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        position: str | None = None,
        state: str | None = None,
        classification: _RecruitClassificationArgument | None = None,
    ) -> FrameT: ...

    async def players(
        self, request: RecruitingPlayersRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return ranked recruiting prospects.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated recruit rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        source = _recruits_source()
        return await self._fetch_many(
            endpoint=source.endpoint,
            request_type=source.request_model,
            request=request,
            filters=filters,
            response_adapter=source.response_adapter,
            row_model=source.output.row_model,
        )

    @overload
    async def teams(self, request: RecruitingTeamsRequest, /) -> FrameT: ...

    @overload
    async def teams(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
    ) -> FrameT: ...

    async def teams(
        self, request: RecruitingTeamsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team recruiting class rankings.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team ranking rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        source = _team_rankings_source()
        return await self._fetch_many(
            endpoint=source.endpoint,
            request_type=source.request_model,
            request=request,
            filters=filters,
            response_adapter=source.response_adapter,
            row_model=source.output.row_model,
        )

    @overload
    async def groups(self, request: RecruitingGroupsRequest, /) -> FrameT: ...

    @overload
    async def groups(
        self,
        request: None = None,
        /,
        *,
        team: str | None = None,
        conference: str | None = None,
        recruit_type: _RecruitClassificationArgument | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> FrameT: ...

    async def groups(
        self, request: RecruitingGroupsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return recruiting ratings aggregated by team and position group.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated recruiting aggregates.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/recruiting/groups",
            request_type=RecruitingGroupsRequest,
            request=request,
            filters=filters,
            response_adapter=_GROUP_ROWS,
            row_model=AggregatedTeamRecruiting,
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


def _recruits_source() -> EndpointOperation[RecruitingPlayersRequest, Recruit]:
    from cfb_data.analytics._sources import EndpointOperation, endpoint_operation

    return cast(
        EndpointOperation[RecruitingPlayersRequest, Recruit],
        endpoint_operation("cfbd.recruiting.players"),
    )


def _team_rankings_source() -> EndpointOperation[
    RecruitingTeamsRequest, TeamRecruitingRanking
]:
    from cfb_data.analytics._sources import EndpointOperation, endpoint_operation

    return cast(
        EndpointOperation[RecruitingTeamsRequest, TeamRecruitingRanking],
        endpoint_operation("cfbd.recruiting.team_rankings"),
    )


__all__ = ["RecruitingResource"]
