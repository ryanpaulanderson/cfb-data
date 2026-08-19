"""Own typed endpoint operations for the Rankings domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.rankings.models.pydantic.requests import RankingsRequest
from cfb_data.rankings.models.pydantic.responses import PollWeek

RANKINGS_LIST = _ManyEndpointOperation(
    id="cfbd.rankings.list",
    revision=1,
    endpoint="/rankings",
    request_type=RankingsRequest,
    response_adapter=TypeAdapter(list[PollWeek]),
    row_model=PollWeek,
    access_tier="free",
)
