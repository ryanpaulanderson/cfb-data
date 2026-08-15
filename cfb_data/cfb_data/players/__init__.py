"""Export the supported Players namespace and public contracts."""

from cfb_data.enums import TransferEligibility

from .models.pydantic import (
    AthleteIdentity,
    PlayerSearchRequest,
    PlayerSearchResult,
    PlayerSearchTeamStint,
    PlayerSeasonOverview,
    PlayerSeasonOverviewBoxScore,
    PlayerSeasonOverviewCategory,
    PlayerSeasonOverviewPPA,
    PlayerSeasonOverviewRequest,
    PlayerSeasonOverviewStat,
    PlayerTransfer,
    PlayerUsage,
    PlayerUsageRequest,
    PlayerUsageSplit,
    ReturningProduction,
    ReturningProductionRequest,
    TransferPortalRequest,
)
from .resource import PlayersResource

__all__ = [
    "AthleteIdentity",
    "PlayerSearchRequest",
    "PlayerSearchResult",
    "PlayerSearchTeamStint",
    "PlayerSeasonOverview",
    "PlayerSeasonOverviewBoxScore",
    "PlayerSeasonOverviewCategory",
    "PlayerSeasonOverviewPPA",
    "PlayerSeasonOverviewRequest",
    "PlayerSeasonOverviewStat",
    "PlayerTransfer",
    "PlayerUsage",
    "PlayerUsageRequest",
    "PlayerUsageSplit",
    "PlayersResource",
    "ReturningProduction",
    "ReturningProductionRequest",
    "TransferEligibility",
    "TransferPortalRequest",
]
