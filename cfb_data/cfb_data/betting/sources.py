"""Expose public validated Betting sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.betting._operations import BETTING_LINES
from cfb_data.betting.models.pydantic.responses import BettingGame
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


@source(operation=BETTING_LINES)
async def betting_lines(
    context: SourceContext[BettingGame],
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
) -> list[BettingGame]:
    """Return validated games and provider lines through the coordinator.

    :param context: Engine-owned source execution context.
    :param game_id: Optional exact game identifier.
    :param year: Optional season year when game ID is absent.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param team: Optional participating-team selector.
    :param home: Optional home-team selector.
    :param away: Optional away-team selector.
    :param conference: Optional participating-conference selector.
    :param provider: Optional line-provider selector.
    :return: Validated betting games in source order.
    """
    return await context.retrieve(
        game_id=game_id,
        year=year,
        season_type=season_type,
        week=week,
        team=team,
        home=home,
        away=away,
        conference=conference,
        provider=provider,
    )


__all__ = ["betting_lines"]
