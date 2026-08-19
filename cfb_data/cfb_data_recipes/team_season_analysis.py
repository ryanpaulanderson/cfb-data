"""Compose the first-party team-season analysis workflow.

The workflow imports and calls ordinary public dataset recipes. It exposes
seven explicit named outputs and performs no hidden flattening or privileged
registration. Repeated endpoint requests introduced by nested composition are
deduplicated by the coordinator.
"""

from __future__ import annotations

from typing import TypedDict

from cfb_data.analytics import workflow
from cfb_data.enums import Classification, SeasonType

from cfb_data_recipes.coach_seasons import CoachSeason, coach_seasons
from cfb_data_recipes.game_summaries import GameSummary, game_summaries
from cfb_data_recipes.player_game_stats import PlayerGameStat, player_game_stats
from cfb_data_recipes.player_seasons import PlayerSeason, player_seasons
from cfb_data_recipes.rosters import RosterMembership, rosters
from cfb_data_recipes.team_games import TeamGame, team_games
from cfb_data_recipes.team_seasons import TeamSeason, team_seasons


class TeamSeasonAnalysisRefs(TypedDict):
    """Describe the workflow's seven explicitly named tabular outputs."""

    game_summaries: list[GameSummary]
    team_games: list[TeamGame]
    player_game_stats: list[PlayerGameStat]
    rosters: list[RosterMembership]
    team_seasons: list[TeamSeason]
    player_seasons: list[PlayerSeason]
    coach_seasons: list[CoachSeason]


@workflow(id="cfbd.team_season_analysis", revision=1)
def team_season_analysis(
    *,
    season: int,
    team: str,
    season_type: SeasonType | None = None,
    classification: Classification | None = None,
) -> TeamSeasonAnalysisRefs:
    """Build the core named products for one team season.

    :param season: Required season shared by every output.
    :param team: Required team selector shared by every output.
    :param season_type: Optional game and player-stat season phase.
    :param classification: Optional roster and source classification.
    :return: Typed references to seven named dataset outputs.
    """
    return {
        "game_summaries": game_summaries(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
        ),
        "team_games": team_games(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
        ),
        "player_game_stats": player_game_stats(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
        ),
        "rosters": rosters(
            season=season,
            team=team,
            classification=classification,
        ),
        "team_seasons": team_seasons(
            season=season,
            team=team,
            classification=classification,
        ),
        "player_seasons": player_seasons(
            season=season,
            team=team,
            season_type=season_type,
            classification=classification,
        ),
        "coach_seasons": coach_seasons(year=season, team=team),
    }


__all__ = ["TeamSeasonAnalysisRefs", "team_season_analysis"]
