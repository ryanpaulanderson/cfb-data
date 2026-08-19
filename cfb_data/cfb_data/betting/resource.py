"""Expose typed Betting endpoints through the primary client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast, overload

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.betting.models.pydantic.requests import BettingLinesRequest
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.enums import SeasonType

if TYPE_CHECKING:
    from cfb_data.analytics._sources import EndpointOperation

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
        source = _betting_source()
        endpoint = source.endpoint
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=source.request_model,
            request=request,
            filters=filters,
        )
        rows = await source.fetch(self._executor, validated)
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=source.output.row_model, models=rows
        )


def _betting_source() -> EndpointOperation[BettingLinesRequest, BettingGame]:
    from cfb_data.analytics._sources import EndpointOperation, endpoint_operation

    return cast(
        EndpointOperation[BettingLinesRequest, BettingGame],
        endpoint_operation("cfbd.betting.lines"),
    )


__all__ = ["BettingResource"]
