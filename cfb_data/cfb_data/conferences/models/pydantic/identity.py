"""Define the normalized conference identity read contract."""

from pydantic import Field

from cfb_data.identities.contracts import _IdentityModel

from .responses import ConferenceClassification


class ConferenceIdentity(_IdentityModel):
    """Represent one provider conference identity."""

    id: int = Field(gt=0)
    name: str
    abbreviation: str | None = None
    classification: ConferenceClassification | None = None


__all__ = ["ConferenceIdentity"]
