"""Expose public validated Coaches sources for modular recipes."""

from __future__ import annotations

from cfb_data.analytics import SourceContext, source
from cfb_data.coaches._operations import COACH_SEASONS, COACH_TENURES
from cfb_data.coaches.models.pydantic.responses import CoachTenure, DetailedCoachSeason


@source(operation=COACH_SEASONS)
async def coach_seasons(
    context: SourceContext[DetailedCoachSeason],
    *,
    coach_id: int | None = None,
    team: str | None = None,
    year: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
) -> list[DetailedCoachSeason]:
    """Return validated coach-season rows through the coordinator client.

    :param context: Engine-owned source execution context.
    :param coach_id: Optional exact coach identifier.
    :param team: Optional team selector.
    :param year: Optional exact season.
    :param min_year: Optional inclusive first season.
    :param max_year: Optional inclusive last season.
    :return: Validated detailed coach seasons in source order.
    """
    return await context.retrieve(
        coach_id=coach_id,
        team=team,
        year=year,
        min_year=min_year,
        max_year=max_year,
    )


@source(operation=COACH_TENURES)
async def coach_tenures(
    context: SourceContext[CoachTenure],
    *,
    coach_id: int | None = None,
    team: str | None = None,
    year: int | None = None,
    active: bool | None = None,
) -> list[CoachTenure]:
    """Return validated coaching tenures through the coordinator client.

    :param context: Engine-owned source execution context.
    :param coach_id: Optional exact coach identifier.
    :param team: Optional team selector.
    :param year: Optional season intersecting a tenure.
    :param active: Optional active-tenure selector.
    :return: Validated tenures in source order.
    """
    return await context.retrieve(
        coach_id=coach_id,
        team=team,
        year=year,
        active=active,
    )


__all__ = ["coach_seasons", "coach_tenures"]
