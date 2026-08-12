"""Validate responses from implemented CFBD Venues endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class Venue(BaseModel):
    """Represent one venue or a Team's nested home location."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: int | None = Field(ge=0)
    name: str | None
    city: str | None
    state: str | None
    zip: str | None
    country_code: str | None = Field(alias="countryCode")
    timezone: str | None
    latitude: float | None
    longitude: float | None
    elevation: str | None
    capacity: int | None = Field(ge=0)
    construction_year: int | None = Field(default=None, alias="constructionYear")
    grass: bool | None = None
    dome: bool | None = None
