"""Own typed endpoint operations for the Metrics domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.metrics.models.pydantic.requests import WinProbabilityRequest
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability

PLAY_WIN_PROBABILITIES = _ManyEndpointOperation(
    id="cfbd.metrics.play_win_probabilities",
    revision=1,
    endpoint="/metrics/wp",
    request_type=WinProbabilityRequest,
    response_adapter=TypeAdapter(list[PlayWinProbability]),
    row_model=PlayWinProbability,
    access_tier="free",
)
