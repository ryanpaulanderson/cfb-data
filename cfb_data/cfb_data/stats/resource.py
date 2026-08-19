"""Expose typed Stats endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.enums import Classification, SeasonType
from cfb_data.stats._operations import (
    ADVANCED_GAME_STATS,
    ADVANCED_SEASON_STATS,
    GAME_HAVOC_STATS,
    PLAYER_GAME_SUCCESS,
    PLAYER_SEASON_STATS,
    PLAYER_SEASON_SUCCESS,
    TEAM_SEASON_STATS,
)
from cfb_data.stats.models.pydantic.requests import (
    AdvancedGameStatsRequest,
    AdvancedSeasonStatsRequest,
    GameHavocRequest,
    PlayerGameSuccessRequest,
    PlayerSeasonStatsRequest,
    PlayerSeasonSuccessRequest,
    TeamSeasonStatsRequest,
)
from cfb_data.stats.models.pydantic.responses import StatCategory, _StatCategoryValue

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

_CATEGORY_VALUES = TypeAdapter(list[_StatCategoryValue])


class _CategoriesRequest(BaseModel):
    """Represent the empty filter set accepted by ``GET /stats/categories``."""

    model_config = ConfigDict(extra="forbid")


_CATEGORIES_REQUEST = _CategoriesRequest()


class StatsResource[FrameT]:
    """Provide validated Stats endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def player_season(self, request: PlayerSeasonStatsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def player_season(
        self, request: PlayerSeasonStatsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player statistics aggregated by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``PlayerStat`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_SEASON_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_season_success(
        self, request: PlayerSeasonSuccessRequest, /
    ) -> FrameT: ...

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
    ) -> FrameT: ...

    async def player_season_success(
        self, request: PlayerSeasonSuccessRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player passing and rushing success rates by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated season success-rate rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_SEASON_SUCCESS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def player_game_success(
        self, request: PlayerGameSuccessRequest, /
    ) -> FrameT: ...

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
    ) -> FrameT: ...

    async def player_game_success(
        self, request: PlayerGameSuccessRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return player passing and rushing success rates by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated game success-rate rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await PLAYER_GAME_SUCCESS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def team_season(self, request: TeamSeasonStatsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def team_season(
        self, request: TeamSeasonStatsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team statistics aggregated by season.

        ``stat_value`` preserves upstream strings and numbers in an object-typed
        column for both supported DataFrame backends.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamStat`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_SEASON_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    async def categories(self) -> FrameT:
        """Return team-stat categories as a one-column selected frame.

        :return: Eager frame with one ``category`` column in upstream order.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        values = await self._executor.fetch_values(
            endpoint="/stats/categories",
            request=_CATEGORIES_REQUEST,
            response_adapter=_CATEGORY_VALUES,
        )
        rows = [StatCategory(category=value.root) for value in values]
        return self._dataframe_adapter.from_models(
            endpoint="/stats/categories",
            row_model=StatCategory,
            models=rows,
        )

    @overload
    async def advanced_season(
        self, request: AdvancedSeasonStatsRequest, /
    ) -> FrameT: ...

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
    ) -> FrameT: ...

    async def advanced_season(
        self, request: AdvancedSeasonStatsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return advanced team statistics aggregated by season.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated advanced season rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await ADVANCED_SEASON_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def advanced_game(self, request: AdvancedGameStatsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def advanced_game(
        self, request: AdvancedGameStatsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return advanced team statistics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated advanced game rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await ADVANCED_GAME_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def game_havoc(self, request: GameHavocRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def game_havoc(
        self, request: GameHavocRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team havoc statistics by game.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated game havoc rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await GAME_HAVOC_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )


__all__ = ["StatsResource"]
