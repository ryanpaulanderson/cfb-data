"""Assemble immutable built-in dataset definitions and transforms."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from pydantic import BaseModel

from cfb_data.analytics import _transforms
from cfb_data.analytics._models import (
    BettingLineRow,
    BettingParams,
    CoachSeasonParams,
    CoachSeasonRow,
    DriveDatasetParams,
    DriveRow,
    GameDatasetParams,
    GameDetailParams,
    GameSummary,
    PlayDatasetParams,
    PlayerGameStatRow,
    PlayerSeasonParams,
    PlayerSeasonRow,
    PlayRow,
    PollRankingRow,
    RankingsParams,
    RecruitingClassRow,
    RecruitingParams,
    RosterDatasetParams,
    RosterMembership,
    TeamGameRow,
    TeamSeasonParams,
    TeamSeasonRow,
)
from cfb_data.analytics._sources import endpoint_operation
from cfb_data.analytics.contracts import (
    AnalyticsDefinition,
    ColumnMetadata,
    DatasetCatalog,
    DatasetDefinition,
    ParameterBinding,
    RegisteredTransform,
    SourceNode,
    TableContract,
    TransformBackend,
    TransformNode,
    TransformRegistry,
)


def _contract[RowT: BaseModel](
    id: str,
    row_model: type[RowT],
    *,
    grain: str,
    keys: tuple[str, ...],
    order_by: tuple[str, ...],
    partition_by: tuple[str, ...] = (),
    event_time: str | None = None,
    columns: Mapping[str, ColumnMetadata] | None = None,
) -> TableContract[RowT]:
    return TableContract(
        id=id,
        revision=1,
        row_model=row_model,
        grain=grain,
        keys=keys,
        order_by=order_by,
        partition_by=partition_by,
        event_time=event_time,
        columns=columns or {},
    )


GAME_SUMMARIES = _contract(
    "cfbd.dataset.game_summaries",
    GameSummary,
    grain="one selected game",
    keys=("id",),
    order_by=("season", "week", "start_date", "id"),
    partition_by=("season",),
    event_time="start_date",
    columns={
        "home_margin": ColumnMetadata(
            "Home points minus away points for a completed scored game.",
            "points",
            "measure",
        ),
        "total_points": ColumnMetadata(
            "Combined points for a completed scored game.", "points", "measure"
        ),
    },
)
TEAM_GAMES = _contract(
    "cfbd.dataset.team_games",
    TeamGameRow,
    grain="one team perspective in one selected game",
    keys=("game_id", "team_id"),
    order_by=("season", "week", "game_id", "team_id"),
    partition_by=("season",),
    event_time="start_date",
)
PLAYER_GAME_STATS = _contract(
    "cfbd.dataset.player_game_stats",
    PlayerGameStatRow,
    grain="one athlete display-stat observation in one game",
    keys=("game_id", "team_id", "athlete_id", "category", "stat_type"),
    order_by=("game_id", "team_id", "category", "stat_type", "athlete_id"),
    partition_by=("game_id",),
)
DRIVES = _contract(
    "cfbd.dataset.drives",
    DriveRow,
    grain="one game-scoped drive",
    keys=("game_id", "id"),
    order_by=("game_id", "drive_number", "id"),
    partition_by=("game_id",),
)
PLAYS = _contract(
    "cfbd.dataset.plays",
    PlayRow,
    grain="one game-scoped play",
    keys=("game_id", "id"),
    order_by=("game_id", "drive_number", "play_number", "id"),
    partition_by=("game_id",),
    event_time="wallclock",
)
ROSTERS = _contract(
    "cfbd.dataset.rosters",
    RosterMembership,
    grain="one athlete-team-season roster membership",
    keys=("season", "team", "id"),
    order_by=("season", "team", "id"),
    partition_by=("season",),
)
TEAM_SEASONS = _contract(
    "cfbd.dataset.team_seasons",
    TeamSeasonRow,
    grain="one team season established by the records source",
    keys=("year", "team_id"),
    order_by=("year", "team_id"),
    partition_by=("year",),
)
PLAYER_SEASONS = _contract(
    "cfbd.dataset.player_seasons",
    PlayerSeasonRow,
    grain="one athlete-team-season membership from roster/stat union",
    keys=("season", "team", "athlete_id"),
    order_by=("season", "team", "athlete_id"),
    partition_by=("season",),
)
POLL_RANKINGS = _contract(
    "cfbd.dataset.poll_rankings",
    PollRankingRow,
    grain="one team in one poll snapshot",
    keys=("season", "season_type", "week", "poll", "team_id"),
    order_by=("season", "season_type", "week", "poll_ordinal", "rank_ordinal"),
    partition_by=("season",),
)
BETTING_LINES = _contract(
    "cfbd.dataset.betting_lines",
    BettingLineRow,
    grain="one provider quote for one game",
    keys=("game_id", "provider", "source_ordinal"),
    order_by=("season", "week", "game_id", "source_ordinal"),
    partition_by=("season",),
    event_time="start_date",
)
RECRUITING_CLASSES = _contract(
    "cfbd.dataset.recruiting_classes",
    RecruitingClassRow,
    grain="one source team recruiting class",
    keys=("class_year", "source_team"),
    order_by=("class_year", "rank", "source_team"),
    partition_by=("class_year",),
)
COACH_SEASONS = _contract(
    "cfbd.dataset.coach_seasons",
    CoachSeasonRow,
    grain="one coach-team-season attribution",
    keys=("coach", "team", "year"),
    order_by=("year", "coach", "team"),
    partition_by=("year",),
)


def _binding(*names: str) -> Mapping[str, ParameterBinding]:
    return MappingProxyType({name: ParameterBinding(name) for name in names})


def _renamed_binding(**names: str) -> Mapping[str, ParameterBinding]:
    return MappingProxyType(
        {
            request_name: ParameterBinding(parameter)
            for request_name, parameter in names.items()
        }
    )


def _source(
    node_id: str,
    operation_id: str,
    bindings: Mapping[str, ParameterBinding],
) -> SourceNode:
    operation = endpoint_operation(operation_id)
    return SourceNode(
        id=node_id,
        operation_id=operation.id,
        operation_revision=operation.revision,
        bindings=bindings,
        output=operation.output,
    )


def _transform(
    node_id: str,
    operation_id: str,
    inputs: tuple[str, ...],
    output: TableContract[BaseModel],
) -> TransformNode:
    return TransformNode(
        id=node_id,
        operation_id=operation_id,
        operation_revision=1,
        inputs=inputs,
        output=output,
    )


_GAME_BINDINGS = _binding(
    "year", "week", "season_type", "team", "conference", "game_id"
)

GAME_SUMMARIES_DEFINITION = DatasetDefinition(
    id="cfbd.game_summaries",
    revision=1,
    parameter_model=GameDatasetParams,
    nodes=(
        _source("games", "cfbd.games.list", _GAME_BINDINGS),
        _transform(
            "result",
            "cfbd.transform.game_summaries",
            ("games",),
            cast(TableContract[BaseModel], GAME_SUMMARIES),
        ),
    ),
    output_node="result",
    output=GAME_SUMMARIES,
    description="Validated games with conservative completion and result semantics.",
)

TEAM_GAMES_DEFINITION = DatasetDefinition(
    id="cfbd.team_games",
    revision=1,
    parameter_model=GameDetailParams,
    nodes=(
        _source("games", "cfbd.games.list", _GAME_BINDINGS),
        _transform(
            "summaries",
            "cfbd.transform.game_summaries",
            ("games",),
            cast(TableContract[BaseModel], GAME_SUMMARIES),
        ),
        _source("team_stats", "cfbd.games.team_stats", _GAME_BINDINGS),
        _transform(
            "result",
            "cfbd.transform.team_games",
            ("summaries", "team_stats"),
            cast(TableContract[BaseModel], TEAM_GAMES),
        ),
    ),
    output_node="result",
    output=TEAM_GAMES,
    description="Two validated team-perspective rows for every selected game.",
)

PLAYER_GAME_STATS_DEFINITION = DatasetDefinition(
    id="cfbd.player_game_stats",
    revision=1,
    parameter_model=GameDetailParams,
    nodes=(
        _source("games", "cfbd.games.list", _GAME_BINDINGS),
        _source("player_stats", "cfbd.games.player_stats", _GAME_BINDINGS),
        _transform(
            "result",
            "cfbd.transform.player_game_stats",
            ("games", "player_stats"),
            cast(TableContract[BaseModel], PLAYER_GAME_STATS),
        ),
    ),
    output_node="result",
    output=PLAYER_GAME_STATS,
    description="Long-form player display statistics flattened from game nesting.",
)

DRIVES_DEFINITION = DatasetDefinition(
    id="cfbd.drives",
    revision=1,
    parameter_model=DriveDatasetParams,
    nodes=(
        _source(
            "drives",
            "cfbd.drives.list",
            _binding(
                "year",
                "week",
                "season_type",
                "team",
                "offense",
                "defense",
                "conference",
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.drives",
            ("drives",),
            cast(TableContract[BaseModel], DRIVES),
        ),
    ),
    output_node="result",
    output=DRIVES,
    description="Game-scoped drives with explicit clock and score arithmetic.",
)

PLAYS_DEFINITION = DatasetDefinition(
    id="cfbd.plays",
    revision=1,
    parameter_model=PlayDatasetParams,
    nodes=(
        _source(
            "plays",
            "cfbd.plays.list",
            _binding(
                "year",
                "week",
                "season_type",
                "team",
                "offense",
                "defense",
                "conference",
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.plays",
            ("plays",),
            cast(TableContract[BaseModel], PLAYS),
        ),
    ),
    output_node="result",
    output=PLAYS,
    description="Game-scoped plays with stable clock and score semantics.",
)

ROSTERS_DEFINITION = DatasetDefinition(
    id="cfbd.rosters",
    revision=1,
    parameter_model=RosterDatasetParams,
    nodes=(
        _source(
            "roster",
            "cfbd.teams.roster",
            _renamed_binding(
                year="season", team="team", classification="classification"
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.rosters",
            ("roster",),
            cast(TableContract[BaseModel], ROSTERS),
        ),
    ),
    output_node="result",
    output=ROSTERS,
    description="Roster memberships with requested season separated from class year.",
)

TEAM_SEASONS_DEFINITION = DatasetDefinition(
    id="cfbd.team_seasons",
    revision=1,
    parameter_model=TeamSeasonParams,
    nodes=(
        _source(
            "records",
            "cfbd.games.records",
            _renamed_binding(year="season", team="team", conference="conference"),
        ),
        _source(
            "stats",
            "cfbd.stats.team_season",
            _renamed_binding(year="season", team="team", conference="conference"),
        ),
        _source(
            "advanced",
            "cfbd.stats.team_season_advanced",
            _renamed_binding(year="season", team="team"),
        ),
        _transform(
            "result",
            "cfbd.transform.team_seasons",
            ("records", "stats", "advanced"),
            cast(TableContract[BaseModel], TEAM_SEASONS),
        ),
    ),
    output_node="result",
    output=TEAM_SEASONS,
    description="Record-established team seasons with common and advanced stats.",
)

PLAYER_SEASONS_DEFINITION = DatasetDefinition(
    id="cfbd.player_seasons",
    revision=1,
    parameter_model=PlayerSeasonParams,
    nodes=(
        _source(
            "roster",
            "cfbd.teams.roster",
            _renamed_binding(year="season", team="team"),
        ),
        _source(
            "stats",
            "cfbd.stats.player_season",
            _renamed_binding(
                year="season", team="team", conference="conference", category="category"
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.player_seasons",
            ("roster", "stats"),
            cast(TableContract[BaseModel], PLAYER_SEASONS),
        ),
    ),
    output_node="result",
    output=PLAYER_SEASONS,
    description="Unioned roster and player-stat season membership.",
)

POLL_RANKINGS_DEFINITION = DatasetDefinition(
    id="cfbd.poll_rankings",
    revision=1,
    parameter_model=RankingsParams,
    nodes=(
        _source(
            "rankings",
            "cfbd.rankings.list",
            _renamed_binding(
                year="season", season_type="season_type", week="week", poll="poll"
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.poll_rankings",
            ("rankings",),
            cast(TableContract[BaseModel], POLL_RANKINGS),
        ),
    ),
    output_node="result",
    output=POLL_RANKINGS,
    description="Long-form poll rankings preserving poll and rank ordinals.",
)

BETTING_LINES_DEFINITION = DatasetDefinition(
    id="cfbd.betting_lines",
    revision=1,
    parameter_model=BettingParams,
    nodes=(
        _source(
            "lines",
            "cfbd.betting.lines",
            _renamed_binding(
                game_id="game_id",
                year="season",
                season_type="season_type",
                week="week",
                team="team",
                provider="provider",
            ),
        ),
        _transform(
            "result",
            "cfbd.transform.betting_lines",
            ("lines",),
            cast(TableContract[BaseModel], BETTING_LINES),
        ),
    ),
    output_node="result",
    output=BETTING_LINES,
    description="Provider betting quotes without implicit quote selection.",
)

RECRUITING_CLASSES_DEFINITION = DatasetDefinition(
    id="cfbd.recruiting_classes",
    revision=1,
    parameter_model=RecruitingParams,
    nodes=(
        _source(
            "rankings",
            "cfbd.recruiting.team_rankings",
            _renamed_binding(year="class_year", team="team"),
        ),
        _source(
            "recruits",
            "cfbd.recruiting.players",
            _renamed_binding(year="class_year", team="team"),
        ),
        _transform(
            "result",
            "cfbd.transform.recruiting_classes",
            ("rankings", "recruits"),
            cast(TableContract[BaseModel], RECRUITING_CLASSES),
        ),
    ),
    output_node="result",
    output=RECRUITING_CLASSES,
    description="Ranked and commitment-backed recruiting classes with explicit uncommitted rows.",
)

COACH_SEASONS_DEFINITION = DatasetDefinition(
    id="cfbd.coach_seasons",
    revision=1,
    parameter_model=CoachSeasonParams,
    nodes=(
        _source(
            "coach_seasons",
            "cfbd.coaches.seasons",
            _binding("team", "year", "min_year", "max_year"),
        ),
        _transform(
            "result",
            "cfbd.transform.coach_seasons",
            ("coach_seasons",),
            cast(TableContract[BaseModel], COACH_SEASONS),
        ),
    ),
    output_node="result",
    output=COACH_SEASONS,
    description="Detailed coach-team-season records with attribution evidence.",
)


_TRANSFORMS = (
    RegisteredTransform(
        "cfbd.transform.game_summaries",
        1,
        TransformBackend.portable,
        True,
        _transforms.game_summaries,
    ),
    RegisteredTransform(
        "cfbd.transform.team_games",
        1,
        TransformBackend.portable,
        True,
        _transforms.team_games,
    ),
    RegisteredTransform(
        "cfbd.transform.player_game_stats",
        1,
        TransformBackend.portable,
        True,
        _transforms.player_game_stats,
    ),
    RegisteredTransform(
        "cfbd.transform.drives", 1, TransformBackend.portable, True, _transforms.drives
    ),
    RegisteredTransform(
        "cfbd.transform.plays", 1, TransformBackend.portable, True, _transforms.plays
    ),
    RegisteredTransform(
        "cfbd.transform.rosters",
        1,
        TransformBackend.portable,
        True,
        _transforms.rosters,
    ),
    RegisteredTransform(
        "cfbd.transform.team_seasons",
        1,
        TransformBackend.portable,
        True,
        _transforms.team_seasons,
    ),
    RegisteredTransform(
        "cfbd.transform.player_seasons",
        1,
        TransformBackend.portable,
        True,
        _transforms.player_seasons,
    ),
    RegisteredTransform(
        "cfbd.transform.poll_rankings",
        1,
        TransformBackend.portable,
        True,
        _transforms.poll_rankings,
    ),
    RegisteredTransform(
        "cfbd.transform.betting_lines",
        1,
        TransformBackend.portable,
        True,
        _transforms.betting_lines,
    ),
    RegisteredTransform(
        "cfbd.transform.recruiting_classes",
        1,
        TransformBackend.portable,
        True,
        _transforms.recruiting_classes,
    ),
    RegisteredTransform(
        "cfbd.transform.coach_seasons",
        1,
        TransformBackend.portable,
        True,
        _transforms.coach_seasons,
    ),
)

BUILTIN_TRANSFORMS = TransformRegistry({item.id: item for item in _TRANSFORMS})

_DEFINITIONS: tuple[AnalyticsDefinition, ...] = tuple(
    cast(
        AnalyticsDefinition,
        definition,
    )
    for definition in (
        GAME_SUMMARIES_DEFINITION,
        TEAM_GAMES_DEFINITION,
        PLAYER_GAME_STATS_DEFINITION,
        DRIVES_DEFINITION,
        PLAYS_DEFINITION,
        ROSTERS_DEFINITION,
        TEAM_SEASONS_DEFINITION,
        PLAYER_SEASONS_DEFINITION,
        POLL_RANKINGS_DEFINITION,
        BETTING_LINES_DEFINITION,
        RECRUITING_CLASSES_DEFINITION,
        COACH_SEASONS_DEFINITION,
    )
)

BUILTIN_CATALOG = DatasetCatalog({item.id: item for item in _DEFINITIONS})


__all__ = ["BUILTIN_CATALOG", "BUILTIN_TRANSFORMS"]
