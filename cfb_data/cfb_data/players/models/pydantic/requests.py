"""Validate request parameters for implemented Players endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _PlayersRequest(BaseModel):
    """Apply the closed-object contract shared by Players requests."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PlayerSearchRequest(_PlayersRequest):
    """Validate filters accepted by ``GET /player/search``."""

    search_term: str = Field(alias="searchTerm", min_length=1)
    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)


class PlayerUsageRequest(_PlayersRequest):
    """Validate filters accepted by ``GET /player/usage``."""

    year: int = Field(ge=1869)
    conference: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)
    team: str | None = Field(default=None, min_length=1)
    player_id: int | None = Field(default=None, alias="playerId", gt=0)
    exclude_garbage_time: bool | None = Field(default=None, alias="excludeGarbageTime")


class PlayerSeasonOverviewRequest(_PlayersRequest):
    """Validate filters accepted by ``GET /player/season/overview``."""

    year: int = Field(ge=1869)
    player_id: int = Field(alias="playerId", gt=0)


class ReturningProductionRequest(_PlayersRequest):
    """Validate filters accepted by ``GET /player/returning``."""

    year: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Require a season or team selector."""
        if self.year is None and self.team is None:
            raise ValueError("year is required when team is not specified")
        return self


class TransferPortalRequest(_PlayersRequest):
    """Validate filters accepted by ``GET /player/portal``."""

    year: int = Field(ge=1869)


__all__ = [
    "PlayerSearchRequest",
    "PlayerSeasonOverviewRequest",
    "PlayerUsageRequest",
    "ReturningProductionRequest",
    "TransferPortalRequest",
]
