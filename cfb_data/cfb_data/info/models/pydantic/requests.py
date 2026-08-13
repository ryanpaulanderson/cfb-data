"""Validate request parameters for implemented Info endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import UserUsageApi


class InfoUsageRequest(BaseModel):
    """Validate filters accepted by ``GET /info/usage``."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    days: int | None = Field(default=None, ge=1, le=31)
    limit: int | None = Field(default=None, ge=1, le=50)
    api: UserUsageApi | None = None


__all__ = ["InfoUsageRequest"]
