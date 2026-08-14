"""Export the supported Games namespace and request contracts."""

from cfb_data.enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)

from .models.pydantic.identity import GameIdentity
from .models.pydantic.requests import (
    AdvancedBoxScoreRequest,
    CalendarRequest,
    GameMediaRequest,
    GamesRequest,
    GameWeatherRequest,
    PlayerGameStatsRequest,
    RecordsRequest,
    ScoreboardRequest,
    TeamGameStatsRequest,
)
from .models.pydantic.responses import AdvancedBoxScore
from .resource import GamesResource

__all__ = [
    "AdvancedBoxScoreRequest",
    "AdvancedBoxScore",
    "CalendarRequest",
    "Classification",
    "GameMediaRequest",
    "GamesRequest",
    "GamesResource",
    "GameIdentity",
    "GameWeatherRequest",
    "MediaType",
    "PlayerGameStatsRequest",
    "PlayoffCompetition",
    "PlayoffRound",
    "RecordsRequest",
    "ScoreboardRequest",
    "SeasonType",
    "TeamGameStatsRequest",
]
