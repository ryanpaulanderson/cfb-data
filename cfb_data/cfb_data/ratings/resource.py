"""Expose typed Ratings endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.enums import Classification, SeasonType
from cfb_data.ratings._operations import (
    CONFERENCE_SP_RATINGS,
    CORE_RATINGS,
    ELO_RATINGS,
    EXPANDED_SRS_RATINGS,
    FPI_RATINGS,
    SP_RATINGS,
    SRS_RATINGS,
)
from cfb_data.ratings.models.pydantic.requests import (
    ConferenceSPRatingsRequest,
    CoreRatingsRequest,
    EloRatingsRequest,
    ExpandedSRSRatingsRequest,
    FPIRatingsRequest,
    SPRatingsRequest,
    SRSRatingsRequest,
)

type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
type _SeasonTypeArgument = (
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


class RatingsResource[FrameT]:
    """Provide validated Ratings endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def core(self, request: CoreRatingsRequest, /) -> FrameT: ...

    @overload
    async def core(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def core(
        self, request: CoreRatingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return Context and Opponent-Relative Efficiency ratings.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated CORE rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await CORE_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def sp(self, request: SPRatingsRequest, /) -> FrameT: ...

    @overload
    async def sp(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
    ) -> FrameT: ...

    async def sp(
        self, request: SPRatingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team SP+ ratings by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team SP+ rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await SP_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def conference_sp(self, request: ConferenceSPRatingsRequest, /) -> FrameT: ...

    @overload
    async def conference_sp(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        conference: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def conference_sp(
        self,
        request: ConferenceSPRatingsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return conference-level SP+ ratings by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated conference SP+ rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await CONFERENCE_SP_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def srs(self, request: SRSRatingsRequest, /) -> FrameT: ...

    @overload
    async def srs(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def srs(
        self, request: SRSRatingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return Simple Rating System ratings by team and season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated SRS rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await SRS_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def expanded_srs(self, request: ExpandedSRSRatingsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def expanded_srs(
        self,
        request: ExpandedSRSRatingsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return expanded SRS ratings including lower classifications.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated expanded SRS rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await EXPANDED_SRS_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def elo(self, request: EloRatingsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def elo(
        self, request: EloRatingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return historical Elo ratings for the selected period.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated Elo rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await ELO_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def fpi(self, request: FPIRatingsRequest, /) -> FrameT: ...

    @overload
    async def fpi(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def fpi(
        self, request: FPIRatingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return Football Power Index ratings by team and season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated FPI rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await FPI_RATINGS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )


__all__ = ["RatingsResource"]
