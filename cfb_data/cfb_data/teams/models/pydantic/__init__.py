"""Export Pydantic models for Teams endpoints."""

from .requests import (
    FBSTeamsRequest,
    RosterRequest,
    TalentRequest,
    TeamATSRequest,
    TeamMatchupRequest,
    TeamsRequest,
)
from .responses import Matchup, MatchupGame, RosterPlayer, Team, TeamATS, TeamTalent

__all__ = [
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
    "TeamTalent",
]
