"""Expose public validated Metrics sources for modular recipes."""

from __future__ import annotations

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics._operations import (
    PLAY_WIN_PROBABILITIES,
    PLAYER_GAME_PPA,
    PLAYER_SEASON_PPA,
    TEAM_GAME_PPA,
    TEAM_SEASON_PPA,
)
from cfb_data.metrics.models.pydantic.responses import (
    PlayerGamePredictedPointsAdded,
    PlayerSeasonPredictedPointsAdded,
    PlayWinProbability,
    TeamGamePredictedPointsAdded,
    TeamSeasonPredictedPointsAdded,
)


@source(operation=TEAM_SEASON_PPA)
async def team_season_ppa(
    context: SourceContext[TeamSeasonPredictedPointsAdded],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
    exclude_garbage_time: bool | None = None,
    classification: Classification | None = None,
) -> list[TeamSeasonPredictedPointsAdded]:
    """Return validated team-season PPA through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :param classification: Optional classification selector.
    :return: Validated team-season PPA rows in source order.
    """
    return await context.retrieve(
        year=year,
        team=team,
        conference=conference,
        exclude_garbage_time=exclude_garbage_time,
        classification=classification,
    )


@source(operation=TEAM_GAME_PPA)
async def team_game_ppa(
    context: SourceContext[TeamGamePredictedPointsAdded],
    *,
    year: int,
    week: int | None = None,
    season_type: SeasonType | None = None,
    team: str | None = None,
    conference: str | None = None,
    exclude_garbage_time: bool | None = None,
    classification: Classification | None = None,
) -> list[TeamGamePredictedPointsAdded]:
    """Return validated team-game PPA through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :param classification: Optional classification selector.
    :return: Validated team-game PPA rows in source order.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        exclude_garbage_time=exclude_garbage_time,
        classification=classification,
    )


@source(operation=PLAYER_GAME_PPA)
async def player_game_ppa(
    context: SourceContext[PlayerGamePredictedPointsAdded],
    *,
    year: int,
    week: int | None = None,
    season_type: SeasonType | None = None,
    team: str | None = None,
    position: str | None = None,
    player_id: int | None = None,
    threshold: int | None = None,
    exclude_garbage_time: bool | None = None,
) -> list[PlayerGamePredictedPointsAdded]:
    """Return validated player-game PPA through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Required season year.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param position: Optional position selector.
    :param player_id: Optional numeric athlete identifier.
    :param threshold: Optional minimum play threshold.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :return: Validated player-game PPA rows in source order.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        position=position,
        player_id=player_id,
        threshold=threshold,
        exclude_garbage_time=exclude_garbage_time,
    )


@source(operation=PLAYER_SEASON_PPA)
async def player_season_ppa(
    context: SourceContext[PlayerSeasonPredictedPointsAdded],
    *,
    year: int | None = None,
    conference: str | None = None,
    team: str | None = None,
    position: str | None = None,
    player_id: int | None = None,
    threshold: int | None = None,
    exclude_garbage_time: bool | None = None,
) -> list[PlayerSeasonPredictedPointsAdded]:
    """Return validated player-season PPA through the coordinator client.

    :param context: Engine-owned source execution context.
    :param year: Optional season year.
    :param conference: Optional conference selector.
    :param team: Optional team selector.
    :param position: Optional position selector.
    :param player_id: Optional numeric athlete identifier.
    :param threshold: Optional minimum play threshold.
    :param exclude_garbage_time: Optional upstream garbage-time policy.
    :return: Validated player-season PPA rows in source order.
    """
    return await context.retrieve(
        year=year,
        conference=conference,
        team=team,
        position=position,
        player_id=player_id,
        threshold=threshold,
        exclude_garbage_time=exclude_garbage_time,
    )


@source(operation=PLAY_WIN_PROBABILITIES)
async def play_win_probabilities(
    context: SourceContext[PlayWinProbability],
    *,
    game_id: int,
) -> list[PlayWinProbability]:
    """Return validated play probabilities through the coordinator client.

    :param context: Engine-owned source execution context.
    :param game_id: Required exact game identifier.
    :return: Validated play probabilities in source order.
    """
    return await context.retrieve(game_id=game_id)


__all__ = [
    "play_win_probabilities",
    "player_game_ppa",
    "player_season_ppa",
    "team_game_ppa",
    "team_season_ppa",
]
