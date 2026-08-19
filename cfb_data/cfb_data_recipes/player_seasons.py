"""Provide the independently authored player-seasons dataset recipe.

``player_seasons`` composes the public ``rosters`` dataset with the public
long-form player-season statistics and temporal Teams source. It unions their
athlete memberships so roster-only and stats-only athletes survive, while
display statistics remain ordered strings rather than inferred numbers.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.stats.models.pydantic.responses import PlayerStat
from cfb_data.stats.sources import player_season_stats
from cfb_data.teams.identity import TeamIdentityIndex, TeamIdentityStatus
from cfb_data.teams.models.pydantic.responses import Team
from cfb_data.teams.sources import teams as teams_source
from pydantic import BaseModel, ConfigDict, Field

from cfb_data_recipes.rosters import RosterMembership, rosters


class PlayerSeasonStatistic(BaseModel):
    """Preserve one long-form player statistic in source order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat_type: str = Field(json_schema_extra={"semantic_type": "dimension"})
    stat: str = Field(
        description="Source display statistic preserved without coercion.",
        json_schema_extra={"semantic_type": "text"},
    )
    source_conference: str = Field(json_schema_extra={"semantic_type": "dimension"})
    source_ordinal: int = Field(ge=0)


class PlayerSeason(BaseModel):
    """Represent one athlete/team/season union membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    season: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    source_team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    team_id: int | None = Field(
        default=None,
        gt=0,
        description="Stable team ID only when temporal evidence is unique.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    team_identity_status: TeamIdentityStatus
    team_identity_candidate_ids: list[int] = Field(
        json_schema_extra={"semantic_type": "identifier"}
    )
    athlete_id: str = Field(json_schema_extra={"semantic_type": "identifier"})
    athlete_name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    position: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    roster_present: bool
    statistics_present: bool
    roster: RosterMembership | None = Field(
        default=None,
        description="Complete validated roster membership when present.",
    )
    statistics: list[PlayerSeasonStatistic] = Field(
        description="Ordered source display statistics for the athlete season."
    )


@step(
    id="cfbd.player_seasons.compose",
    revision=1,
    output=PlayerSeason,
    deterministic=True,
)
def compose_player_seasons(
    season: int,
    memberships: list[RosterMembership],
    statistics: list[PlayerStat],
    teams: list[Team],
) -> list[PlayerSeason]:
    """Union roster and statistic athletes with explicit identity evidence.

    :param season: Requested player season.
    :param memberships: Validated output of the public Rosters recipe.
    :param statistics: Validated long-form player statistics.
    :param teams: Validated temporal team identity evidence.
    :return: Union athlete memberships in deterministic team/athlete order.
    :raises ValueError: If source keys or athlete attributes conflict.
    """
    identity_index = TeamIdentityIndex(teams)
    roster_by_key: dict[tuple[str, str], RosterMembership] = {}
    source_team_by_key: dict[tuple[str, str], str] = {}
    for roster_membership in memberships:
        key = (
            _identity_text(roster_membership.source_team),
            roster_membership.athlete_id,
        )
        if key in roster_by_key:
            raise ValueError("Roster memberships contain duplicate athlete keys")
        roster_by_key[key] = roster_membership
        source_team_by_key[key] = roster_membership.source_team

    stats_by_key: dict[tuple[str, str], list[PlayerSeasonStatistic]] = {}
    stat_identity: dict[tuple[str, str], tuple[str, str]] = {}
    observed_stat_keys: set[tuple[str, str, str, str]] = set()
    for ordinal, statistic in enumerate(statistics):
        if statistic.season != season:
            raise ValueError("Player statistics contain a different season")
        key = (_identity_text(statistic.team), statistic.player_id)
        stat_key = (*key, statistic.category, statistic.stat_type)
        if stat_key in observed_stat_keys:
            raise ValueError("Player statistics contain duplicate candidate keys")
        observed_stat_keys.add(stat_key)
        identity = (statistic.player, statistic.position)
        previous_identity = stat_identity.get(key)
        if previous_identity is not None and previous_identity != identity:
            raise ValueError("Player statistics disagree on athlete identity")
        stat_identity[key] = identity
        source_team_by_key.setdefault(key, statistic.team)
        stats_by_key.setdefault(key, []).append(
            PlayerSeasonStatistic(
                category=statistic.category,
                stat_type=statistic.stat_type,
                stat=statistic.stat,
                source_conference=statistic.conference,
                source_ordinal=ordinal,
            )
        )

    rows: list[PlayerSeason] = []
    for key in set(roster_by_key) | set(stats_by_key):
        selected_membership = roster_by_key.get(key)
        source_team = source_team_by_key[key]
        if selected_membership is None:
            evidence = identity_index.resolve(source_team)
            resolved_name, stats_position = stat_identity[key]
            resolved_position: str | None = stats_position
        else:
            evidence = identity_index.resolve(selected_membership.source_team)
            resolved_name = " ".join(
                part
                for part in (
                    selected_membership.first_name,
                    selected_membership.last_name,
                )
                if part
            )
            resolved_position = selected_membership.position
        rows.append(
            PlayerSeason(
                season=season,
                source_team=source_team,
                team_id=evidence.team_id,
                team_identity_status=evidence.status,
                team_identity_candidate_ids=list(evidence.candidate_ids),
                athlete_id=key[1],
                athlete_name=resolved_name,
                position=resolved_position,
                roster_present=selected_membership is not None,
                statistics_present=key in stats_by_key,
                roster=selected_membership,
                statistics=stats_by_key.get(key, []),
            )
        )
    return sorted(
        rows,
        key=lambda row: (row.season, row.source_team.casefold(), row.athlete_id),
    )


@dataset(
    id="cfbd.player_seasons",
    revision=1,
    row=PlayerSeason,
    grain="one athlete/source-team/season union membership",
    keys=("season", "source_team", "athlete_id"),
    order_by=("season", "source_team", "athlete_id"),
    partition_by=("season",),
)
def player_seasons(
    *,
    season: int,
    team: str | None = None,
    conference: str | None = None,
    classification: Classification | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    season_type: SeasonType | None = None,
    category: str | None = None,
) -> RecipeRef[list[PlayerSeason]]:
    """Build the union of roster and season-stat athlete memberships.

    :param season: Required roster and statistics season.
    :param team: Optional team selector.
    :param conference: Optional statistics conference selector.
    :param classification: Optional roster classification selector.
    :param start_week: Optional inclusive statistics starting week.
    :param end_week: Optional inclusive statistics ending week.
    :param season_type: Optional statistics season phase.
    :param category: Optional source statistic-category selector.
    :return: A reference to the validated player-seasons dataset.
    """
    return compose_player_seasons(
        season,
        rosters(season=season, team=team, classification=classification),
        player_season_stats(
            year=season,
            conference=conference,
            team=team,
            start_week=start_week,
            end_week=end_week,
            season_type=season_type,
            category=category,
        ),
        teams_source(year=season),
    )


def _identity_text(value: str) -> str:
    return " ".join(value.split()).casefold()


__all__ = ["PlayerSeason", "PlayerSeasonStatistic", "player_seasons"]
