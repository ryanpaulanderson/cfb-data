"""Compose the first-party team-season analysis workflow.

The workflow imports and calls ordinary public dataset recipes. It exposes
seven explicit named outputs and performs no hidden flattening or privileged
registration. Repeated endpoint requests introduced by nested composition are
deduplicated by the coordinator.
"""

from __future__ import annotations

from typing import TypedDict

from cfb_data.analytics import workflow
from cfb_data.enums import Classification, MediaType, SeasonType

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


@workflow(id="cfbd.team_season_analysis", revision=3)
def team_season_analysis(
    *,
    season: int,
    team: str,
    season_type: SeasonType | None = None,
    classification: Classification | None = None,
    include_team_game_stats: bool = False,
    include_game_media: bool = False,
    game_media_type: MediaType | None = None,
    include_game_weather: bool = False,
    include_advanced_game_stats: bool = False,
    include_game_havoc: bool = False,
    include_game_ppa: bool = False,
    include_team_season_ppa: bool = False,
    include_team_talent: bool = False,
    include_team_ats: bool = False,
    include_returning_production: bool = False,
    include_core_rating: bool = False,
    include_sp_rating: bool = False,
    include_srs_rating: bool = False,
    include_elo_rating: bool = False,
    team_elo_week: int | None = None,
    team_elo_season_type: SeasonType | None = None,
    include_fpi_rating: bool = False,
    include_adjusted_team_metrics: bool = False,
    include_player_usage: bool = False,
    include_player_ppa: bool = False,
    include_player_success: bool = False,
    include_passing_wepa: bool = False,
    include_rushing_wepa: bool = False,
    include_kicker_paar: bool = False,
    include_coach_tenure: bool = False,
    exclude_garbage_time: bool | None = None,
) -> TeamSeasonAnalysisRefs:
    """Build the core named products for one team season.

    :param season: Required season shared by every output.
    :param team: Required team selector shared by every output.
    :param season_type: Optional game and player-stat season phase.
    :param classification: Optional roster and source classification.
    :param include_team_game_stats: Request conventional team-game statistics.
    :param include_game_media: Request game-summary broadcast outlets.
    :param game_media_type: Optional broadcast-medium selector.
    :param include_game_weather: Request Tier 1 game-summary weather.
    :param include_advanced_game_stats: Request advanced team-game statistics.
    :param include_game_havoc: Request team-game havoc statistics.
    :param include_game_ppa: Request team-game PPA metrics.
    :param include_team_season_ppa: Request team-season PPA metrics.
    :param include_team_talent: Request team-talent composites.
    :param include_team_ats: Request team against-the-spread records.
    :param include_returning_production: Request returning-production metrics.
    :param include_core_rating: Request the team CORE rating.
    :param include_sp_rating: Request the team SP+ rating.
    :param include_srs_rating: Request the team SRS result.
    :param include_elo_rating: Request the team Elo result.
    :param team_elo_week: Optional week cutoff for requested team Elo.
    :param team_elo_season_type: Optional season phase for requested team Elo.
    :param include_fpi_rating: Request the team FPI result.
    :param include_adjusted_team_metrics: Request adjusted team metrics.
    :param include_player_usage: Request player-season usage metrics.
    :param include_player_ppa: Request player-season PPA metrics.
    :param include_player_success: Request player success-rate metrics.
    :param include_passing_wepa: Request adjusted player passing EPA.
    :param include_rushing_wepa: Request adjusted player rushing EPA.
    :param include_kicker_paar: Request kicker points above replacement.
    :param include_coach_tenure: Request continuous coach-tenure context.
    :param exclude_garbage_time: Optional source policy for supported metrics.
    :return: Typed references to seven named dataset outputs.
    """
    return {
        "game_summaries": game_summaries(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
            include_media=include_game_media,
            media_type=game_media_type,
            include_weather=include_game_weather,
        ),
        "team_games": team_games(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
            include_team_stats=include_team_game_stats,
            include_advanced_stats=include_advanced_game_stats,
            include_havoc=include_game_havoc,
            include_ppa=include_game_ppa,
            exclude_garbage_time=exclude_garbage_time,
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
            exclude_garbage_time=exclude_garbage_time,
            include_ppa=include_team_season_ppa,
            include_talent=include_team_talent,
            include_ats=include_team_ats,
            include_returning_production=include_returning_production,
            include_core_rating=include_core_rating,
            include_sp_rating=include_sp_rating,
            include_srs_rating=include_srs_rating,
            include_elo_rating=include_elo_rating,
            elo_week=team_elo_week,
            elo_season_type=team_elo_season_type,
            include_fpi_rating=include_fpi_rating,
            include_adjusted_metrics=include_adjusted_team_metrics,
        ),
        "player_seasons": player_seasons(
            season=season,
            team=team,
            season_type=season_type,
            classification=classification,
            exclude_garbage_time=exclude_garbage_time,
            include_usage=include_player_usage,
            include_ppa=include_player_ppa,
            include_success=include_player_success,
            include_passing_wepa=include_passing_wepa,
            include_rushing_wepa=include_rushing_wepa,
            include_kicker_paar=include_kicker_paar,
        ),
        "coach_seasons": coach_seasons(
            year=season,
            team=team,
            include_tenure=include_coach_tenure,
        ),
    }


__all__ = ["TeamSeasonAnalysisRefs", "team_season_analysis"]
