"""Define compact validated identity-query results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import Classification


class FreshnessMode(StrEnum):
    """Control whether identity lookup may spend API quota."""

    ensure_fresh = "ensure_fresh"
    allow_stale = "allow_stale"
    local_only = "local_only"


class _IdentityModel(BaseModel):
    """Apply immutable closed-object behavior to compact identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TeamIdentity(_IdentityModel):
    """Represent one provider team identity."""

    id: int = Field(gt=0)
    school: str
    abbreviation: str | None = None
    alternate_names: tuple[str, ...] = ()


class ConferenceIdentity(_IdentityModel):
    """Represent one provider conference identity."""

    id: int = Field(gt=0)
    name: str
    abbreviation: str | None = None
    classification: str | None = None


class VenueIdentity(_IdentityModel):
    """Represent one provider venue identity."""

    id: int = Field(gt=0)
    name: str
    city: str | None = None
    state: str | None = None


class GameIdentity(_IdentityModel):
    """Represent one game's partition and stable relationships."""

    id: int = Field(gt=0)
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    start_date: datetime | None = None
    status: str | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    venue_id: int | None = None


class AthleteIdentity(_IdentityModel):
    """Represent one athlete and an optional team-season membership."""

    id: str
    name: str
    position: str | None = None
    team: str | None = None
    season: int | None = None


class HydrationPlan(_IdentityModel):
    """Describe or report a resumable identity hydration operation."""

    seasons: tuple[int, ...]
    classification: Classification | None = None
    endpoints: tuple[str, ...]
    planned_calls: int = Field(ge=0)
    completed_calls: int = Field(ge=0)
    dry_run: bool
