"""Define the normalized team identity read contract."""

from pydantic import Field

from cfb_data.identities.contracts import _IdentityModel


class TeamIdentity(_IdentityModel):
    """Represent one provider team identity."""

    id: int = Field(gt=0)
    school: str
    abbreviation: str | None = None
    alternate_names: tuple[str, ...] = ()


__all__ = ["TeamIdentity"]
