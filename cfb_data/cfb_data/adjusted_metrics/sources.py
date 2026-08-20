"""Expose public validated Adjusted Metrics sources for modular recipes."""

from __future__ import annotations

from cfb_data.adjusted_metrics._operations import (
    KICKER_PAAR_METRICS,
    PLAYER_PASSING_METRICS,
    PLAYER_RUSHING_METRICS,
    TEAM_SEASON_METRICS,
)
from cfb_data.adjusted_metrics.models.pydantic.responses import (
    AdjustedTeamMetrics,
    KickerPAAR,
    PlayerWeightedEPA,
)
from cfb_data.analytics import SourceContext, source


@source(operation=TEAM_SEASON_METRICS)
async def adjusted_team_metrics(
    context: SourceContext[AdjustedTeamMetrics],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[AdjustedTeamMetrics]:
    """Return validated opponent-adjusted team metrics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional metric season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful adjusted team rows.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


@source(operation=PLAYER_PASSING_METRICS)
async def adjusted_player_passing(
    context: SourceContext[PlayerWeightedEPA],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
    position: str | None = None,
) -> list[PlayerWeightedEPA]:
    """Return validated adjusted player passing metrics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional metric season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param position: Optional position selector.
    :return: Source-faithful passing WEPA rows.
    """
    return await context.retrieve(
        year=year,
        team=team,
        conference=conference,
        position=position,
    )


@source(operation=PLAYER_RUSHING_METRICS)
async def adjusted_player_rushing(
    context: SourceContext[PlayerWeightedEPA],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
    position: str | None = None,
) -> list[PlayerWeightedEPA]:
    """Return validated adjusted player rushing metrics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional metric season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param position: Optional position selector.
    :return: Source-faithful rushing WEPA rows.
    """
    return await context.retrieve(
        year=year,
        team=team,
        conference=conference,
        position=position,
    )


@source(operation=KICKER_PAAR_METRICS)
async def kicker_paar_metrics(
    context: SourceContext[KickerPAAR],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[KickerPAAR]:
    """Return validated kicker PAAR metrics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional metric season.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Source-faithful kicker rows.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


__all__ = [
    "adjusted_player_passing",
    "adjusted_player_rushing",
    "adjusted_team_metrics",
    "kicker_paar_metrics",
]
