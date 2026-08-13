"""Export the supported Betting namespace and public contracts."""

from cfb_data.enums import Classification, SeasonType

from .models.pydantic import BettingGame, BettingLinesRequest, GameLine
from .resource import BettingResource

__all__ = [
    "BettingGame",
    "BettingLinesRequest",
    "BettingResource",
    "Classification",
    "GameLine",
    "SeasonType",
]
