"""Define the normalized athlete identity read contract."""

from cfb_data.identities.contracts import _IdentityModel


class AthleteIdentity(_IdentityModel):
    """Represent one athlete and an optional team-season membership."""

    id: str
    name: str
    position: str | None = None
    team: str | None = None
    season: int | None = None


__all__ = ["AthleteIdentity"]
