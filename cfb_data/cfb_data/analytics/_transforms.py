"""Implement pure built-in transforms for curated analytical products."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from cfb_data.analytics._models import (
    BettingLineRow,
    CoachSeasonRow,
    DriveRow,
    GameResultState,
    GameSummary,
    PlayerGameStatRow,
    PlayerSeasonRow,
    PlayRow,
    PollRankingRow,
    RecruitingClassRow,
    RosterMembership,
    TeamGameRow,
    TeamSeasonRow,
)
from cfb_data.analytics.operations import normalize_text
from cfb_data.base.types import JSONValue
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.coaches.models.pydantic.responses import DetailedCoachSeason
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.errors import CFBDAnalyticsError
from cfb_data.games.models.pydantic.responses import (
    Game,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)
from cfb_data.plays.models.pydantic.responses import Play
from cfb_data.rankings.models.pydantic.responses import PollWeek
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
)
from cfb_data.teams.models.pydantic.responses import RosterPlayer


def game_summaries(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Preserve games while deriving result metrics conservatively."""
    del parameters, config
    rows: list[GameSummary] = []
    for game in _rows(inputs, "games", Game):
        has_scores = game.home_points is not None and game.away_points is not None
        margin: int | None = None
        total: int | None = None
        if (
            game.completed
            and game.home_points is not None
            and game.away_points is not None
        ):
            margin = game.home_points - game.away_points
            total = game.home_points + game.away_points
        winner_id: int | None = None
        loser_id: int | None = None
        if not game.completed:
            state = (
                GameResultState.scheduled
                if not has_scores
                else GameResultState.incomplete
            )
        elif not has_scores:
            state = GameResultState.incomplete
        elif margin == 0:
            state = GameResultState.tie
        else:
            state = GameResultState.completed
            if margin is not None and margin > 0:
                winner_id, loser_id = game.home_id, game.away_id
            else:
                winner_id, loser_id = game.away_id, game.home_id
        rows.append(
            GameSummary.model_validate(
                {
                    **game.model_dump(mode="python"),
                    "result_state": state,
                    "home_margin": margin,
                    "total_points": total,
                    "winner_id": winner_id,
                    "loser_id": loser_id,
                }
            )
        )
    return rows


