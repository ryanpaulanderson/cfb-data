"""Own typed endpoint operations for the Games domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation, _OneEndpointOperation
from cfb_data.games.models.pydantic.requests import (
    AdvancedBoxScoreRequest,
    GamesRequest,
    PlayerGameStatsRequest,
    RecordsRequest,
    TeamGameStatsRequest,
)
from cfb_data.games.models.pydantic.responses import (
    AdvancedBoxScore,
    Game,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)

ADVANCED_BOX_SCORE = _OneEndpointOperation(
    id="cfbd.games.advanced_box_score",
    revision=1,
    endpoint="/game/box/advanced",
    request_type=AdvancedBoxScoreRequest,
    response_adapter=TypeAdapter(AdvancedBoxScore),
    row_model=AdvancedBoxScore,
    access_tier="free",
)

GAMES_LIST = _ManyEndpointOperation(
    id="cfbd.games.list",
    revision=1,
    endpoint="/games",
    request_type=GamesRequest,
    response_adapter=TypeAdapter(list[Game]),
    row_model=Game,
    access_tier="free",
)

GAMES_TEAM_STATS = _ManyEndpointOperation(
    id="cfbd.games.team_stats",
    revision=1,
    endpoint="/games/teams",
    request_type=TeamGameStatsRequest,
    response_adapter=TypeAdapter(list[TeamGameStats]),
    row_model=TeamGameStats,
    access_tier="free",
)

GAMES_PLAYER_STATS = _ManyEndpointOperation(
    id="cfbd.games.player_stats",
    revision=1,
    endpoint="/games/players",
    request_type=PlayerGameStatsRequest,
    response_adapter=TypeAdapter(list[PlayerGameStats]),
    row_model=PlayerGameStats,
    access_tier="free",
)

TEAM_RECORDS = _ManyEndpointOperation(
    id="cfbd.games.team_records",
    revision=1,
    endpoint="/records",
    request_type=RecordsRequest,
    response_adapter=TypeAdapter(list[TeamRecords]),
    row_model=TeamRecords,
    access_tier="free",
)
