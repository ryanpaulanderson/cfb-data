"""Construct domain-owned identity views from backend-neutral catalog values."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity


def team_identity(
    *,
    id: int,
    school: str,
    abbreviation: str | None,
    alternate_names: tuple[str, ...],
) -> TeamIdentity:
    """Return one validated team identity from canonical catalog values."""
    from cfb_data.teams.models.pydantic.identity import TeamIdentity

    return TeamIdentity(
        id=id,
        school=school,
        abbreviation=abbreviation,
        alternate_names=alternate_names,
    )


def conference_identity(
    *,
    id: int,
    name: str,
    abbreviation: str | None,
    classification: str | None,
) -> ConferenceIdentity:
    """Return one validated conference identity from canonical catalog values."""
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity

    return ConferenceIdentity(
        id=id,
        name=name,
        abbreviation=abbreviation,
        classification=classification,
    )


def venue_identity(
    *, id: int, name: str, city: str | None, state: str | None
) -> VenueIdentity:
    """Return one validated venue identity from canonical catalog values."""
    from cfb_data.venues.models.pydantic.identity import VenueIdentity

    return VenueIdentity(id=id, name=name, city=city, state=state)


def game_identity(
    *,
    id: int,
    season: int | None,
    week: int | None,
    season_type: str | None,
    start_date: datetime | None,
    status: str | None,
    home_team_id: int | None,
    away_team_id: int | None,
    venue_id: int | None,
) -> GameIdentity:
    """Return one validated game identity from canonical catalog values."""
    from cfb_data.games.models.pydantic.identity import GameIdentity

    return GameIdentity(
        id=id,
        season=season,
        week=week,
        season_type=season_type,
        start_date=start_date,
        status=status,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        venue_id=venue_id,
    )


def athlete_identity(
    *,
    id: str,
    name: str,
    position: str | None,
    team: str | None = None,
    season: int | None = None,
) -> AthleteIdentity:
    """Return one validated athlete identity from canonical catalog values."""
    from cfb_data.players.models.pydantic.identity import AthleteIdentity

    return AthleteIdentity(
        id=id,
        name=name,
        position=position,
        team=team,
        season=season,
    )
