"""Expose public validated Recruiting sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import RecruitClassification
from cfb_data.recruiting._operations import RECRUITING_PLAYERS, RECRUITING_TEAMS
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)

type _RecruitClassificationArgument = (
    RecruitClassification | Literal["JUCO", "PrepSchool", "HighSchool"]
)


@source(operation=RECRUITING_PLAYERS)
async def recruiting_players(
    context: SourceContext[Recruit],
    *,
    year: int | None = None,
    team: str | None = None,
    position: str | None = None,
    state: str | None = None,
    classification: _RecruitClassificationArgument | None = None,
) -> list[Recruit]:
    """Return validated recruits through the coordinator-owned client.

    :param context: Engine-owned source execution context.
    :param year: Optional class year when team is absent.
    :param team: Optional committed-team selector.
    :param position: Optional position selector.
    :param state: Optional home-state selector.
    :param classification: Optional recruit-type selector.
    :return: Validated recruits in source order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        position=position,
        state=state,
        classification=classification,
    )


@source(operation=RECRUITING_TEAMS)
async def recruiting_teams(
    context: SourceContext[TeamRecruitingRanking],
    *,
    year: int | None = None,
    team: str | None = None,
) -> list[TeamRecruitingRanking]:
    """Return validated team class rankings through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Optional class year.
    :param team: Optional team selector.
    :return: Validated team rankings in source order.
    """
    return await context.retrieve(year=year, team=team)


__all__ = ["recruiting_players", "recruiting_teams"]
