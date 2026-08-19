"""Own typed endpoint operations for the Teams domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.teams.models.pydantic.requests import RosterRequest, TeamsRequest
from cfb_data.teams.models.pydantic.responses import RosterPlayer, Team

TEAMS_LIST = _ManyEndpointOperation(
    id="cfbd.teams.list",
    revision=1,
    endpoint="/teams",
    request_type=TeamsRequest,
    response_adapter=TypeAdapter(list[Team]),
    row_model=Team,
    access_tier="free",
)

ROSTER_LIST = _ManyEndpointOperation(
    id="cfbd.teams.roster",
    revision=1,
    endpoint="/roster",
    request_type=RosterRequest,
    response_adapter=TypeAdapter(list[RosterPlayer]),
    row_model=RosterPlayer,
    access_tier="free",
)
