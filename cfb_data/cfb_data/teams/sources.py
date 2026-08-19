"""Expose public validated Teams sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification
from cfb_data.teams._operations import ROSTER_LIST, TEAM_ATS, TEAM_TALENT, TEAMS_LIST
from cfb_data.teams.models.pydantic.responses import (
    RosterPlayer,
    Team,
    TeamATS,
    TeamTalent,
)

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


@source(operation=TEAM_ATS)
async def team_ats(
    context: SourceContext[TeamATS],
    *,
    year: int,
    conference: str | None = None,
    team: str | None = None,
) -> list[TeamATS]:
    """Return validated team ATS records in source order.

    :param context: Engine-owned source execution context.
    :param year: Required ATS season.
    :param conference: Optional conference selector.
    :param team: Optional team selector.
    :return: Source-faithful ATS rows.
    """
    return await context.retrieve(year=year, conference=conference, team=team)


@source(operation=TEAM_TALENT)
async def team_talent(
    context: SourceContext[TeamTalent],
    *,
    year: int,
) -> list[TeamTalent]:
    """Return validated team-talent ratings in source order.

    :param context: Engine-owned source execution context.
    :param year: Required talent-composite season.
    :return: Source-faithful team talent rows.
    """
    return await context.retrieve(year=year)


__all__ = ["roster", "team_ats", "team_talent", "teams"]
