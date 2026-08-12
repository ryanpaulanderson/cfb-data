"""Access validated CollegeFootballData endpoints as pandas or Polars frames."""

from .client import CFBDClient, DataFrameBackend
from .conferences.models.pydantic.requests import (
    ConferenceAffiliationsRequest,
    ConferenceChangesRequest,
    ConferencesRequest,
)
from .conferences.models.pydantic.responses import ConferenceClassification
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
from .teams.models.pydantic.requests import (
    FBSTeamsRequest,
    RosterRequest,
    TalentRequest,
    TeamATSRequest,
    TeamMatchupRequest,
    TeamsRequest,
)

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
    "ConferenceAffiliationsRequest",
    "ConferenceChangesRequest",
    "ConferenceClassification",
    "ConferencesRequest",
    "DataFrameBackend",
    "DrivesRequest",
    "GameMediaRequest",
    "GamesRequest",
    "GameWeatherRequest",
    "FBSTeamsRequest",
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
    "RosterRequest",
    "RushPass",
    "ScoreboardRequest",
    "SeasonType",
    "TeamGameStatsRequest",
    "TalentRequest",
    "TeamATSRequest",
    "TeamMatchupRequest",
    "TeamsRequest",
    "DownType",
]
