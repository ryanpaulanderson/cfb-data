"""Export the supported Playoffs namespace and public contracts."""

from .models.pydantic import (
    CfpGamesRequest,
    CfpParticipantsRequest,
    CfpPlayoff,
    CfpPlayoffRequest,
    PlayoffAdvancement,
    PlayoffBidType,
    PlayoffLinkedGame,
    PlayoffMatchup,
    PlayoffMatchupSlot,
    PlayoffMatchupSlotSource,
    PlayoffOutcome,
    PlayoffParticipant,
    PlayoffRoundRecord,
    PlayoffSlotOutcome,
    PlayoffStatus,
    PlayoffTeam,
)
from .resource import PlayoffsResource

__all__ = [
    "CfpGamesRequest",
    "CfpParticipantsRequest",
    "CfpPlayoff",
    "CfpPlayoffRequest",
    "PlayoffAdvancement",
    "PlayoffBidType",
    "PlayoffLinkedGame",
    "PlayoffMatchup",
    "PlayoffMatchupSlot",
    "PlayoffMatchupSlotSource",
    "PlayoffOutcome",
    "PlayoffParticipant",
    "PlayoffRoundRecord",
    "PlayoffSlotOutcome",
    "PlayoffsResource",
    "PlayoffStatus",
    "PlayoffTeam",
]
