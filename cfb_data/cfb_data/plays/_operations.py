"""Own typed endpoint operations for the Plays domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.plays.models.pydantic.requests import PlaysRequest
from cfb_data.plays.models.pydantic.responses import Play

PLAYS_LIST = _ManyEndpointOperation(
    id="cfbd.plays.list",
    revision=1,
    endpoint="/plays",
    request_type=PlaysRequest,
    response_adapter=TypeAdapter(list[Play]),
    row_model=Play,
    access_tier="free",
)
