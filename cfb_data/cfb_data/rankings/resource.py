"""Expose typed Rankings endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.enums import RankingPoll, SeasonType
from cfb_data.rankings._operations import RANKINGS_LIST
from cfb_data.rankings.models.pydantic.requests import RankingsRequest

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
type _RankingPollArgument = RankingPoll | Literal["cfp"]


class RankingsResource[FrameT]:
    """Provide validated Rankings endpoints with selected frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: RankingsRequest, /) -> FrameT: ...

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
    ) -> FrameT: ...

    async def list(
        self, request: RankingsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return historical poll rankings grouped by season week.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated poll-week rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await RANKINGS_LIST.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )


__all__ = ["RankingsResource"]
