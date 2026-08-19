"""Own typed endpoint operations for the Betting domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.betting.models.pydantic.requests import BettingLinesRequest
from cfb_data.betting.models.pydantic.responses import BettingGame

BETTING_LINES = _ManyEndpointOperation(
    id="cfbd.betting.lines",
    revision=1,
    endpoint="/lines",
    request_type=BettingLinesRequest,
    response_adapter=TypeAdapter(list[BettingGame]),
    row_model=BettingGame,
    access_tier="free",
)
