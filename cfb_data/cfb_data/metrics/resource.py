"""Expose typed Metrics endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypeVar, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics._operations import (
    PLAY_WIN_PROBABILITIES,
    PLAYER_GAME_PPA,
    PLAYER_SEASON_PPA,
    TEAM_GAME_PPA,
    TEAM_SEASON_PPA,
)
from cfb_data.metrics.models.pydantic.requests import (
    PlayerGamePPARequest,
    PlayerSeasonPPARequest,
    PredictedPointsRequest,
    PregameWinProbabilityRequest,
    TeamGamePPARequest,
    TeamSeasonPPARequest,
    WinProbabilityRequest,
)
from cfb_data.metrics.models.pydantic.responses import (
    FieldGoalExpectedPoints,
    PredictedPointsValue,
    PregameWinProbability,
)

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
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

_PREDICTED_POINTS_ROWS = TypeAdapter(list[PredictedPointsValue])
_PREGAME_WIN_PROBABILITY_ROWS = TypeAdapter(list[PregameWinProbability])
_FIELD_GOAL_EP_ROWS = TypeAdapter(list[FieldGoalExpectedPoints])


class _FieldGoalEPRequest(BaseModel):
    """Represent the empty filter set accepted by ``GET /metrics/fg/ep``."""

    model_config = ConfigDict(extra="forbid")


_FIELD_GOAL_EP_REQUEST = _FieldGoalEPRequest()


class MetricsResource[FrameT]:
    """Provide validated Metrics endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def predicted_points(self, request: PredictedPointsRequest, /) -> FrameT: ...

    @overload
    async def predicted_points(
        self, request: None = None, /, *, down: int, distance: int
    ) -> FrameT: ...

    async def predicted_points(
        self, request: PredictedPointsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return predicted points by yard line for a down and distance.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated predicted-points rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/ppa/predicted",
            request_type=PredictedPointsRequest,
            request=request,
            filters=filters,
            response_adapter=_PREDICTED_POINTS_ROWS,
            row_model=PredictedPointsValue,
        )

    @overload
    async def team_season_ppa(self, request: TeamSeasonPPARequest, /) -> FrameT: ...

    @overload
    async def team_season_ppa(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
        exclude_garbage_time: bool | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def team_season_ppa(
        self, request: TeamSeasonPPARequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team predicted-points-added metrics by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team season PPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_SEASON_PPA.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def team_game_ppa(self, request: TeamGamePPARequest, /) -> FrameT: ...

    @overload
    async def team_game_ppa(
        self,
        request: None = None,
        /,
        *,
        year: int,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        exclude_garbage_time: bool | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def team_game_ppa(
        self, request: TeamGamePPARequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team predicted-points-added metrics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated team game PPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_GAME_PPA.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_game_ppa(self, request: PlayerGamePPARequest, /) -> FrameT: ...

    @overload
    async def player_game_ppa(
        self,
        request: None = None,
        /,
        *,
        year: int,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        position: str | None = None,
        player_id: int | None = None,
        threshold: int | None = None,
        exclude_garbage_time: bool | None = None,
    ) -> FrameT: ...

    async def player_game_ppa(
        self, request: PlayerGamePPARequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player predicted-points-added metrics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player game PPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_GAME_PPA.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_season_ppa(self, request: PlayerSeasonPPARequest, /) -> FrameT: ...

    @overload
    async def player_season_ppa(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        conference: str | None = None,
        team: str | None = None,
        position: str | None = None,
        player_id: int | None = None,
        threshold: int | None = None,
        exclude_garbage_time: bool | None = None,
    ) -> FrameT: ...

    async def player_season_ppa(
        self, request: PlayerSeasonPPARequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player predicted-points-added metrics by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated player season PPA rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_SEASON_PPA.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def win_probability(self, request: WinProbabilityRequest, /) -> FrameT: ...

    @overload
    async def win_probability(
        self, request: None = None, /, *, game_id: int
    ) -> FrameT: ...

    async def win_probability(
        self, request: WinProbabilityRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return play-by-play win probabilities for one game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated play probability rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAY_WIN_PROBABILITIES.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def pregame_win_probability(
        self, request: PregameWinProbabilityRequest, /
    ) -> FrameT: ...

    @overload
    async def pregame_win_probability(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
    ) -> FrameT: ...

    async def pregame_win_probability(
        self,
        request: PregameWinProbabilityRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return modeled pregame win probabilities.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated pregame probability rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/metrics/wp/pregame",
            request_type=PregameWinProbabilityRequest,
            request=request,
            filters=filters,
            response_adapter=_PREGAME_WIN_PROBABILITY_ROWS,
            row_model=PregameWinProbability,
        )

    async def field_goal_expected_points(self) -> FrameT:
        """Return field-goal expected points by distance.

        :return: Eager frame containing validated field-goal EP rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        rows = await self._executor.fetch_many(
            endpoint="/metrics/fg/ep",
            request=_FIELD_GOAL_EP_REQUEST,
            response_adapter=_FIELD_GOAL_EP_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint="/metrics/fg/ep",
            row_model=FieldGoalExpectedPoints,
            models=rows,
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


__all__ = ["MetricsResource"]
