"""Expose public validated Teams sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification
from cfb_data.teams._operations import ROSTER_LIST, TEAMS_LIST
from cfb_data.teams.models.pydantic.responses import RosterPlayer, Team

type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]


@source(operation=TEAMS_LIST)
async def teams(
    context: SourceContext[Team],
    *,
    conference: str | None = None,
    year: int | None = None,
) -> list[Team]:
    """Return validated teams through the coordinator-owned client.

    :param context: Engine-owned source execution context.
    :param conference: Optional conference selector.
    :param year: Optional historical membership season.
    :return: Validated teams in source order.
    """
    return await context.retrieve(conference=conference, year=year)


@source(operation=ROSTER_LIST)
async def roster(
    context: SourceContext[RosterPlayer],
    *,
    team: str | None = None,
    year: int | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[RosterPlayer]:
    """Return validated roster memberships through the coordinator client.

    :param context: Engine-owned source execution context.
    :param team: Optional team selector.
    :param year: Optional roster season.
    :param classification: Optional classification selector.
    :return: Validated roster players in source order.
    """
    return await context.retrieve(
        team=team,
        year=year,
        classification=classification,
    )


__all__ = ["roster", "teams"]
