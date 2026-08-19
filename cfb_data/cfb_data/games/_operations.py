"""Own typed endpoint operations for the Games domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.games.models.pydantic.requests import (
    GamesRequest,
    PlayerGameStatsRequest,
    TeamGameStatsRequest,
)
from cfb_data.games.models.pydantic.responses import (
    Game,
    PlayerGameStats,
    TeamGameStats,
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
