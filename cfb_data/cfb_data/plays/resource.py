"""Expose typed Plays endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import Classification, SeasonType
from cfb_data.plays._operations import PLAYS_LIST
from cfb_data.plays.models.pydantic.requests import (
    LivePlaysRequest,
    PlaysRequest,
    PlayStatsRequest,
)
from cfb_data.plays.models.pydantic.responses import (
    LiveGame,
    PlayStat,
    PlayStatType,
    PlayType,
)

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
type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]

_PLAY_TYPE_ROWS = TypeAdapter(list[PlayType])
_PLAY_STAT_ROWS = TypeAdapter(list[PlayStat])
_PLAY_STAT_TYPE_ROWS = TypeAdapter(list[PlayStatType])
_LIVE_GAME = TypeAdapter(LiveGame)


class _EmptyRequest(BaseModel):
    """Represent a route with no query parameters."""

    model_config = ConfigDict(extra="forbid")


_EMPTY_REQUEST = _EmptyRequest()


class PlaysResource[FrameT]:
    """Provide validated Plays endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: PlaysRequest, /) -> FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        year: int,
        week: int,
        team: str | None = None,
        offense: str | None = None,
        defense: str | None = None,
        offense_conference: str | None = None,
        defense_conference: str | None = None,
        conference: str | None = None,
        play_type: str | None = None,
        season_type: _SeasonTypeArgument | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def list(
        self,
        request: PlaysRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return historical plays as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Play`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYS_LIST.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    async def types(self) -> FrameT:
        """Return available play types as the selected DataFrame type.

        :return: Eager frame containing validated ``PlayType`` rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        endpoint = "/plays/types"
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=_EMPTY_REQUEST,
            response_adapter=_PLAY_TYPE_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=PlayType,
            models=rows,
        )

    @overload
    async def stats(self, request: PlayStatsRequest, /) -> FrameT: ...

    @overload
    async def stats(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        team: str | None = None,
        game_id: int | None = None,
        athlete_id: int | None = None,
        stat_type_id: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def stats(
        self,
        request: PlayStatsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return athlete play statistics as the selected DataFrame type.

        The upstream endpoint limits responses to 2,000 rows.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``PlayStat`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/plays/stats"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=PlayStatsRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_PLAY_STAT_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=PlayStat,
            models=rows,
        )

    async def stat_types(self) -> FrameT:
        """Return athlete play-stat types as the selected DataFrame type.

        :return: Eager frame containing validated ``PlayStatType`` rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        endpoint = "/plays/stats/types"
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=_EMPTY_REQUEST,
            response_adapter=_PLAY_STAT_TYPE_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=PlayStatType,
            models=rows,
        )

    @overload
    async def live(self, request: LivePlaysRequest, /) -> LiveGame: ...

    @overload
    async def live(
        self,
        request: None = None,
        /,
        *,
        game_id: int,
    ) -> LiveGame: ...

    async def live(
        self,
        request: LivePlaysRequest | None = None,
        /,
        **filters: object,
    ) -> LiveGame:
        """Return live play-by-play and metrics as one validated model.

        The upstream route requires Patreon Tier 2 access.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Validated nested live game, team, drive, and play data.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, decode, or validation fails.
        """
        endpoint = "/live/plays"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=LivePlaysRequest,
            request=request,
            filters=filters,
        )
        return await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_LIVE_GAME,
        )
