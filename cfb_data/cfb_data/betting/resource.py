"""Expose typed Betting endpoints through the primary client."""

from __future__ import annotations

from typing import Generic, Literal, TypeAlias, TypeVar, overload

from pydantic import TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.betting.models.pydantic.requests import BettingLinesRequest
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.enums import SeasonType

_FrameT = TypeVar("_FrameT")
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

_BETTING_GAME_ROWS = TypeAdapter(list[BettingGame])


class BettingResource(Generic[_FrameT]):
    """Provide validated Betting endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def lines(self, request: BettingLinesRequest, /) -> _FrameT: ...

    @overload
    async def lines(
        self,
        request: None = None,
        /,
        *,
        game_id: int | None = None,
        year: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        week: int | None = None,
        team: str | None = None,
        home: str | None = None,
        away: str | None = None,
        conference: str | None = None,
        provider: str | None = None,
    ) -> _FrameT: ...

    async def lines(
        self, request: BettingLinesRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return games with nested historical provider lines.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated betting-game rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/lines"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=BettingLinesRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_BETTING_GAME_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=BettingGame, models=rows
        )


__all__ = ["BettingResource"]
