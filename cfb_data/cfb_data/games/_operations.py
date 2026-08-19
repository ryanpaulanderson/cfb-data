"""Own typed endpoint operations for the Games domain."""

from __future__ import annotations

from pydantic import TypeAdapter

from cfb_data._operation import _ManyEndpointOperation
from cfb_data.games.models.pydantic.requests import GamesRequest
from cfb_data.games.models.pydantic.responses import Game

GAMES_LIST = _ManyEndpointOperation(
    id="cfbd.games.list",
    revision=1,
    endpoint="/games",
    request_type=GamesRequest,
    response_adapter=TypeAdapter(list[Game]),
    row_model=Game,
    access_tier="free",
)
