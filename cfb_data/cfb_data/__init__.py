"""Access validated CollegeFootballData endpoints as pandas or Polars frames."""

from .client import CFBDClient, DataFrameBackend
from .drives.models.pydantic.requests import DrivesRequest
from .enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)
from .errors import (
    CFBDAuthenticationError,
    CFBDAuthorizationError,
    CFBDClientStateError,
    CFBDConfigurationError,
    CFBDDataFrameConversionError,
    CFBDError,
    CFBDHTTPError,
    CFBDOptionalDependencyError,
    CFBDRateLimitError,
    CFBDRequestValidationError,
    CFBDResponseDecodeError,
    CFBDResponseValidationError,
    CFBDServerError,
    CFBDTimeoutError,
    CFBDTLSError,
    CFBDTransportError,
)
from .games.models.pydantic.requests import (
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
from .games.models.pydantic.responses import AdvancedBoxScore
from .plays.models.pydantic.requests import (
    LivePlaysRequest,
    PlaysRequest,
    PlayStatsRequest,
)
from .plays.models.pydantic.responses import DownType, HomeAway, LiveGame, RushPass
from .retry import RetryPolicy

__all__ = [
    "AdvancedBoxScoreRequest",
    "AdvancedBoxScore",
    "CalendarRequest",
    "CFBDAuthenticationError",
    "CFBDAuthorizationError",
    "CFBDClient",
    "CFBDClientStateError",
    "CFBDConfigurationError",
    "CFBDDataFrameConversionError",
    "CFBDError",
    "CFBDHTTPError",
    "CFBDOptionalDependencyError",
    "CFBDRateLimitError",
    "CFBDRequestValidationError",
    "CFBDResponseDecodeError",
    "CFBDResponseValidationError",
    "CFBDServerError",
    "CFBDTimeoutError",
    "CFBDTLSError",
    "CFBDTransportError",
    "Classification",
    "DataFrameBackend",
    "DrivesRequest",
    "GameMediaRequest",
    "GamesRequest",
    "GameWeatherRequest",
    "HomeAway",
    "LiveGame",
    "LivePlaysRequest",
    "MediaType",
    "PlayerGameStatsRequest",
    "PlayoffCompetition",
    "PlayoffRound",
    "PlaysRequest",
    "PlayStatsRequest",
    "RecordsRequest",
    "RetryPolicy",
    "RushPass",
    "ScoreboardRequest",
    "SeasonType",
    "TeamGameStatsRequest",
    "DownType",
]
