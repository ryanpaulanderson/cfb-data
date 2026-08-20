"""Own typed endpoint operations for the Coaches domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.coaches.models.pydantic.requests import (
    CoachSeasonsRequest,
    CoachTenuresRequest,
)
from cfb_data.coaches.models.pydantic.responses import CoachTenure, DetailedCoachSeason

COACH_SEASONS = _ManyEndpointOperation(
    id="cfbd.coaches.seasons",
    revision=1,
    endpoint="/coaches/seasons",
    request_type=CoachSeasonsRequest,
    response_adapter=TypeAdapter(list[DetailedCoachSeason]),
    row_model=DetailedCoachSeason,
    access_tier="free",
)

COACH_TENURES = _ManyEndpointOperation(
    id="cfbd.coaches.tenures",
    revision=1,
    endpoint="/coaches/tenures",
    request_type=CoachTenuresRequest,
    response_adapter=TypeAdapter(list[CoachTenure]),
    row_model=CoachTenure,
    access_tier="free",
)
