"""Validate responses from implemented CFBD Info endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data.enums import UserUsageApi


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Info responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def require_utc_datetimes(cls, value: object) -> object:
        """Require aware response timestamps and normalize them to UTC."""
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Response timestamps must be timezone-aware")
        return value.astimezone(UTC)


class UserFeatureAccess(_ResponseModel):
    """Represent route families enabled for the authenticated user."""

    adjusted_metrics: bool = Field(alias="adjustedMetrics")
    weather: bool
    scoreboard: bool
    live_play_by_play: bool = Field(alias="livePlayByPlay")
    graph_ql: bool = Field(alias="graphQl")


class UserInfo(_ResponseModel):
    """Represent account tier, quota, product, and feature metadata."""

    patron_level: int = Field(alias="patronLevel", ge=0)
    tier_name: str = Field(alias="tierName")
    monthly_limit: int | None = Field(alias="monthlyLimit", ge=0)
    remaining_calls: int | None = Field(alias="remainingCalls", ge=0)
    used_calls: int | None = Field(alias="usedCalls", ge=0)
    reset_at: datetime = Field(alias="resetAt")
    shared_pool: bool = Field(alias="sharedPool")
    products: list[str]
    features: UserFeatureAccess


class UserUsageWindow(_ResponseModel):
    """Represent the inclusive time window summarized by a usage response."""

    start: datetime
    end: datetime


class UserUsageTotals(_ResponseModel):
    """Represent aggregate requests within one usage window."""

    requests: int = Field(ge=0)
    cfb_requests: int = Field(alias="cfbRequests", ge=0)
    cbb_requests: int = Field(alias="cbbRequests", ge=0)
    unique_endpoints: int = Field(alias="uniqueEndpoints", ge=0)


class UserUsageEndpoint(_ResponseModel):
    """Represent aggregate usage for one API endpoint."""

    api: UserUsageApi
    endpoint: str
    requests: int = Field(ge=0)
    last_used_at: datetime = Field(alias="lastUsedAt")


class UserUsageRecentRequest(_ResponseModel):
    """Represent one recent API request in account usage metadata."""

    api: UserUsageApi
    endpoint: str
    requested_at: datetime = Field(alias="requestedAt")


class UserUsage(_ResponseModel):
    """Represent recent shared-pool request activity for one account."""

    window: UserUsageWindow
    api: UserUsageApi
    totals: UserUsageTotals
    top_endpoints: list[UserUsageEndpoint] = Field(alias="topEndpoints")
    recent_requests: list[UserUsageRecentRequest] = Field(alias="recentRequests")


__all__ = [
    "UserFeatureAccess",
    "UserInfo",
    "UserUsage",
    "UserUsageEndpoint",
    "UserUsageRecentRequest",
    "UserUsageTotals",
    "UserUsageWindow",
]
