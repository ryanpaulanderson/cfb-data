"""Expose typed Betting endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.betting._operations import BETTING_LINES
from cfb_data.betting.models.pydantic.requests import BettingLinesRequest
from cfb_data.enums import SeasonType

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


class BettingResource[FrameT]:
    """Provide validated Betting endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def lines(self, request: BettingLinesRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def lines(
        self, request: BettingLinesRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return games with nested historical provider lines.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated betting-game rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await BETTING_LINES.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )


__all__ = ["BettingResource"]
