"""Expose typed Playoffs endpoints through the primary client."""

from __future__ import annotations

from typing import Generic, Literal, TypeAlias, TypeVar, overload

from pydantic import TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import PlayoffRound
from cfb_data.playoffs.models.pydantic.requests import (
    CfpGamesRequest,
    CfpParticipantsRequest,
    CfpPlayoffRequest,
)
from cfb_data.playoffs.models.pydantic.responses import (
    CfpPlayoff,
    PlayoffMatchup,
    PlayoffParticipant,
)

_FrameT = TypeVar("_FrameT")
_PlayoffRoundArgument: TypeAlias = (
    PlayoffRound | Literal["first_round", "quarterfinal", "semifinal", "championship"]
)

_CFP_PLAYOFF = TypeAdapter(CfpPlayoff)
_CFP_PARTICIPANT_ROWS = TypeAdapter(list[PlayoffParticipant])
_CFP_GAME_ROWS = TypeAdapter(list[PlayoffMatchup])


class PlayoffsResource(Generic[_FrameT]):
    """Provide validated CFP endpoints with model and frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def cfp(self, request: CfpPlayoffRequest, /) -> CfpPlayoff: ...

    @overload
    async def cfp(self, request: None = None, /, *, year: int) -> CfpPlayoff: ...

    async def cfp(
        self, request: CfpPlayoffRequest | None = None, /, **filters: object
    ) -> CfpPlayoff:
        """Return one complete nested College Football Playoff bracket.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Validated bracket preserving participants, rounds, and matchups.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, or response validation fails.
        """
        endpoint = "/playoffs/cfp"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=CfpPlayoffRequest,
            request=request,
            filters=filters,
        )
        return await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_CFP_PLAYOFF,
        )

    @overload
    async def participants(self, request: CfpParticipantsRequest, /) -> _FrameT: ...

    @overload
    async def participants(self, request: None = None, /, *, year: int) -> _FrameT: ...

    async def participants(
        self, request: CfpParticipantsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return College Football Playoff participants for one season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated participant rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/playoffs/cfp/participants"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=CfpParticipantsRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_CFP_PARTICIPANT_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=PlayoffParticipant, models=rows
        )

    @overload
    async def games(self, request: CfpGamesRequest, /) -> _FrameT: ...

    @overload
    async def games(
        self,
        request: None = None,
        /,
        *,
        year: int,
        round: _PlayoffRoundArgument | None = None,
    ) -> _FrameT: ...

    async def games(
        self, request: CfpGamesRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return College Football Playoff matchups for one season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated matchup rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/playoffs/cfp/games"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=CfpGamesRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_CFP_GAME_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=PlayoffMatchup, models=rows
        )


__all__ = ["PlayoffsResource"]
