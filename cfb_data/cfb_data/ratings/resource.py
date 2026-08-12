"""Expose typed Ratings endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, Literal, TypeAlias, TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import Classification, SeasonType
from cfb_data.ratings.models.pydantic.requests import (
    ConferenceSPRatingsRequest,
    CoreRatingsRequest,
    EloRatingsRequest,
    ExpandedSRSRatingsRequest,
    FPIRatingsRequest,
    SPRatingsRequest,
    SRSRatingsRequest,
)
from cfb_data.ratings.models.pydantic.responses import (
    ConferenceSP,
    ExpandedTeamSRS,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)

_FrameT = TypeVar("_FrameT")
_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
_ClassificationArgument: TypeAlias = Classification | Literal["fbs", "fcs", "ii", "iii"]
_SeasonTypeArgument: TypeAlias = (
    SeasonType
    | Literal[
        "regular",
        "postseason",
        "both",
        "allstar",
        "spring_regular",
        "spring_postseason",
    ]
)

_CORE_ROWS = TypeAdapter(list[TeamCoreRating])
_SP_ROWS = TypeAdapter(list[TeamSP])
_CONFERENCE_SP_ROWS = TypeAdapter(list[ConferenceSP])
_SRS_ROWS = TypeAdapter(list[TeamSRS])
_EXPANDED_SRS_ROWS = TypeAdapter(list[ExpandedTeamSRS])
_ELO_ROWS = TypeAdapter(list[TeamElo])
_FPI_ROWS = TypeAdapter(list[TeamFPI])


class RatingsResource(Generic[_FrameT]):
    """Provide validated Ratings endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def core(self, request: CoreRatingsRequest, /) -> _FrameT: ...

    @overload
    async def core(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> _FrameT: ...

    async def core(
        self, request: CoreRatingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return Context and Opponent-Relative Efficiency ratings.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated CORE rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/core",
            request_type=CoreRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_CORE_ROWS,
            row_model=TeamCoreRating,
        )

    @overload
    async def sp(self, request: SPRatingsRequest, /) -> _FrameT: ...

    @overload
    async def sp(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
    ) -> _FrameT: ...

    async def sp(
        self, request: SPRatingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return team SP+ ratings by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team SP+ rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/sp",
            request_type=SPRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_SP_ROWS,
            row_model=TeamSP,
        )

    @overload
    async def conference_sp(
        self, request: ConferenceSPRatingsRequest, /
    ) -> _FrameT: ...

    @overload
    async def conference_sp(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        conference: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> _FrameT: ...

    async def conference_sp(
        self,
        request: ConferenceSPRatingsRequest | None = None,
        /,
        **filters: object,
    ) -> _FrameT:
        """Return conference-level SP+ ratings by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated conference SP+ rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/sp/conferences",
            request_type=ConferenceSPRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_CONFERENCE_SP_ROWS,
            row_model=ConferenceSP,
        )

    @overload
    async def srs(self, request: SRSRatingsRequest, /) -> _FrameT: ...

    @overload
    async def srs(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> _FrameT: ...

    async def srs(
        self, request: SRSRatingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return Simple Rating System ratings by team and season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated SRS rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/srs",
            request_type=SRSRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_SRS_ROWS,
            row_model=TeamSRS,
        )

    @overload
    async def expanded_srs(self, request: ExpandedSRSRatingsRequest, /) -> _FrameT: ...

    @overload
    async def expanded_srs(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> _FrameT: ...

    async def expanded_srs(
        self,
        request: ExpandedSRSRatingsRequest | None = None,
        /,
        **filters: object,
    ) -> _FrameT:
        """Return expanded SRS ratings including lower classifications.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated expanded SRS rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/srs/expanded",
            request_type=ExpandedSRSRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_EXPANDED_SRS_ROWS,
            row_model=ExpandedTeamSRS,
        )

    @overload
    async def elo(self, request: EloRatingsRequest, /) -> _FrameT: ...

    @overload
    async def elo(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> _FrameT: ...

    async def elo(
        self, request: EloRatingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return historical Elo ratings for the selected period.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated Elo rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/elo",
            request_type=EloRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_ELO_ROWS,
            row_model=TeamElo,
        )

    @overload
    async def fpi(self, request: FPIRatingsRequest, /) -> _FrameT: ...

    @overload
    async def fpi(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> _FrameT: ...

    async def fpi(
        self, request: FPIRatingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return Football Power Index ratings by team and season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated FPI rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ratings/fpi",
            request_type=FPIRatingsRequest,
            request=request,
            filters=filters,
            response_adapter=_FPI_ROWS,
            row_model=TeamFPI,
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


__all__ = ["RatingsResource"]
