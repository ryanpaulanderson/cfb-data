"""Compose the first-party bounded program-history workflow.

The season range is validated and expanded entirely during graph compilation.
No source response can add nodes. Each season calls the same independent public
dataset recipes an external analyst would use, and small coordinator-local
concatenation steps preserve their already validated rows and ordering.
"""

from __future__ import annotations

from typing import TypedDict

from cfb_data.analytics import step, workflow
from cfb_data.enums import (
    Classification,
    MediaType,
    RecruitClassification,
    SeasonType,
)

from cfb_data_recipes.coach_seasons import CoachSeason, coach_seasons
from cfb_data_recipes.game_summaries import GameSummary, game_summaries
from cfb_data_recipes.poll_rankings import PollRanking, poll_rankings
from cfb_data_recipes.recruiting_classes import RecruitingClass, recruiting_classes
from cfb_data_recipes.team_games import TeamGame, team_games
from cfb_data_recipes.team_seasons import TeamSeason, team_seasons

_MAX_SEASONS = 50


class ProgramHistoryRefs(TypedDict):
    """Describe the workflow's six explicitly named tabular outputs."""

    game_summaries: list[GameSummary]
    team_games: list[TeamGame]
    team_seasons: list[TeamSeason]
    recruiting_classes: list[RecruitingClass]
    coach_seasons: list[CoachSeason]
    poll_rankings: list[PollRanking]


@step(
    id="cfbd.program_history.concatenate_game_summaries",
    revision=1,
    output=GameSummary,
    dask=False,
)
def _concatenate_game_summaries(
    groups: tuple[list[GameSummary], ...],
) -> list[GameSummary]:
    """Concatenate season-ordered game-summary partitions."""
    return _concatenate(groups)


@step(
    id="cfbd.program_history.concatenate_team_games",
    revision=1,
    output=TeamGame,
    dask=False,
)
def _concatenate_team_games(
    groups: tuple[list[TeamGame], ...],
) -> list[TeamGame]:
    """Concatenate season-ordered team-game partitions."""
    return _concatenate(groups)


@step(
    id="cfbd.program_history.concatenate_team_seasons",
    revision=1,
    output=TeamSeason,
    dask=False,
)
def _concatenate_team_seasons(
    groups: tuple[list[TeamSeason], ...],
) -> list[TeamSeason]:
    """Concatenate season-ordered team-season partitions."""
    return _concatenate(groups)


@step(
    id="cfbd.program_history.concatenate_recruiting_classes",
    revision=1,
    output=RecruitingClass,
    dask=False,
)
def _concatenate_recruiting_classes(
    groups: tuple[list[RecruitingClass], ...],
) -> list[RecruitingClass]:
    """Concatenate year-ordered recruiting-class partitions."""
    return _concatenate(groups)


@step(
    id="cfbd.program_history.concatenate_poll_rankings",
    revision=1,
    output=PollRanking,
    dask=False,
)
def _concatenate_poll_rankings(
    groups: tuple[list[PollRanking], ...],
) -> list[PollRanking]:
    """Concatenate season-ordered poll-ranking partitions."""
    return _concatenate(groups)


@workflow(id="cfbd.program_history", revision=2)
def program_history(
    *,
    team: str,
    start_season: int,
    end_season: int,
    season_type: SeasonType | None = None,
    classification: Classification | None = None,
    recruit_classification: RecruitClassification | None = None,
    include_game_media: bool = False,
    game_media_type: MediaType | None = None,
    include_game_weather: bool = False,
    include_team_game_stats: bool = False,
    include_advanced_game_stats: bool = False,
    include_game_havoc: bool = False,
    include_game_ppa: bool = False,
    include_team_season_ppa: bool = False,
    include_coach_tenure: bool = False,
    exclude_garbage_time: bool | None = None,
) -> ProgramHistoryRefs:
    """Build bounded historical program products over an inclusive range.

    :param team: Required program selector.
    :param start_season: Inclusive first season.
    :param end_season: Inclusive final season.
    :param season_type: Optional game and ranking season phase.
    :param classification: Optional game and team-stat classification.
    :param recruit_classification: Optional recruit-type selector.
    :param include_game_media: Request game-summary broadcast outlets.
    :param game_media_type: Optional broadcast-medium selector.
    :param include_game_weather: Request Tier 1 game-summary weather.
    :param include_team_game_stats: Request conventional team-game statistics.
    :param include_advanced_game_stats: Request advanced team-game statistics.
    :param include_game_havoc: Request team-game havoc statistics.
    :param include_game_ppa: Request team-game PPA metrics.
    :param include_team_season_ppa: Request team-season PPA metrics.
    :param include_coach_tenure: Request continuous coach-tenure context.
    :param exclude_garbage_time: Optional source policy for supported metrics.
    :return: Typed references to six named historical outputs.
    :raises ValueError: If the range is reversed or exceeds the static bound.
    """
    seasons = _seasons(start_season, end_season)
    summaries = tuple(
        game_summaries.as_(f"game-summaries-{season}")(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
            include_media=include_game_media,
            media_type=game_media_type,
            include_weather=include_game_weather,
        )
        for season in seasons
    )
    perspectives = tuple(
        team_games.as_(f"team-games-{season}")(
            year=season,
            team=team,
            season_type=season_type,
            classification=classification,
            include_team_stats=include_team_game_stats,
            include_advanced_stats=include_advanced_game_stats,
            include_havoc=include_game_havoc,
            include_ppa=include_game_ppa,
            exclude_garbage_time=exclude_garbage_time,
        )
        for season in seasons
    )
    season_rows = tuple(
        team_seasons.as_(f"team-seasons-{season}")(
            season=season,
            team=team,
            classification=classification,
            exclude_garbage_time=exclude_garbage_time,
            include_ppa=include_team_season_ppa,
        )
        for season in seasons
    )
    recruiting = tuple(
        recruiting_classes.as_(f"recruiting-classes-{season}")(
            class_year=season,
            team=team,
            classification=recruit_classification,
        )
        for season in seasons
    )
    rankings = tuple(
        poll_rankings.as_(f"poll-rankings-{season}")(
            season=season,
            season_type=season_type,
        )
        for season in seasons
    )
    return {
        "game_summaries": _concatenate_game_summaries(summaries),
        "team_games": _concatenate_team_games(perspectives),
        "team_seasons": _concatenate_team_seasons(season_rows),
        "recruiting_classes": _concatenate_recruiting_classes(recruiting),
        "coach_seasons": coach_seasons(
            team=team,
            min_year=start_season,
            max_year=end_season,
            include_tenure=include_coach_tenure,
        ),
        "poll_rankings": _concatenate_poll_rankings(rankings),
    }


def _seasons(start_season: int, end_season: int) -> tuple[int, ...]:
    if end_season < start_season:
        raise ValueError("end_season must not precede start_season")
    count = end_season - start_season + 1
    if count > _MAX_SEASONS:
        raise ValueError(f"program_history supports at most {_MAX_SEASONS} seasons")
    return tuple(range(start_season, end_season + 1))


def _concatenate[RowT](groups: tuple[list[RowT], ...]) -> list[RowT]:
    return [row for group in groups for row in group]


__all__ = ["ProgramHistoryRefs", "program_history"]
