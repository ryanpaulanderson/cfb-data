"""Expose public validated Rankings sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import RankingPoll, SeasonType
from cfb_data.rankings._operations import RANKINGS_LIST
from cfb_data.rankings.models.pydantic.responses import PollWeek

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


@source(operation=RANKINGS_LIST)
async def rankings(
    context: SourceContext[PollWeek],
    *,
    year: int,
    season_type: _SeasonTypeArgument | None = None,
    week: int | None = None,
    poll: _RankingPollArgument | None = None,
    latest: bool | None = None,
    final: bool | None = None,
) -> list[PollWeek]:
    """Return validated poll snapshots through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param poll: Optional upstream poll selector.
    :param latest: Optional latest-CFP selector.
    :param final: Optional final-CFP selector.
    :return: Validated poll weeks in source order.
    """
    return await context.retrieve(
        year=year,
        season_type=season_type,
        week=week,
        poll=poll,
        latest=latest,
        final=final,
    )


__all__ = ["rankings"]
