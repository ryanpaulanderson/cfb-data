"""Expose public validated Drives sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.drives._operations import DRIVES_LIST
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.enums import Classification, SeasonType

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


@source(operation=DRIVES_LIST)
async def drives(
    context: SourceContext[Drive],
    *,
    year: int,
    season_type: _SeasonTypeArgument | None = None,
    week: int | None = None,
    team: str | None = None,
    offense: str | None = None,
    defense: str | None = None,
    conference: str | None = None,
    offense_conference: str | None = None,
    defense_conference: str | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[Drive]:
    """Return validated drives through the coordinator-owned client.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param team: Optional participating-team selector.
    :param offense: Optional offensive-team selector.
    :param defense: Optional defensive-team selector.
    :param conference: Optional participating-conference selector.
    :param offense_conference: Optional offensive-conference selector.
    :param defense_conference: Optional defensive-conference selector.
    :param classification: Optional classification selector.
    :return: Validated drives in source order.
    """
    return await context.retrieve(
        year=year,
        season_type=season_type,
        week=week,
        team=team,
        offense=offense,
        defense=defense,
        conference=conference,
        offense_conference=offense_conference,
        defense_conference=defense_conference,
        classification=classification,
    )


__all__ = ["drives"]
