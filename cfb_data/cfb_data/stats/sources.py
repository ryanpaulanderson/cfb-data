"""Expose public validated Stats sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, SeasonType
from cfb_data.stats._operations import (
    ADVANCED_SEASON_STATS,
    PLAYER_SEASON_STATS,
    TEAM_SEASON_STATS,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
)

type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
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


@source(operation=PLAYER_SEASON_STATS)
async def player_season_stats(
    context: SourceContext[PlayerStat],
    *,
    year: int,
    conference: str | None = None,
    team: str | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    category: str | None = None,
) -> list[PlayerStat]:
    """Return validated long-form player-season statistics.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param conference: Optional conference selector.
    :param team: Optional team selector.
    :param start_week: Optional inclusive starting week.
    :param end_week: Optional inclusive ending week.
    :param season_type: Optional season phase.
    :param category: Optional statistic-category selector.
    :return: Validated long-form statistics in source order.
    """
    return await context.retrieve(
        year=year,
        conference=conference,
        team=team,
        start_week=start_week,
        end_week=end_week,
        season_type=season_type,
        category=category,
    )


@source(operation=TEAM_SEASON_STATS)
async def team_season_stats(
    context: SourceContext[TeamStat],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[TeamStat]:
    """Return validated conventional team-season statistics.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param start_week: Optional inclusive starting week.
    :param end_week: Optional inclusive ending week.
    :param classification: Optional classification selector.
    :return: Validated source statistics in upstream order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        conference=conference,
        start_week=start_week,
        end_week=end_week,
        classification=classification,
    )


@source(operation=ADVANCED_SEASON_STATS)
async def advanced_season_stats(
    context: SourceContext[AdvancedSeasonStat],
    *,
    year: int | None = None,
    team: str | None = None,
    exclude_garbage_time: bool | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[AdvancedSeasonStat]:
    """Return validated advanced team-season statistics.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :param start_week: Optional inclusive starting week.
    :param end_week: Optional inclusive ending week.
    :param classification: Optional classification selector.
    :return: Validated source statistics in upstream order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        exclude_garbage_time=exclude_garbage_time,
        start_week=start_week,
        end_week=end_week,
        classification=classification,
    )


__all__ = ["advanced_season_stats", "player_season_stats", "team_season_stats"]
