"""Expose typed Stats endpoints through the primary client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, Literal, TypeAlias, TypeVar, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import Classification, SeasonType
from cfb_data.stats.models.pydantic.requests import (
    AdvancedGameStatsRequest,
    AdvancedSeasonStatsRequest,
    GameHavocRequest,
    PlayerGameSuccessRequest,
    PlayerSeasonStatsRequest,
    PlayerSeasonSuccessRequest,
    TeamSeasonStatsRequest,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedGameStat,
    AdvancedSeasonStat,
    GameHavocStats,
    PlayerGameSuccessRate,
    PlayerSeasonSuccessRate,
    PlayerStat,
    StatCategory,
    TeamStat,
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

_PLAYER_STAT_ROWS = TypeAdapter(list[PlayerStat])
_PLAYER_SEASON_SUCCESS_ROWS = TypeAdapter(list[PlayerSeasonSuccessRate])
_PLAYER_GAME_SUCCESS_ROWS = TypeAdapter(list[PlayerGameSuccessRate])
_TEAM_STAT_ROWS = TypeAdapter(list[TeamStat])
_CATEGORY_VALUES = TypeAdapter(list[str])
_ADVANCED_SEASON_ROWS = TypeAdapter(list[AdvancedSeasonStat])
_ADVANCED_GAME_ROWS = TypeAdapter(list[AdvancedGameStat])
_GAME_HAVOC_ROWS = TypeAdapter(list[GameHavocStats])


class _CategoriesRequest(BaseModel):
    """Represent the empty filter set accepted by ``GET /stats/categories``."""

    model_config = ConfigDict(extra="forbid")


_CATEGORIES_REQUEST = _CategoriesRequest()


class StatsResource(Generic[_FrameT]):
    """Provide validated Stats endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def player_season(self, request: PlayerSeasonStatsRequest, /) -> _FrameT: ...

    @overload
    async def player_season(
        self,
        request: None = None,
        /,
        *,
        year: int,
        conference: str | None = None,
        team: str | None = None,
        start_week: int | None = None,
        end_week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        category: str | None = None,
    ) -> _FrameT: ...

    async def player_season(
        self, request: PlayerSeasonStatsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return player statistics aggregated by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``PlayerStat`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/player/season",
            request_type=PlayerSeasonStatsRequest,
            request=request,
            filters=filters,
            response_adapter=_PLAYER_STAT_ROWS,
            row_model=PlayerStat,
        )

    @overload
    async def player_season_success(
        self, request: PlayerSeasonSuccessRequest, /
    ) -> _FrameT: ...

    @overload
    async def player_season_success(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        conference: str | None = None,
        team: str | None = None,
        player_id: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        start_week: int | None = None,
        end_week: int | None = None,
        threshold: int | None = None,
        exclude_garbage_time: bool | None = None,
    ) -> _FrameT: ...

    async def player_season_success(
        self, request: PlayerSeasonSuccessRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return player passing and rushing success rates by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated season success-rate rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/player/success",
            request_type=PlayerSeasonSuccessRequest,
            request=request,
            filters=filters,
            response_adapter=_PLAYER_SEASON_SUCCESS_ROWS,
            row_model=PlayerSeasonSuccessRate,
        )

    @overload
    async def player_game_success(
        self, request: PlayerGameSuccessRequest, /
    ) -> _FrameT: ...

    @overload
    async def player_game_success(
        self,
        request: None = None,
        /,
        *,
        year: int,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        conference: str | None = None,
        team: str | None = None,
        player_id: int | None = None,
        threshold: int | None = None,
        exclude_garbage_time: bool | None = None,
    ) -> _FrameT: ...

    async def player_game_success(
        self, request: PlayerGameSuccessRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return player passing and rushing success rates by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated game success-rate rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/player/success/game",
            request_type=PlayerGameSuccessRequest,
            request=request,
            filters=filters,
            response_adapter=_PLAYER_GAME_SUCCESS_ROWS,
            row_model=PlayerGameSuccessRate,
        )

    @overload
    async def team_season(self, request: TeamSeasonStatsRequest, /) -> _FrameT: ...

    @overload
    async def team_season(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
        start_week: int | None = None,
        end_week: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> _FrameT: ...

    async def team_season(
        self, request: TeamSeasonStatsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return team statistics aggregated by season.

        ``stat_value`` preserves upstream strings and numbers in an object-typed
        column for both supported DataFrame backends.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamStat`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/season",
            request_type=TeamSeasonStatsRequest,
            request=request,
            filters=filters,
            response_adapter=_TEAM_STAT_ROWS,
            row_model=TeamStat,
        )

    async def categories(self) -> _FrameT:
        """Return team-stat categories as a one-column selected frame.

        :return: Eager frame with one ``category`` column in upstream order.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        values = await self._executor.fetch_values(
            endpoint="/stats/categories",
            request=_CATEGORIES_REQUEST,
            response_adapter=_CATEGORY_VALUES,
        )
        rows = [StatCategory(category=value) for value in values]
        return self._dataframe_adapter.from_models(
            endpoint="/stats/categories",
            row_model=StatCategory,
            models=rows,
        )

    @overload
    async def advanced_season(
        self, request: AdvancedSeasonStatsRequest, /
    ) -> _FrameT: ...

    @overload
    async def advanced_season(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        exclude_garbage_time: bool | None = None,
        start_week: int | None = None,
        end_week: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> _FrameT: ...

    async def advanced_season(
        self, request: AdvancedSeasonStatsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return advanced team statistics aggregated by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated advanced season rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/season/advanced",
            request_type=AdvancedSeasonStatsRequest,
            request=request,
            filters=filters,
            response_adapter=_ADVANCED_SEASON_ROWS,
            row_model=AdvancedSeasonStat,
        )

    @overload
    async def advanced_game(self, request: AdvancedGameStatsRequest, /) -> _FrameT: ...

    @overload
    async def advanced_game(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        week: int | None = None,
        opponent: str | None = None,
        exclude_garbage_time: bool | None = None,
        season_type: _SeasonTypeArgument | None = None,
    ) -> _FrameT: ...

    async def advanced_game(
        self, request: AdvancedGameStatsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return advanced team statistics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated advanced game rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/game/advanced",
            request_type=AdvancedGameStatsRequest,
            request=request,
            filters=filters,
            response_adapter=_ADVANCED_GAME_ROWS,
            row_model=AdvancedGameStat,
        )

    @overload
    async def game_havoc(self, request: GameHavocRequest, /) -> _FrameT: ...

    @overload
    async def game_havoc(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        week: int | None = None,
        opponent: str | None = None,
        season_type: _SeasonTypeArgument | None = None,
    ) -> _FrameT: ...

    async def game_havoc(
        self, request: GameHavocRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return team havoc statistics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated game havoc rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/stats/game/havoc",
            request_type=GameHavocRequest,
            request=request,
            filters=filters,
            response_adapter=_GAME_HAVOC_ROWS,
            row_model=GameHavocStats,
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
        """Validate, fetch, and convert one Stats list route."""
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
            endpoint=endpoint,
            row_model=row_model,
            models=rows,
        )


__all__ = ["StatsResource"]
