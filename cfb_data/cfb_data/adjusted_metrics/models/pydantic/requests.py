"""Validate request parameters for implemented Adjusted Metrics endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class _AdjustedMetricsRequest(BaseModel):
    """Apply the closed-object contract shared by Adjusted Metrics requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class _TeamFilters(_AdjustedMetricsRequest):
    """Define team and season filters shared by adjusted metric routes."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)


class AdjustedTeamMetricsRequest(_TeamFilters):
    """Validate filters accepted by ``GET /wepa/team/season``."""


class AdjustedPlayerPassingRequest(_TeamFilters):
    """Validate filters accepted by ``GET /wepa/players/passing``."""

    position: str | None = Field(default=None, min_length=1)


class AdjustedPlayerRushingRequest(_TeamFilters):
    """Validate filters accepted by ``GET /wepa/players/rushing``."""

    position: str | None = Field(default=None, min_length=1)


class KickerPAARRequest(_TeamFilters):
    """Validate filters accepted by ``GET /wepa/players/kicking``."""


__all__ = [
    "AdjustedPlayerPassingRequest",
    "AdjustedPlayerRushingRequest",
    "AdjustedTeamMetricsRequest",
    "KickerPAARRequest",
]
