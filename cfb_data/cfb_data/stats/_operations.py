"""Own typed endpoint operations for the Stats domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.stats.models.pydantic.requests import (
    AdvancedGameStatsRequest,
    AdvancedSeasonStatsRequest,
    GameHavocRequest,
    PlayerGameSuccessRequest,
    PlayerSeasonStatsRequest,
    PlayerSeasonSuccessRequest,
    TeamSeasonStatsRequest,
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

PLAYER_SEASON_SUCCESS = _ManyEndpointOperation(
    id="cfbd.stats.player_season_success",
    revision=1,
    endpoint="/stats/player/success",
    request_type=PlayerSeasonSuccessRequest,
    response_adapter=TypeAdapter(list[PlayerSeasonSuccessRate]),
    row_model=PlayerSeasonSuccessRate,
    access_tier="free",
)

PLAYER_GAME_SUCCESS = _ManyEndpointOperation(
    id="cfbd.stats.player_game_success",
    revision=1,
    endpoint="/stats/player/success/game",
    request_type=PlayerGameSuccessRequest,
    response_adapter=TypeAdapter(list[PlayerGameSuccessRate]),
    row_model=PlayerGameSuccessRate,
    access_tier="free",
)

PLAYER_SEASON_STATS = _ManyEndpointOperation(
    id="cfbd.stats.player_season",
    revision=1,
    endpoint="/stats/player/season",
    request_type=PlayerSeasonStatsRequest,
    response_adapter=TypeAdapter(list[PlayerStat]),
    row_model=PlayerStat,
    access_tier="free",
)

TEAM_SEASON_STATS = _ManyEndpointOperation(
    id="cfbd.stats.team_season",
    revision=1,
    endpoint="/stats/season",
    request_type=TeamSeasonStatsRequest,
    response_adapter=TypeAdapter(list[TeamStat]),
    row_model=TeamStat,
    access_tier="free",
)

ADVANCED_SEASON_STATS = _ManyEndpointOperation(
    id="cfbd.stats.advanced_season",
    revision=1,
    endpoint="/stats/season/advanced",
    request_type=AdvancedSeasonStatsRequest,
    response_adapter=TypeAdapter(list[AdvancedSeasonStat]),
    row_model=AdvancedSeasonStat,
    access_tier="free",
)

ADVANCED_GAME_STATS = _ManyEndpointOperation(
    id="cfbd.stats.advanced_game",
    revision=1,
    endpoint="/stats/game/advanced",
    request_type=AdvancedGameStatsRequest,
    response_adapter=TypeAdapter(list[AdvancedGameStat]),
    row_model=AdvancedGameStat,
    access_tier="free",
)

GAME_HAVOC_STATS = _ManyEndpointOperation(
    id="cfbd.stats.game_havoc",
    revision=1,
    endpoint="/stats/game/havoc",
    request_type=GameHavocRequest,
    response_adapter=TypeAdapter(list[GameHavocStats]),
    row_model=GameHavocStats,
    access_tier="free",
)
