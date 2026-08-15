"""Validate responses from implemented CFBD Venues endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from cfb_data._catalog.models import VenueFact
from cfb_data._catalog.projection import (
    IdentityAttribute,
    IdentityKey,
    ObservationAuthority,
    ValueTransform,
)


class Venue(BaseModel):
    """Represent one venue or a Team's nested home location."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: Annotated[
        int | None,
        IdentityKey(
            VenueFact,
            "id",
            transform=ValueTransform.positive_int,
            authority=ObservationAuthority.authoritative,
        ),
    ] = Field(ge=0)
    name: Annotated[
        str | None,
        IdentityAttribute(
            VenueFact,
            "name",
            transform=ValueTransform.nonempty_text,
            authority=ObservationAuthority.authoritative,
        ),
    ]
    city: Annotated[
        str | None,
        IdentityAttribute(
            VenueFact,
            "city",
            authority=ObservationAuthority.authoritative,
        ),
    ]
    state: Annotated[
        str | None,
        IdentityAttribute(
            VenueFact,
            "state",
            authority=ObservationAuthority.authoritative,
        ),
    ]
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
