"""Own typed endpoint operations for the Plays domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.plays.models.pydantic.requests import (
    PlaysRequest,
    PlayStatsRequest,
    PlayStatTypesRequest,
)
from cfb_data.plays.models.pydantic.responses import Play, PlayStat, PlayStatType

PLAYS_LIST = _ManyEndpointOperation(
    id="cfbd.plays.list",
    revision=1,
    endpoint="/plays",
    request_type=PlaysRequest,
    response_adapter=TypeAdapter(list[Play]),
    row_model=Play,
    access_tier="free",
)

PLAYS_STATS = _ManyEndpointOperation(
    id="cfbd.plays.stats",
    revision=1,
    endpoint="/plays/stats",
    request_type=PlayStatsRequest,
    response_adapter=TypeAdapter(list[PlayStat]),
    row_model=PlayStat,
    access_tier="free",
    documented_limit=2_000,
)

PLAY_STAT_TYPES = _ManyEndpointOperation(
    id="cfbd.plays.stat_types",
    revision=1,
    endpoint="/plays/stats/types",
    request_type=PlayStatTypesRequest,
    response_adapter=TypeAdapter(list[PlayStatType]),
    row_model=PlayStatType,
    access_tier="free",
)
