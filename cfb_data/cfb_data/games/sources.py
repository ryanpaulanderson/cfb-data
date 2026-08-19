"""Expose public validated Games sources for modular recipes."""

from __future__ import annotations

from typing import Literal

from cfb_data.analytics import SourceContext, source
from cfb_data.enums import Classification, PlayoffCompetition, PlayoffRound, SeasonType
from cfb_data.games._operations import GAMES_LIST, GAMES_TEAM_STATS
from cfb_data.games.models.pydantic.responses import Game, TeamGameStats

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


__all__ = ["games", "team_game_stats"]
