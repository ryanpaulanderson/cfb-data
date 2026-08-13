"""Expose typed Recruiting endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, Literal, TypeAlias, TypeVar, overload

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

_FrameT = TypeVar("_FrameT")
_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
_RecruitClassificationArgument: TypeAlias = (
    RecruitClassification | Literal["JUCO", "PrepSchool", "HighSchool"]
)

_RECRUIT_ROWS = TypeAdapter(list[Recruit])
_TEAM_RANKING_ROWS = TypeAdapter(list[TeamRecruitingRanking])
_GROUP_ROWS = TypeAdapter(list[AggregatedTeamRecruiting])


class RecruitingResource(Generic[_FrameT]):
    """Provide validated Recruiting endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def players(self, request: RecruitingPlayersRequest, /) -> _FrameT: ...

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
    ) -> _FrameT: ...

    async def players(
        self, request: RecruitingPlayersRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return ranked recruiting prospects.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated recruit rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/recruiting/players",
            request_type=RecruitingPlayersRequest,
            request=request,
            filters=filters,
            response_adapter=_RECRUIT_ROWS,
            row_model=Recruit,
        )

    @overload
    async def teams(self, request: RecruitingTeamsRequest, /) -> _FrameT: ...

    @overload
    async def teams(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
    ) -> _FrameT: ...

    async def teams(
        self, request: RecruitingTeamsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return team recruiting class rankings.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team ranking rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/recruiting/teams",
            request_type=RecruitingTeamsRequest,
            request=request,
            filters=filters,
            response_adapter=_TEAM_RANKING_ROWS,
            row_model=TeamRecruitingRanking,
        )

    @overload
    async def groups(self, request: RecruitingGroupsRequest, /) -> _FrameT: ...

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
    ) -> _FrameT: ...

    async def groups(
        self, request: RecruitingGroupsRequest | None = None, /, **filters: object
    ) -> _FrameT:
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
    ) -> _FrameT:
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


__all__ = ["RecruitingResource"]
