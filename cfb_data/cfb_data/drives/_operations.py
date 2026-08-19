"""Own typed endpoint operations for the Drives domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.drives.models.pydantic.requests import DrivesRequest
from cfb_data.drives.models.pydantic.responses import Drive

DRIVES_LIST = _ManyEndpointOperation(
    id="cfbd.drives.list",
    revision=1,
    endpoint="/drives",
    request_type=DrivesRequest,
    response_adapter=TypeAdapter(list[Drive]),
    row_model=Drive,
    access_tier="free",
)