def team_games(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Normalize each game into exactly two team-perspective rows."""
    del parameters, config
    summaries = _rows(inputs, "summaries", GameSummary)
    stat_games = _rows(inputs, "team_stats", TeamGameStats)
    stats_by_key: dict[tuple[int, int], list[object]] = {}
    for stat_game in stat_games:
        for stat_team in stat_game.teams:
            key = (stat_game.id, stat_team.team_id)
            if key in stats_by_key:
                raise CFBDAnalyticsError("Duplicate team-game statistics")
            stats_by_key[key] = list(stat_team.stats)

    output: list[TeamGameRow] = []
    for game in summaries:
        perspectives = (
            (
                game.home_id,
                game.home_team,
                game.home_conference,
                game.home_classification,
                "home",
                game.away_id,
                game.away_team,
                game.home_points,
                game.away_points,
            ),
            (
                game.away_id,
                game.away_team,
                game.away_conference,
                game.away_classification,
                "away",
                game.home_id,
                game.home_team,
                game.away_points,
                game.home_points,
            ),
        )
        for (
            team_id,
            perspective_team,
            conference,
            classification,
            side,
            opponent_id,
            opponent,
            points_for,
            points_against,
        ) in perspectives:
            differential = (
                points_for - points_against
                if game.completed
                and points_for is not None
                and points_against is not None
                else None
            )
            result = None
            if differential is not None:
                result = "W" if differential > 0 else "L" if differential < 0 else "T"
            output.append(
                TeamGameRow(
                    game_id=game.id,
                    season=game.season,
                    week=game.week,
                    season_type=game.season_type,
                    start_date=game.start_date,
                    team_id=team_id,
                    team=perspective_team,
                    conference=conference,
                    classification=classification,
                    home_away=side,
                    opponent_id=opponent_id,
                    opponent=opponent,
                    points_for=points_for,
                    points_against=points_against,
                    point_differential=differential,
                    result=result,
                    completed=game.completed,
                    stats=stats_by_key.get((game.id, team_id), []),
                )
            )
    return output


def player_game_stats(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Flatten game/team/category/type/athlete nesting in source order."""
    del parameters, config
    games = _rows(inputs, "games", Game)
    game_teams = {
        (game.id, normalize_text(game.home_team, casefold=True)): game.home_id
        for game in games
    }
    game_teams.update(
        {
            (game.id, normalize_text(game.away_team, casefold=True)): game.away_id
            for game in games
        }
    )
    output: list[PlayerGameStatRow] = []
    seen: set[tuple[int, int, str, str, str]] = set()
    for game in _rows(inputs, "player_stats", PlayerGameStats):
        for team in game.teams:
            team_key = (game.id, normalize_text(team.team, casefold=True))
            if team_key not in game_teams:
                raise CFBDAnalyticsError("Player-stat team cannot be resolved in game")
            team_id = game_teams[team_key]
            for category in team.categories:
                for stat_type in category.types:
                    for athlete in stat_type.athletes:
                        key = (
                            game.id,
                            team_id,
                            athlete.id,
                            category.name,
                            stat_type.name,
                        )
                        if key in seen:
                            raise CFBDAnalyticsError(
                                "Duplicate player-game statistic candidate key"
                            )
                        seen.add(key)
                        output.append(
                            PlayerGameStatRow(
                                game_id=game.id,
                                team_id=team_id,
                                team=team.team,
                                home_away=team.home_away,
                                conference=team.conference,
                                team_points=team.points,
                                athlete_id=athlete.id,
                                athlete_name=athlete.name,
                                category=category.name,
                                stat_type=stat_type.name,
                                stat=athlete.stat,
                            )
                        )
    return output


def drives(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Add explicit drive clock and score arithmetic."""
    del config
    selected_game_id = getattr(parameters, "game_id", None)
    output: list[DriveRow] = []
    for row in _rows(inputs, "drives", Drive):
        if selected_game_id is not None and row.game_id != selected_game_id:
            continue
        output.append(
            DriveRow.model_validate(
                {
                    **row.model_dump(mode="python"),
                    "start_clock_seconds": _clock_seconds(
                        row.start_time.minutes, row.start_time.seconds
                    ),
                    "end_clock_seconds": _clock_seconds(
                        row.end_time.minutes, row.end_time.seconds
                    ),
                    "elapsed_seconds": _clock_seconds(
                        row.elapsed.minutes, row.elapsed.seconds
                    ),
                    "points_gained": row.end_offense_score - row.start_offense_score,
                    "end_score_differential": (
                        row.end_offense_score - row.end_defense_score
                    ),
                }
            )
        )
    return output


def plays(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Add explicit play clock and team-perspective arithmetic."""
    del config
    selected_game_id = getattr(parameters, "game_id", None)
    return [
        PlayRow.model_validate(
            {
                **row.model_dump(mode="python"),
                "clock_seconds": _clock_seconds(row.clock.minutes, row.clock.seconds),
                "score_differential": row.offense_score - row.defense_score,
                "is_home_offense": normalize_text(row.offense, casefold=True)
                == normalize_text(row.home, casefold=True),
            }
        )
        for row in _rows(inputs, "plays", Play)
        if selected_game_id is None or row.game_id == selected_game_id
    ]


def rosters(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Attach the requested season to roster membership rows."""
    del config
    season = getattr(parameters, "season", None)
    if not isinstance(season, int) or isinstance(season, bool):
        raise CFBDAnalyticsError("Roster parameters do not contain a season")
    return [
        RosterMembership.model_validate(
            {**row.model_dump(mode="python"), "season": season}
        )
        for row in _rows(inputs, "roster", RosterPlayer)
    ]


def team_seasons(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Compose record-established team seasons without changing their universe."""
    del parameters, config
    stats: dict[tuple[int, str], list[TeamStat]] = {}
    for stat in _rows(inputs, "stats", TeamStat):
        stats.setdefault(
            (stat.season, normalize_text(stat.team, casefold=True)), []
        ).append(stat)
    advanced: dict[tuple[int, str], AdvancedSeasonStat] = {}
    for row in _rows(inputs, "advanced", AdvancedSeasonStat):
        key = (row.season, normalize_text(row.team, casefold=True))
        if key in advanced:
            raise CFBDAnalyticsError("Duplicate advanced team-season record")
        advanced[key] = row
    return [
        TeamSeasonRow.model_validate(
            {
                **record.model_dump(mode="python"),
                "stats": stats.get(
                    (record.year, normalize_text(record.team, casefold=True)), []
                ),
                "advanced": advanced.get(
                    (record.year, normalize_text(record.team, casefold=True))
                ),
            }
        )
        for record in _rows(inputs, "records", TeamRecords)
    ]


def player_seasons(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Union roster and statistic evidence at athlete-team-season grain."""
    del config
    season = getattr(parameters, "season", None)
    if not isinstance(season, int) or isinstance(season, bool):
        raise CFBDAnalyticsError("Player-season parameters have no season")
    roster_by_key: dict[tuple[str, str], RosterPlayer] = {}
    for roster_row in _rows(inputs, "roster", RosterPlayer):
        key = (normalize_text(roster_row.team, casefold=True), roster_row.id)
        if key in roster_by_key:
            raise CFBDAnalyticsError("Duplicate roster membership")
        roster_by_key[key] = roster_row
    stats_by_key: dict[tuple[str, str], list[PlayerStat]] = {}
    for stat_row in _rows(inputs, "stats", PlayerStat):
        key = (normalize_text(stat_row.team, casefold=True), stat_row.player_id)
        stats_by_key.setdefault(key, []).append(stat_row)
    keys = list(roster_by_key)
    keys.extend(key for key in stats_by_key if key not in roster_by_key)
    output: list[PlayerSeasonRow] = []
    for key in keys:
        roster = roster_by_key.get(key)
        stats = stats_by_key.get(key, [])
        first_stat = stats[0] if stats else None
        if roster is None and first_stat is None:
            raise AssertionError("Union key must have roster or statistic evidence")
        position: str | None
        if roster is None:
            assert first_stat is not None
            team = first_stat.team
            athlete_id = first_stat.player_id
            athlete_name = first_stat.player
            position = first_stat.position
        else:
            team = roster.team
            athlete_id = roster.id
            athlete_name = " ".join((roster.first_name, roster.last_name)).strip()
            position = roster.position
        output.append(
            PlayerSeasonRow(
                season=season,
                team=team,
                athlete_id=athlete_id,
                athlete_name=athlete_name,
                position=position,
                conference=first_stat.conference if first_stat is not None else None,
                roster=roster,
                stats=stats,
                roster_present=roster is not None,
                stats_present=bool(stats),
            )
        )
    return output


def poll_rankings(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Flatten poll weeks while preserving poll and rank ordinals."""
    del config
    selected_team = getattr(parameters, "team", None)
    output: list[PollRankingRow] = []
    for week in _rows(inputs, "rankings", PollWeek):
        for poll_ordinal, poll in enumerate(week.polls):
            for rank_ordinal, rank in enumerate(poll.ranks):
                if selected_team is not None and normalize_text(
                    rank.school, casefold=True
                ) != normalize_text(selected_team, casefold=True):
                    continue
                output.append(
                    PollRankingRow(
                        season=week.season,
                        season_type=week.season_type,
                        week=week.week,
                        poll=poll.poll,
                        poll_ordinal=poll_ordinal,
                        is_final=poll.is_final,
                        rank_ordinal=rank_ordinal,
                        rank=rank.rank,
                        team_id=rank.team_id,
                        school=rank.school,
                        conference=rank.conference,
                        first_place_votes=rank.first_place_votes,
                        points=rank.points,
                    )
                )
    return output


def betting_lines(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Flatten provider quotes without selecting or relabeling a quote."""
    del parameters, config
    output: list[BettingLineRow] = []
    for game in _rows(inputs, "lines", BettingGame):
        for ordinal, quote in enumerate(game.lines):
            output.append(
                BettingLineRow(
                    game_id=game.id,
                    season=game.season,
                    season_type=game.season_type,
                    week=game.week,
                    start_date=game.start_date,
                    home_team_id=game.home_team_id,
                    home_team=game.home_team,
                    home_score=game.home_score,
                    away_team_id=game.away_team_id,
                    away_team=game.away_team,
                    away_score=game.away_score,
                    source_ordinal=ordinal,
                    provider=quote.provider,
                    quote=quote,
                )
            )
    return output


def recruiting_classes(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Union ranked and committed teams while keeping uncommitted recruits separate."""
    del config
    class_year = getattr(parameters, "class_year", None)
    if not isinstance(class_year, int) or isinstance(class_year, bool):
        raise CFBDAnalyticsError("Recruiting parameters have no class year")
    rankings: dict[str, TeamRecruitingRanking] = {}
    display_names: dict[str, str] = {}
    for row in _rows(inputs, "rankings", TeamRecruitingRanking):
        key = normalize_text(row.team, casefold=True)
        if key in rankings:
            raise CFBDAnalyticsError("Duplicate recruiting team ranking")
        rankings[key] = row
        display_names[key] = row.team
    recruits: dict[str, list[Recruit]] = {}
    uncommitted: list[Recruit] = []
    for recruit in _rows(inputs, "recruits", Recruit):
        if recruit.committed_to is None:
            uncommitted.append(recruit)
            continue
        key = normalize_text(recruit.committed_to, casefold=True)
        display_names.setdefault(key, recruit.committed_to)
        recruits.setdefault(key, []).append(recruit)
    keys = list(rankings)
    keys.extend(key for key in recruits if key not in rankings)
    output: list[RecruitingClassRow] = []
    for key in keys:
        ranking = rankings.get(key)
        team_recruits = recruits.get(key, [])
        output.append(
            RecruitingClassRow(
                class_year=class_year,
                source_team=display_names[key],
                rank=ranking.rank if ranking is not None else None,
                points=ranking.points if ranking is not None else None,
                recruits=team_recruits,
                committed_recruits=len(team_recruits),
                uncommitted_recruits=0,
            )
        )
    if uncommitted:
        output.append(
            RecruitingClassRow(
                class_year=class_year,
                source_team="__uncommitted__",
                rank=None,
                points=None,
                recruits=uncommitted,
                committed_recruits=0,
                uncommitted_recruits=len(uncommitted),
            )
        )
    return output


def coach_seasons(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Apply a stable analytics contract to detailed coach seasons."""
    del parameters, config
    return [
        CoachSeasonRow.model_validate(row.model_dump(mode="python"))
        for row in _rows(inputs, "coach_seasons", DetailedCoachSeason)
    ]


def _rows[RowT: BaseModel](
    inputs: Mapping[str, Sequence[BaseModel]],
    name: str,
    row_type: type[RowT],
) -> list[RowT]:
    try:
        values = inputs[name]
    except KeyError as exc:
        raise CFBDAnalyticsError(f"Transform input is missing: {name}") from exc
    rows: list[RowT] = []
    for value in values:
        if not isinstance(value, row_type):
            raise CFBDAnalyticsError("Transform input row has the wrong contract")
        rows.append(value)
    return rows


def _clock_seconds(minutes: int | None, seconds: int | None) -> int | None:
    if minutes is None or seconds is None:
        return None
    return minutes * 60 + seconds


__all__ = [
    "betting_lines",
    "coach_seasons",
    "drives",
    "game_summaries",
    "player_game_stats",
    "player_seasons",
    "plays",
    "poll_rankings",
    "recruiting_classes",
    "rosters",
    "team_games",
    "team_seasons",
]
