"""Expose public validated Plays sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, SeasonType
from cfb_data.plays._operations import PLAYS_LIST
from cfb_data.plays.models.pydantic.responses import Play

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


@source(operation=PLAYS_LIST)
async def plays(
    context: SourceContext[Play],
    *,
    year: int,
    week: int,
    team: str | None = None,
    offense: str | None = None,
    defense: str | None = None,
    offense_conference: str | None = None,
    defense_conference: str | None = None,
    conference: str | None = None,
    play_type: str | None = None,
    season_type: _SeasonTypeArgument | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[Play]:
    """Return validated historical plays through the coordinator-owned client.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param week: Required season week.
    :param team: Optional participating-team selector.
    :param offense: Optional offensive-team selector.
    :param defense: Optional defensive-team selector.
    :param offense_conference: Optional offensive-conference selector.
    :param defense_conference: Optional defensive-conference selector.
    :param conference: Optional participating-conference selector.
    :param play_type: Optional source play-type selector.
    :param season_type: Optional season phase.
    :param classification: Optional classification selector.
    :return: Validated plays in source order.
    """
    return await context.retrieve(
        year=year,
        week=week,
        team=team,
        offense=offense,
        defense=defense,
        offense_conference=offense_conference,
        defense_conference=defense_conference,
        conference=conference,
        play_type=play_type,
        season_type=season_type,
        classification=classification,
    )


__all__ = ["plays"]
