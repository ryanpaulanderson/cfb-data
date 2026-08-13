"""Expose typed Rankings endpoints through the primary client."""

from __future__ import annotations

from typing import Generic, Literal, TypeAlias, TypeVar, overload

from pydantic import TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import RankingPoll, SeasonType
from cfb_data.rankings.models.pydantic.requests import RankingsRequest
from cfb_data.rankings.models.pydantic.responses import PollWeek

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
_RankingPollArgument: TypeAlias = RankingPoll | Literal["cfp"]

_POLL_WEEK_ROWS = TypeAdapter(list[PollWeek])


class RankingsResource(Generic[_FrameT]):
    """Provide validated Rankings endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: RankingsRequest, /) -> _FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        year: int,
        season_type: _SeasonTypeArgument | None = None,
        week: int | None = None,
        poll: _RankingPollArgument | None = None,
        latest: bool | None = None,
        final: bool | None = None,
    ) -> _FrameT: ...

    async def list(
        self, request: RankingsRequest | None = None, /, **filters: object
    ) -> _FrameT:
        """Return historical poll rankings grouped by season week.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated poll-week rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/rankings"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=RankingsRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_POLL_WEEK_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=PollWeek, models=rows
        )


__all__ = ["RankingsResource"]
