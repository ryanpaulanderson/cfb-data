"""Export validated Playoffs request and response models."""

from .requests import CfpGamesRequest, CfpParticipantsRequest, CfpPlayoffRequest
from .responses import (
    CfpPlayoff,
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
    "PlayoffStatus",
    "PlayoffTeam",
]
