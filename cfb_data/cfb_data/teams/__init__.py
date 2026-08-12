"""Export the supported Teams namespace and public contracts."""

from cfb_data.conferences import ConferenceClassification
from cfb_data.enums import Classification
from cfb_data.venues import Venue

from .models.pydantic import (
    FBSTeamsRequest,
    Matchup,
    MatchupGame,
    RosterPlayer,
    RosterRequest,
    TalentRequest,
    Team,
    TeamATS,
    TeamATSRequest,
    TeamMatchupRequest,
    TeamsRequest,
    TeamTalent,
)
from .resource import TeamsResource

__all__ = [
    "Classification",
    "ConferenceClassification",
    "FBSTeamsRequest",
    "Matchup",
    "MatchupGame",
    "RosterPlayer",
    "RosterRequest",
    "TalentRequest",
    "Team",
    "TeamATS",
    "TeamATSRequest",
    "TeamMatchupRequest",
    "TeamsRequest",
    "TeamsResource",
    "TeamTalent",
    "Venue",
]
