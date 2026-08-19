"""Compose the first-party single-game analysis workflow.

The workflow resolves the season, week, and one participating team from the
validated game summary, then binds those scalars into the smallest historical
drive and play partitions supported by CFBD. Its graph is fixed before I/O;
only the exact downstream selectors are deferred.
"""

from __future__ import annotations

from typing import TypedDict

from cfb_data.analytics import require_one, value, workflow

from cfb_data_recipes.betting_lines import BettingLine, betting_lines
from cfb_data_recipes.drives import DriveRow, drives
from cfb_data_recipes.game_summaries import GameSummary, game_summaries
from cfb_data_recipes.player_game_stats import PlayerGameStat, player_game_stats
from cfb_data_recipes.plays import PlayRow, plays
from cfb_data_recipes.team_games import TeamGame, team_games


class SingleGameAnalysisRefs(TypedDict):
    """Describe the workflow's six explicitly named tabular outputs."""

    game_summaries: list[GameSummary]
    team_games: list[TeamGame]
    player_game_stats: list[PlayerGameStat]
    drives: list[DriveRow]
    plays: list[PlayRow]
    betting_lines: list[BettingLine]


@workflow(id="cfbd.single_game_analysis", revision=1)
def single_game_analysis(
    *,
    game_id: int,
    include_team_stats: bool = False,
    include_win_probability: bool = False,
) -> SingleGameAnalysisRefs:
    """Build the core named products for one exact game.

    :param game_id: Stable CFBD game identifier.
    :param include_team_stats: Request conventional team-game statistics.
    :param include_win_probability: Request exact play win probabilities.
    :return: Typed references to six named dataset outputs.
    """
    summaries = game_summaries(game_id=game_id)
    context = require_one(summaries)
    season = value(context, path=("season",), expected_type=int)
    week = value(context, path=("week",), expected_type=int)
    team = value(context, path=("home_team",), expected_type=str)
    return {
        "game_summaries": summaries,
        "team_games": team_games(
            game_id=game_id,
            include_team_stats=include_team_stats,
        ),
        "player_game_stats": player_game_stats(game_id=game_id),
        "drives": drives(
            year=season,
            week=week,
            team=team,
            game_id=game_id,
        ),
        "plays": plays(
            year=season,
            week=week,
            team=team,
            game_id=game_id,
            include_win_probability=include_win_probability,
        ),
        "betting_lines": betting_lines(game_id=game_id),
    }


__all__ = ["SingleGameAnalysisRefs", "single_game_analysis"]
