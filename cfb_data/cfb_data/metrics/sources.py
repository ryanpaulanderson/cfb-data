"""Expose public validated Metrics sources for modular recipes."""

from __future__ import annotations

from cfb_data.analytics import SourceContext, source
from cfb_data.metrics._operations import PLAY_WIN_PROBABILITIES
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability


@source(operation=PLAY_WIN_PROBABILITIES)
async def play_win_probabilities(
    context: SourceContext[PlayWinProbability],
    *,
    game_id: int,
) -> list[PlayWinProbability]:
    """Return validated play probabilities through the coordinator client.

    :param context: Engine-owned source execution context.
    :param game_id: Required exact game identifier.
    :return: Validated play probabilities in source order.
    """
    return await context.retrieve(game_id=game_id)


__all__ = ["play_win_probabilities"]
