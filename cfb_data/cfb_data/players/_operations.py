"""Own typed endpoint operations for the Players domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.players.models.pydantic.requests import (
    PlayerUsageRequest,
    ReturningProductionRequest,
)
from cfb_data.players.models.pydantic.responses import PlayerUsage, ReturningProduction

PLAYER_USAGE = _ManyEndpointOperation(
    id="cfbd.players.usage",
    revision=1,
    endpoint="/player/usage",
    request_type=PlayerUsageRequest,
    response_adapter=TypeAdapter(list[PlayerUsage]),
    row_model=PlayerUsage,
    access_tier="free",
)

RETURNING_PRODUCTION = _ManyEndpointOperation(
    id="cfbd.players.returning_production",
    revision=1,
    endpoint="/player/returning",
    request_type=ReturningProductionRequest,
    response_adapter=TypeAdapter(list[ReturningProduction]),
    row_model=ReturningProduction,
    access_tier="free",
)
