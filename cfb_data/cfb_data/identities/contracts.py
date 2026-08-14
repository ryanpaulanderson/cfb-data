"""Define identity-query controls and hydration results."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import Classification


class _IdentityModel(BaseModel):
    """Apply immutable closed-object behavior to compact identity values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FreshnessMode(StrEnum):
    """Control whether identity lookup may spend API quota."""

    ensure_fresh = "ensure_fresh"
    allow_stale = "allow_stale"
    local_only = "local_only"


class HydrationPlan(_IdentityModel):
    """Describe or report a resumable identity hydration operation."""

    seasons: tuple[int, ...]
    classification: Classification | None = None
    endpoints: tuple[str, ...]
    planned_calls: int = Field(ge=0)
    completed_calls: int = Field(ge=0)
    dry_run: bool


__all__ = ["FreshnessMode", "HydrationPlan"]
