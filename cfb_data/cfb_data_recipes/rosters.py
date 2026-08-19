"""Provide the independently authored historical rosters dataset recipe.

``rosters`` composes the public roster and season-scoped teams sources. Roster
membership keeps the source team text as part of its grain, while temporal
team resolution records resolved, unresolved, or ambiguous evidence instead
of silently choosing a name match.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification
from cfb_data.teams.identity import TeamIdentityIndex, TeamIdentityStatus
from cfb_data.teams.models.pydantic.responses import RosterPlayer, Team
from cfb_data.teams.sources import roster as roster_source
from cfb_data.teams.sources import teams as teams_source
from pydantic import BaseModel, ConfigDict, Field


class RosterMembership(BaseModel):
    """Represent one athlete/team/season roster membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    season: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    source_team: str = Field(
        description="Team text retained from the roster source.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    team_id: int | None = Field(
        default=None,
        gt=0,
        description="Resolved stable team ID only when evidence is unique.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    team_identity_status: TeamIdentityStatus = Field(
        description="Outcome of season-scoped school and alias resolution."
    )
    team_identity_candidate_ids: list[int] = Field(
        description="Ordered matching team IDs retained as identity evidence.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    athlete_id: str = Field(json_schema_extra={"semantic_type": "identifier"})
    first_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    last_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    height: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "inches"},
    )
    weight: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "pounds"},
    )
    jersey: int | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    class_year: int = Field(
        ge=0,
        description="Source player class-year value, distinct from roster season.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    position: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_city: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_state: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_country: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    home_latitude: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "degrees"},
    )
    home_longitude: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "degrees"},
    )
    home_county_fips: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "identifier"},
    )
    recruit_ids: list[str] | None = Field(
        default=None,
        description="Source recruiting identifiers preserved in source order.",
        json_schema_extra={"semantic_type": "identifier"},
    )


@step(
    id="cfbd.rosters.normalize",
    revision=1,
    output=RosterMembership,
    deterministic=True,
)
def normalize_roster(
    season: int,
    players: list[RosterPlayer],
    teams: list[Team],
) -> list[RosterMembership]:
    """Attach explicit season-scoped team identity evidence.

    :param season: Requested roster season.
    :param players: Validated roster memberships.
    :param teams: Validated teams carrying historical school and alias evidence.
    :return: Memberships with deterministic identity outcomes and ordering.
    """
    identity_index = TeamIdentityIndex(teams)
    rows = [_normalize_player(season, player, identity_index) for player in players]
    return sorted(
        rows,
        key=lambda row: (row.season, row.source_team.casefold(), row.athlete_id),
    )


@dataset(
    id="cfbd.rosters",
    revision=1,
    row=RosterMembership,
    grain="one athlete/team/season membership",
    keys=("season", "source_team", "athlete_id"),
    order_by=("season", "source_team", "athlete_id"),
    partition_by=("season",),
)
def rosters(
    *,
    season: int,
    team: str | None = None,
    classification: Classification | None = None,
) -> RecipeRef[list[RosterMembership]]:
    """Build historical roster memberships with temporal identity evidence.

    :param season: Required roster and team-evidence season.
    :param team: Optional roster team selector.
    :param classification: Optional roster classification selector.
    :return: A reference to the validated rosters dataset.
    """
    return normalize_roster(
        season,
        roster_source(team=team, year=season, classification=classification),
        teams_source(year=season),
    )


def _normalize_player(
    season: int,
    player: RosterPlayer,
    identity_index: TeamIdentityIndex,
) -> RosterMembership:
    evidence = identity_index.resolve(player.team)
    return RosterMembership(
        season=season,
        source_team=player.team,
        team_id=evidence.team_id,
        team_identity_status=evidence.status,
        team_identity_candidate_ids=list(evidence.candidate_ids),
        athlete_id=player.id,
        first_name=player.first_name,
        last_name=player.last_name,
        height=player.height,
        weight=player.weight,
        jersey=player.jersey,
        class_year=player.year,
        position=player.position,
        home_city=player.home_city,
        home_state=player.home_state,
        home_country=player.home_country,
        home_latitude=player.home_latitude,
        home_longitude=player.home_longitude,
        home_county_fips=player.home_county_fips,
        recruit_ids=player.recruit_ids,
    )


__all__ = ["RosterMembership", "TeamIdentityStatus", "rosters"]
