"""Expose typed game endpoints through the primary client."""

from __future__ import annotations

import builtins
from typing import Literal, TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)
from cfb_data.games._operations import (
    GAMES_LIST,
    GAMES_PLAYER_STATS,
    GAMES_TEAM_STATS,
    TEAM_RECORDS,
)
from cfb_data.games.models.pydantic.requests import (
    AdvancedBoxScoreRequest,
    CalendarRequest,
    GameMediaRequest,
    GamesRequest,
    GameWeatherRequest,
    PlayerGameStatsRequest,
    RecordsRequest,
    ScoreboardRequest,
    TeamGameStatsRequest,
)
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    CalendarWeek,
    GameMedia,
    GameWeather,
    ScoreboardGame,
)

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
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
type _MediaTypeArgument = MediaType | Literal["tv", "radio", "web", "ppv", "mobile"]
type _CompetitionArgument = PlayoffCompetition | Literal["cfp"]
type _RoundArgument = (
    PlayoffRound | Literal["first_round", "quarterfinal", "semifinal", "championship"]
)

_CALENDAR_ROWS = TypeAdapter(list[CalendarWeek])
_SCOREBOARD_ROWS = TypeAdapter(list[ScoreboardGame])
_MEDIA_ROWS = TypeAdapter(list[GameMedia])
_WEATHER_ROWS = TypeAdapter(list[GameWeather])
_ADVANCED_BOX = TypeAdapter(AdvancedBoxScore)


class GamesResource[FrameT]:
    """Provide validated Games endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: GamesRequest, /) -> FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        home: str | None = None,
        away: str | None = None,
        conference: str | None = None,
        classification: _ClassificationArgument | None = None,
        game_id: int | None = None,
        competition: _CompetitionArgument | None = None,
        round: _RoundArgument | None = None,
    ) -> FrameT: ...

    async def list(
        self,
        request: GamesRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return games in upstream order as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Game`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await GAMES_LIST.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request,
            filters,
        )

    @overload
    async def records(self, request: RecordsRequest, /) -> FrameT: ...

    @overload
    async def records(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def records(
        self,
        request: RecordsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return team records as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamRecords`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_RECORDS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def calendar(self, request: CalendarRequest, /) -> FrameT: ...

    @overload
    async def calendar(
        self,
        request: None = None,
        /,
        *,
        year: int,
    ) -> FrameT: ...

    async def calendar(
        self,
        request: CalendarRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return calendar weeks as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``CalendarWeek`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_frame(
            endpoint="/calendar",
            request_type=CalendarRequest,
            request=request,
            filters=filters,
            response_adapter=_CALENDAR_ROWS,
            row_model=CalendarWeek,
        )

    @overload
    async def scoreboard(self, request: ScoreboardRequest, /) -> FrameT: ...

    @overload
    async def scoreboard(
        self,
        request: None = None,
        /,
        *,
        classification: _ClassificationArgument | None = None,
        conference: str | None = None,
    ) -> FrameT: ...

    async def scoreboard(
        self,
        request: ScoreboardRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return current scoreboard games as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``ScoreboardGame`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_frame(
            endpoint="/scoreboard",
            request_type=ScoreboardRequest,
            request=request,
            filters=filters,
            response_adapter=_SCOREBOARD_ROWS,
            row_model=ScoreboardGame,
        )

    @overload
    async def media(self, request: GameMediaRequest, /) -> FrameT: ...

    @overload
    async def media(
        self,
        request: None = None,
        /,
        *,
        year: int,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        media_type: _MediaTypeArgument | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def media(
        self,
        request: GameMediaRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return game broadcasts as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``GameMedia`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_frame(
            endpoint="/games/media",
            request_type=GameMediaRequest,
            request=request,
            filters=filters,
            response_adapter=_MEDIA_ROWS,
            row_model=GameMedia,
        )

    @overload
    async def weather(self, request: GameWeatherRequest, /) -> FrameT: ...

    @overload
    async def weather(
        self,
        request: None = None,
        /,
        *,
        game_id: int | None = None,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def weather(
        self,
        request: GameWeatherRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return game weather as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``GameWeather`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_frame(
            endpoint="/games/weather",
            request_type=GameWeatherRequest,
            request=request,
            filters=filters,
            response_adapter=_WEATHER_ROWS,
            row_model=GameWeather,
        )

    @overload
    async def player_stats(
        self,
        request: PlayerGameStatsRequest,
        /,
    ) -> FrameT: ...

    @overload
    async def player_stats(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        category: str | None = None,
        game_id: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def player_stats(
        self,
        request: PlayerGameStatsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return player game statistics as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``PlayerGameStats`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await GAMES_PLAYER_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def team_stats(self, request: TeamGameStatsRequest, /) -> FrameT: ...

    @overload
    async def team_stats(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def team_stats(
        self,
        request: TeamGameStatsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return team game statistics as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamGameStats`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await GAMES_TEAM_STATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def advanced_box_score(
        self,
        request: AdvancedBoxScoreRequest,
        /,
    ) -> AdvancedBoxScore: ...

    @overload
    async def advanced_box_score(
        self,
        request: None = None,
        /,
        *,
        game_id: int,
    ) -> AdvancedBoxScore: ...

    async def advanced_box_score(
        self,
        request: AdvancedBoxScoreRequest | None = None,
        /,
        **filters: object,
    ) -> AdvancedBoxScore:
        """Return the nested advanced box score as one validated model.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Validated nested game, team, and player sections.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, decode, or validation fails.
        """
        endpoint = "/game/box/advanced"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=AdvancedBoxScoreRequest,
            request=request,
            filters=filters,
        )
        return await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_ADVANCED_BOX,
        )

    async def _fetch_frame(
        self,
        *,
        endpoint: str,
        request_type: type[_RequestT],
        request: _RequestT | None,
        filters: dict[str, object],
        response_adapter: TypeAdapter[builtins.list[_RowT]],
        row_model: type[_RowT],
    ) -> FrameT:
        """Share the validated-list-to-frame flow across game endpoints."""
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
            endpoint=endpoint,
            row_model=row_model,
            models=rows,
        )
