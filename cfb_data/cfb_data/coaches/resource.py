"""Expose typed Coaches endpoints through the primary client."""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from typing import Generic, TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.coaches.models.pydantic.requests import (
    CoachesRequest,
    CoachProfileRequest,
    CoachSeasonsRequest,
    CoachTenuresRequest,
)
from cfb_data.coaches.models.pydantic.responses import (
    Coach,
    CoachProfile,
    CoachTenure,
    DetailedCoachSeason,
)

_FrameT = TypeVar("_FrameT")
_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)

_COACH_ROWS = TypeAdapter(list[Coach])
_COACH_PROFILE = TypeAdapter(CoachProfile)
_COACH_SEASON_ROWS = TypeAdapter(list[DetailedCoachSeason])
_COACH_TENURE_ROWS = TypeAdapter(list[CoachTenure])


class CoachesResource(Generic[_FrameT]):
    """Provide validated Coaches endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: CoachesRequest, /) -> _FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        team: str | None = None,
        year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
    ) -> _FrameT: ...

    async def list(
        self, request: CoachesRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return historical head coaches with nested season summaries.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated coach rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/coaches",
            request_type=CoachesRequest,
            request=request,
            filters=filters,
            response_adapter=_COACH_ROWS,
            row_model=Coach,
        )

    @overload
    async def profile(self, request: CoachProfileRequest, /) -> _FrameT: ...

    @overload
    async def profile(self, request: None = None, /, *, coach_id: int) -> _FrameT: ...

    async def profile(
        self, request: CoachProfileRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return one canonical coach profile as a one-row frame.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: One-row eager frame containing the validated coach profile.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/coaches/profile"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=CoachProfileRequest,
            request=request,
            filters=filters,
        )
        profile = await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_COACH_PROFILE,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=CoachProfile, models=[profile]
        )

    @overload
    async def seasons(self, request: CoachSeasonsRequest, /) -> _FrameT: ...

    @overload
    async def seasons(
        self,
        request: None = None,
        /,
        *,
        coach_id: int | None = None,
        team: str | None = None,
        year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
    ) -> _FrameT: ...

    async def seasons(
        self, request: CoachSeasonsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return coach-season records with attributed results and context.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated detailed coach seasons.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/coaches/seasons",
            request_type=CoachSeasonsRequest,
            request=request,
            filters=filters,
            response_adapter=_COACH_SEASON_ROWS,
            row_model=DetailedCoachSeason,
        )

    @overload
    async def tenures(self, request: CoachTenuresRequest, /) -> _FrameT: ...

    @overload
    async def tenures(
        self,
        request: None = None,
        /,
        *,
        coach_id: int | None = None,
        team: str | None = None,
        year: int | None = None,
        active: bool | None = None,
    ) -> _FrameT: ...

    async def tenures(
        self, request: CoachTenuresRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return continuous head-coaching tenures and attributed records.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated coaching tenure rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/coaches/tenures",
            request_type=CoachTenuresRequest,
            request=request,
            filters=filters,
            response_adapter=_COACH_TENURE_ROWS,
            row_model=CoachTenure,
        )

    async def _fetch_many(
        self,
        *,
        endpoint: str,
        request_type: type[_RequestT],
        request: _RequestT | None,
        filters: Mapping[str, object],
        response_adapter: TypeAdapter[builtins.list[_RowT]],
        row_model: type[_RowT],
    ) -> _FrameT:
        """Resolve, validate, fetch, and tabularize one list endpoint."""
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=request_type,
            request=request,
            filters=filters,
        )
        rows: builtins.list[_RowT] = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=response_adapter,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=row_model, models=rows
        )


__all__ = ["CoachesResource"]
