"""Own typed endpoint operations for the Ratings domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.ratings.models.pydantic.requests import (
    ConferenceSPRatingsRequest,
    CoreRatingsRequest,
    EloRatingsRequest,
    ExpandedSRSRatingsRequest,
    FPIRatingsRequest,
    SPRatingsRequest,
    SRSRatingsRequest,
)
from cfb_data.ratings.models.pydantic.responses import (
    ConferenceSP,
    ExpandedTeamSRS,
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)

CORE_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.core",
    revision=1,
    endpoint="/ratings/core",
    request_type=CoreRatingsRequest,
    response_adapter=TypeAdapter(list[TeamCoreRating]),
    row_model=TeamCoreRating,
    access_tier="free",
)

SP_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.sp",
    revision=1,
    endpoint="/ratings/sp",
    request_type=SPRatingsRequest,
    response_adapter=TypeAdapter(list[TeamSP]),
    row_model=TeamSP,
    access_tier="free",
)

CONFERENCE_SP_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.conference_sp",
    revision=1,
    endpoint="/ratings/sp/conferences",
    request_type=ConferenceSPRatingsRequest,
    response_adapter=TypeAdapter(list[ConferenceSP]),
    row_model=ConferenceSP,
    access_tier="free",
)

SRS_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.srs",
    revision=1,
    endpoint="/ratings/srs",
    request_type=SRSRatingsRequest,
    response_adapter=TypeAdapter(list[TeamSRS]),
    row_model=TeamSRS,
    access_tier="free",
)

EXPANDED_SRS_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.expanded_srs",
    revision=1,
    endpoint="/ratings/srs/expanded",
    request_type=ExpandedSRSRatingsRequest,
    response_adapter=TypeAdapter(list[ExpandedTeamSRS]),
    row_model=ExpandedTeamSRS,
    access_tier="free",
)

ELO_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.elo",
    revision=1,
    endpoint="/ratings/elo",
    request_type=EloRatingsRequest,
    response_adapter=TypeAdapter(list[TeamElo]),
    row_model=TeamElo,
    access_tier="free",
)

FPI_RATINGS = _ManyEndpointOperation(
    id="cfbd.ratings.fpi",
    revision=1,
    endpoint="/ratings/fpi",
    request_type=FPIRatingsRequest,
    response_adapter=TypeAdapter(list[TeamFPI]),
    row_model=TeamFPI,
    access_tier="free",
)
