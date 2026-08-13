"""Validate request parameters for implemented Draft endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class DraftPicksRequest(BaseModel):
    """Validate filters accepted by ``GET /draft/picks``."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1936)
    team: str | None = Field(default=None, min_length=1)
    school: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    position: str | None = Field(default=None, min_length=1)


__all__ = ["DraftPicksRequest"]
