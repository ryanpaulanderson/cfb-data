"""Own typed endpoint operations for the Teams domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.teams.models.pydantic.requests import (
    RosterRequest,
    TalentRequest,
    TeamATSRequest,
    TeamsRequest,
)
from cfb_data.teams.models.pydantic.responses import (
    RosterPlayer,
    Team,
    TeamATS,
    TeamTalent,
)

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

TEAM_ATS = _ManyEndpointOperation(
    id="cfbd.teams.ats",
    revision=1,
    endpoint="/teams/ats",
    request_type=TeamATSRequest,
    response_adapter=TypeAdapter(list[TeamATS]),
    row_model=TeamATS,
    access_tier="free",
)

TEAM_TALENT = _ManyEndpointOperation(
    id="cfbd.teams.talent",
    revision=1,
    endpoint="/talent",
    request_type=TalentRequest,
    response_adapter=TypeAdapter(list[TeamTalent]),
    row_model=TeamTalent,
    access_tier="free",
)
