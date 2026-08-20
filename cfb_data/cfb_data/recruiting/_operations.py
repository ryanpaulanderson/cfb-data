"""Own typed endpoint operations for the Recruiting domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.recruiting.models.pydantic.requests import (
    RecruitingPlayersRequest,
    RecruitingTeamsRequest,
)
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)

RECRUITING_PLAYERS = _ManyEndpointOperation(
    id="cfbd.recruiting.players",
    revision=1,
    endpoint="/recruiting/players",
    request_type=RecruitingPlayersRequest,
    response_adapter=TypeAdapter(list[Recruit]),
    row_model=Recruit,
    access_tier="free",
)

RECRUITING_TEAMS = _ManyEndpointOperation(
    id="cfbd.recruiting.teams",
    revision=1,
    endpoint="/recruiting/teams",
    request_type=RecruitingTeamsRequest,
    response_adapter=TypeAdapter(list[TeamRecruitingRanking]),
    row_model=TeamRecruitingRanking,
    access_tier="free",
)
