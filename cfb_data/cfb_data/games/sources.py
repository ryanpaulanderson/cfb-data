"""Expose public validated Games sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games._operations import (
    ADVANCED_BOX_SCORE,
    GAMES_LIST,
    GAMES_PLAYER_STATS,
    GAMES_TEAM_STATS,
    TEAM_RECORDS,
)
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    Game,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)

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
type _CompetitionArgument = PlayoffCompetition | Literal["cfp"]
type _RoundArgument = (
    PlayoffRound | Literal["first_round", "quarterfinal", "semifinal", "championship"]
)


@source(operation=ADVANCED_BOX_SCORE)
async def advanced_box_score(
    context: SourceContext[AdvancedBoxScore],
    *,
    game_id: int,
) -> list[AdvancedBoxScore]:
    """Return one validated advanced box score as an analytical row list.

    :param context: Engine-owned source execution context.
    :param game_id: Required exact game identifier.
    :return: One source-faithful advanced box score.
    """
    return await context.retrieve(game_id=game_id)


@source(operation=GAMES_LIST)
async def games(
    context: SourceContext[Game],
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    team: str | None = None,
    home: str | None = None,
    away: str | None = None,
    conference: str | None = None,
    classification: _ClassificationArgument | None = None,
    game_id: int | None = None,
    competition: _CompetitionArgument | None = None,
    round: _RoundArgument | None = None,
) -> list[Game]:
    """Return validated games through the coordinator-owned client.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when game ID is absent.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional participating-team selector.
    :param home: Optional home-team selector.
    :param away: Optional away-team selector.
    :param conference: Optional participating-conference selector.
    :param classification: Optional classification selector.
    :param game_id: Optional exact game identifier.
    :param competition: Optional playoff competition.
    :param round: Optional playoff round.
    :return: Validated source rows in upstream order.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        home=home,
        away=away,
        conference=conference,
        classification=classification,
        game_id=game_id,
        competition=competition,
        round=round,
    )


@source(operation=GAMES_TEAM_STATS)
async def team_game_stats(
    context: SourceContext[TeamGameStats],
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    team: str | None = None,
    conference: str | None = None,
    game_id: int | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[TeamGameStats]:
    """Return validated conventional team-game statistics.

    :param context: Engine-owned source execution context.
    :param year: Season year used for grouped retrieval.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param game_id: Optional exact game identifier.
    :param classification: Optional classification selector.
    :return: Validated game-scoped nested team statistics.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        game_id=game_id,
        classification=classification,
    )


@source(operation=GAMES_PLAYER_STATS)
async def player_game_stats(
    context: SourceContext[PlayerGameStats],
    *,
    year: int | None = None,
    week: int | None = None,
    season_type: _SeasonTypeArgument | None = None,
    team: str | None = None,
    conference: str | None = None,
    category: str | None = None,
    game_id: int | None = None,
    classification: _ClassificationArgument | None = None,
) -> list[PlayerGameStats]:
    """Return validated nested player-game statistics.

    :param context: Engine-owned source execution context.
    :param year: Season year used for grouped retrieval.
    :param week: Optional season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param category: Optional source statistic-category selector.
    :param game_id: Optional exact game identifier.
    :param classification: Optional classification selector.
    :return: Validated game/team/category/type/athlete nesting.
    """
    return await context.retrieve(
        year=year,
        week=week,
        season_type=season_type,
        team=team,
        conference=conference,
        category=category,
        game_id=game_id,
        classification=classification,
    )


@source(operation=TEAM_RECORDS)
async def team_records(
    context: SourceContext[TeamRecords],
    *,
    year: int | None = None,
    team: str | None = None,
    conference: str | None = None,
) -> list[TeamRecords]:
    """Return validated team-season records.

    :param context: Engine-owned source execution context.
    :param year: Optional season year when team is absent.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :return: Validated team-season records in source order.
    """
    return await context.retrieve(year=year, team=team, conference=conference)


__all__ = [
    "advanced_box_score",
    "games",
    "player_game_stats",
    "team_game_stats",
    "team_records",
]
