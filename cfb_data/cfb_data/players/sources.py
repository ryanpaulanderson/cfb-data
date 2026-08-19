"""Expose public validated Players sources for modular recipes."""

from __future__ import annotations

from cfb_data.analytics import SourceContext, source
from cfb_data.players._operations import PLAYER_USAGE
from cfb_data.players.models.pydantic.responses import PlayerUsage


@source(operation=PLAYER_USAGE)
async def player_usage(
    context: SourceContext[PlayerUsage],
    *,
    year: int,
    conference: str | None = None,
    position: str | None = None,
    team: str | None = None,
    player_id: int | None = None,
    exclude_garbage_time: bool | None = None,
) -> list[PlayerUsage]:
    """Return validated player-usage rows in upstream order.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param conference: Optional conference selector.
    :param position: Optional position selector.
    :param team: Optional team selector.
    :param player_id: Optional numeric upstream athlete selector.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :return: Validated source rows without analytical manipulation.
    """
    return await context.retrieve(
        year=year,
        conference=conference,
        position=position,
        team=team,
        player_id=player_id,
        exclude_garbage_time=exclude_garbage_time,
    )


__all__ = ["player_usage"]
