"""Define the normalized game identity read contract."""

from datetime import datetime

from pydantic import Field

from cfb_data.enums import SeasonType
from cfb_data.identities.contracts import _IdentityModel

from .responses import GameStatus


class GameIdentity(_IdentityModel):
    """Represent one game's partition and stable relationships."""

    id: int = Field(gt=0)
    season: int | None = None
    week: int | None = None
    season_type: SeasonType | None = None
    start_date: datetime | None = None
    status: GameStatus | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    venue_id: int | None = None


__all__ = ["GameIdentity"]
