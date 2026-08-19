"""Own typed endpoint operations for the Adjusted Metrics domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.adjusted_metrics.models.pydantic.requests import (
    AdjustedPlayerPassingRequest,
    AdjustedPlayerRushingRequest,
    AdjustedTeamMetricsRequest,
    KickerPAARRequest,
)
from cfb_data.adjusted_metrics.models.pydantic.responses import (
    AdjustedTeamMetrics,
    KickerPAAR,
    PlayerWeightedEPA,
)

TEAM_SEASON_METRICS = _ManyEndpointOperation(
    id="cfbd.adjusted_metrics.team_season",
    revision=1,
    endpoint="/wepa/team/season",
    request_type=AdjustedTeamMetricsRequest,
    response_adapter=TypeAdapter(list[AdjustedTeamMetrics]),
    row_model=AdjustedTeamMetrics,
    access_tier="tier_1",
)

PLAYER_PASSING_METRICS = _ManyEndpointOperation(
    id="cfbd.adjusted_metrics.player_passing",
    revision=1,
    endpoint="/wepa/players/passing",
    request_type=AdjustedPlayerPassingRequest,
    response_adapter=TypeAdapter(list[PlayerWeightedEPA]),
    row_model=PlayerWeightedEPA,
    access_tier="tier_1",
)

PLAYER_RUSHING_METRICS = _ManyEndpointOperation(
    id="cfbd.adjusted_metrics.player_rushing",
    revision=1,
    endpoint="/wepa/players/rushing",
    request_type=AdjustedPlayerRushingRequest,
    response_adapter=TypeAdapter(list[PlayerWeightedEPA]),
    row_model=PlayerWeightedEPA,
    access_tier="tier_1",
)

KICKER_PAAR_METRICS = _ManyEndpointOperation(
    id="cfbd.adjusted_metrics.kicker_paar",
    revision=1,
    endpoint="/wepa/players/kicking",
    request_type=KickerPAARRequest,
    response_adapter=TypeAdapter(list[KickerPAAR]),
    row_model=KickerPAAR,
    access_tier="tier_1",
)
