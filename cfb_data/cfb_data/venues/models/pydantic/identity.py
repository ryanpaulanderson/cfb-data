"""Define the normalized venue identity read contract."""

from pydantic import Field

from cfb_data.identities.contracts import _IdentityModel


class VenueIdentity(_IdentityModel):
    """Represent one provider venue identity."""

    id: int = Field(gt=0)
    name: str
    city: str | None = None
    state: str | None = None


__all__ = ["VenueIdentity"]
