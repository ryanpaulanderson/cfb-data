"""Export the supported Recruiting namespace and public contracts."""

from cfb_data.enums import RecruitClassification

from .models.pydantic import (
    AggregatedTeamRecruiting,
    Recruit,
    RecruitHometown,
    RecruitingGroupsRequest,
    RecruitingPlayersRequest,
    RecruitingTeamsRequest,
    TeamRecruitingRanking,
)
from .resource import RecruitingResource

__all__ = [
    "AggregatedTeamRecruiting",
    "Recruit",
    "RecruitClassification",
    "RecruitHometown",
    "RecruitingGroupsRequest",
    "RecruitingPlayersRequest",
    "RecruitingResource",
    "RecruitingTeamsRequest",
    "TeamRecruitingRanking",
]
