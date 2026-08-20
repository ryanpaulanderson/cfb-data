"""Expose public validated Stats sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, SeasonType
from cfb_data.stats._operations import (
    ADVANCED_GAME_STATS,
    ADVANCED_SEASON_STATS,
    GAME_HAVOC_STATS,
    PLAYER_GAME_SUCCESS,
    PLAYER_SEASON_STATS,
    PLAYER_SEASON_SUCCESS,
    TEAM_SEASON_STATS,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedGameStat,
    AdvancedSeasonStat,
    GameHavocStats,
    PlayerGameSuccessRate,
    PlayerSeasonSuccessRate,
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


@source(operation=ADVANCED_GAME_STATS)
async def advanced_game_stats(
    context: SourceContext[AdvancedGameStat],
    *,
    year: int | None = None,
    team: str | None = None,
    week: int | None = None,
    opponent: str | None = None,
    exclude_garbage_time: bool | None = None,
    season_type: _SeasonTypeArgument | None = None,
) -> list[AdvancedGameStat]:
    """Return validated advanced team-game statistics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param week: Optional season week.
    :param opponent: Optional opponent selector.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :param season_type: Optional season phase.
    :return: Validated advanced team-game rows in source order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        week=week,
        opponent=opponent,
        exclude_garbage_time=exclude_garbage_time,
        season_type=season_type,
    )


@source(operation=GAME_HAVOC_STATS)
async def game_havoc_stats(
    context: SourceContext[GameHavocStats],
    *,
    year: int | None = None,
    team: str | None = None,
    week: int | None = None,
    opponent: str | None = None,
    season_type: _SeasonTypeArgument | None = None,
) -> list[GameHavocStats]:
    """Return validated game havoc statistics in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param week: Optional season week.
    :param opponent: Optional opponent selector.
    :param season_type: Optional season phase.
    :return: Validated havoc rows in source order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        week=week,
        opponent=opponent,
        season_type=season_type,
    )


@source(operation=PLAYER_SEASON_SUCCESS)
async def player_season_success(
    context: SourceContext[PlayerSeasonSuccessRate],
    *,
    year: int | None = None,
    conference: str | None = None,
    team: str | None = None,
    player_id: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    threshold: int | None = None,
    exclude_garbage_time: bool | None = None,
) -> list[PlayerSeasonSuccessRate]:
    """Return validated player-season success rates in source order.

    :param context: Engine-owned source execution context.
    :param year: Optional season year.
    :param conference: Optional conference selector.
    :param team: Optional team selector.
    :param player_id: Optional numeric athlete identifier.
    :param season_type: Optional season phase.
    :param start_week: Optional inclusive starting week.
    :param end_week: Optional inclusive ending week.
    :param threshold: Optional minimum play threshold.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :return: Validated player-season success rows in source order.
    """
    return await context.retrieve(
        year=year,
        conference=conference,
        team=team,
        player_id=player_id,
        season_type=season_type,
        start_week=start_week,
        end_week=end_week,
        threshold=threshold,
        exclude_garbage_time=exclude_garbage_time,
    )


@source(operation=PLAYER_GAME_SUCCESS)
async def player_game_success(
    context: SourceContext[PlayerGameSuccessRate],
    *,
    year: int,
    week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    conference: str | None = None,
    team: str | None = None,
    player_id: int | None = None,
    threshold: int | None = None,
    exclude_garbage_time: bool | None = None,
) -> list[PlayerGameSuccessRate]:
    """Return validated player-game success rates in source order.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param conference: Optional conference selector.
    :param team: Optional team selector.
    :param player_id: Optional numeric athlete identifier.
    :param threshold: Optional minimum play threshold.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :return: Validated player-game success rows in source order.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        conference=conference,
        team=team,
        player_id=player_id,
        threshold=threshold,
        exclude_garbage_time=exclude_garbage_time,
    )


__all__ = [
    "advanced_game_stats",
    "advanced_season_stats",
    "game_havoc_stats",
    "player_game_success",
    "player_season_stats",
    "player_season_success",
    "team_season_stats",
]
