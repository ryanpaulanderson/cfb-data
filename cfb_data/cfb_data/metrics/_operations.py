"""Own typed endpoint operations for the Metrics domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.metrics.models.pydantic.requests import (
    PlayerGamePPARequest,
    PlayerSeasonPPARequest,
    TeamGamePPARequest,
    TeamSeasonPPARequest,
    WinProbabilityRequest,
)
from cfb_data.metrics.models.pydantic.responses import (
    PlayerGamePredictedPointsAdded,
    PlayerSeasonPredictedPointsAdded,
    PlayWinProbability,
    TeamGamePredictedPointsAdded,
    TeamSeasonPredictedPointsAdded,
)

TEAM_SEASON_PPA = _ManyEndpointOperation(
    id="cfbd.metrics.team_season_ppa",
    revision=1,
    endpoint="/ppa/teams",
    request_type=TeamSeasonPPARequest,
    response_adapter=TypeAdapter(list[TeamSeasonPredictedPointsAdded]),
    row_model=TeamSeasonPredictedPointsAdded,
    access_tier="free",
)

TEAM_GAME_PPA = _ManyEndpointOperation(
    id="cfbd.metrics.team_game_ppa",
    revision=1,
    endpoint="/ppa/games",
    request_type=TeamGamePPARequest,
    response_adapter=TypeAdapter(list[TeamGamePredictedPointsAdded]),
    row_model=TeamGamePredictedPointsAdded,
    access_tier="free",
)

PLAYER_GAME_PPA = _ManyEndpointOperation(
    id="cfbd.metrics.player_game_ppa",
    revision=1,
    endpoint="/ppa/players/games",
    request_type=PlayerGamePPARequest,
    response_adapter=TypeAdapter(list[PlayerGamePredictedPointsAdded]),
    row_model=PlayerGamePredictedPointsAdded,
    access_tier="free",
)

PLAYER_SEASON_PPA = _ManyEndpointOperation(
    id="cfbd.metrics.player_season_ppa",
    revision=1,
    endpoint="/ppa/players/season",
    request_type=PlayerSeasonPPARequest,
    response_adapter=TypeAdapter(list[PlayerSeasonPredictedPointsAdded]),
    row_model=PlayerSeasonPredictedPointsAdded,
    access_tier="free",
)

PLAY_WIN_PROBABILITIES = _ManyEndpointOperation(
    id="cfbd.metrics.play_win_probabilities",
    revision=1,
    endpoint="/metrics/wp",
    request_type=WinProbabilityRequest,
    response_adapter=TypeAdapter(list[PlayWinProbability]),
    row_model=PlayWinProbability,
    access_tier="free",
)
