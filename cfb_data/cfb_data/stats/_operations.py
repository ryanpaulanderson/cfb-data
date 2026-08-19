"""Own typed endpoint operations for the Stats domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.stats.models.pydantic.requests import (
    AdvancedSeasonStatsRequest,
    PlayerSeasonStatsRequest,
    TeamSeasonStatsRequest,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
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
