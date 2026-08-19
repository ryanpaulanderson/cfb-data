"""Provide the independently authored player-seasons dataset recipe.

``player_seasons`` composes the public ``rosters`` dataset with the public
long-form player-season statistics and temporal Teams source. It unions their
athlete memberships so roster-only and stats-only athletes survive, while
display statistics remain ordered strings rather than inferred numbers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum

from cfb_data.adjusted_metrics.models.pydantic.responses import (
    KickerPAAR,
    PlayerWeightedEPA,
)
from cfb_data.adjusted_metrics.sources import (
    adjusted_player_passing,
    adjusted_player_rushing,
    kicker_paar_metrics,
)
from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics.models.pydantic.responses import PlayerSeasonPredictedPointsAdded
from cfb_data.metrics.sources import player_season_ppa
from cfb_data.players.models.pydantic.responses import PlayerUsage
from cfb_data.players.sources import player_usage
from cfb_data.stats.models.pydantic.responses import (
    PlayerSeasonSuccessRate,
    PlayerStat,
)
from cfb_data.stats.sources import (
    player_season_stats,
    player_season_success,
)
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


class PlayerSeasonCoverage(StrEnum):
    """Describe whether a requested player enrichment produced a row."""

    not_requested = "not_requested"
    empty = "empty"
    present = "present"


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
    usage_coverage: PlayerSeasonCoverage = Field(
        description="Explicit player-usage enrichment availability."
    )
    usage: PlayerUsage | None = Field(
        default=None,
        description="Source player-usage metrics when requested and present.",
    )
    ppa_coverage: PlayerSeasonCoverage = Field(
        description="Explicit player-PPA enrichment availability."
    )
    ppa: PlayerSeasonPredictedPointsAdded | None = Field(
        default=None,
        description="Source player-season PPA when requested and present.",
    )
    success_coverage: PlayerSeasonCoverage = Field(
        description="Explicit player-success enrichment availability."
    )
    success: PlayerSeasonSuccessRate | None = Field(
        default=None,
        description="Source player success rates when requested and present.",
    )
    passing_wepa_coverage: PlayerSeasonCoverage = Field(
        description="Explicit adjusted passing EPA availability."
    )
    passing_wepa: PlayerWeightedEPA | None = Field(
        default=None,
        description="Source opponent-adjusted passing EPA when requested.",
    )
    rushing_wepa_coverage: PlayerSeasonCoverage = Field(
        description="Explicit adjusted rushing EPA availability."
    )
    rushing_wepa: PlayerWeightedEPA | None = Field(
        default=None,
        description="Source opponent-adjusted rushing EPA when requested.",
    )
    kicker_paar_coverage: PlayerSeasonCoverage = Field(
        description="Explicit kicker PAAR availability."
    )
    kicker_paar: KickerPAAR | None = Field(
        default=None,
        description="Source kicker points above replacement when requested.",
    )


@step(
    id="cfbd.player_seasons.compose",
    revision=2,
    output=PlayerSeason,
    deterministic=True,
)
def compose_player_seasons(
    season: int,
    memberships: list[RosterMembership],
    statistics: list[PlayerStat],
    teams: list[Team],
    *,
    usage: list[PlayerUsage] | None,
    ppa: list[PlayerSeasonPredictedPointsAdded] | None,
    success: list[PlayerSeasonSuccessRate] | None,
    passing_wepa: list[PlayerWeightedEPA] | None,
    rushing_wepa: list[PlayerWeightedEPA] | None,
    kicker_paar: list[KickerPAAR] | None,
) -> list[PlayerSeason]:
    """Union roster and statistic athletes with explicit identity evidence.

    :param season: Requested player season.
    :param memberships: Validated output of the public Rosters recipe.
    :param statistics: Validated long-form player statistics.
    :param teams: Validated temporal team identity evidence.
    :param usage: Requested player-usage rows, or ``None`` when omitted.
    :param ppa: Requested player-season PPA rows, or ``None`` when omitted.
    :param success: Requested player-success rows, or ``None`` when omitted.
    :param passing_wepa: Requested adjusted passing rows, or ``None``.
    :param rushing_wepa: Requested adjusted rushing rows, or ``None``.
    :param kicker_paar: Requested kicker PAAR rows, or ``None``.
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

    base_keys = set(roster_by_key) | set(stats_by_key)
    usage_by_key = _index_enrichment(
        usage,
        base_keys=base_keys,
        season=season,
        label="Player usage",
        identity=lambda row: (row.season, row.team, row.id),
    )
    ppa_by_key = _index_enrichment(
        ppa,
        base_keys=base_keys,
        season=season,
        label="Player PPA",
        identity=lambda row: (row.season, row.team, row.id),
    )
    success_by_key = _index_enrichment(
        success,
        base_keys=base_keys,
        season=season,
        label="Player success",
        identity=lambda row: (row.season, row.team, row.id),
    )
    passing_wepa_by_key = _index_enrichment(
        passing_wepa,
        base_keys=base_keys,
        season=season,
        label="Passing WEPA",
        identity=lambda row: (row.year, row.team, row.athlete_id),
    )
    rushing_wepa_by_key = _index_enrichment(
        rushing_wepa,
        base_keys=base_keys,
        season=season,
        label="Rushing WEPA",
        identity=lambda row: (row.year, row.team, row.athlete_id),
    )
    kicker_paar_by_key = _index_enrichment(
        kicker_paar,
        base_keys=base_keys,
        season=season,
        label="Kicker PAAR",
        identity=lambda row: (row.year, row.team, row.athlete_id),
    )

    rows: list[PlayerSeason] = []
    for key in base_keys:
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
                usage_coverage=_coverage_for(key, usage_by_key),
                usage=usage_by_key.get(key) if usage_by_key is not None else None,
                ppa_coverage=_coverage_for(key, ppa_by_key),
                ppa=ppa_by_key.get(key) if ppa_by_key is not None else None,
                success_coverage=_coverage_for(key, success_by_key),
                success=(
                    success_by_key.get(key) if success_by_key is not None else None
                ),
                passing_wepa_coverage=_coverage_for(key, passing_wepa_by_key),
                passing_wepa=(
                    passing_wepa_by_key.get(key)
                    if passing_wepa_by_key is not None
                    else None
                ),
                rushing_wepa_coverage=_coverage_for(key, rushing_wepa_by_key),
                rushing_wepa=(
                    rushing_wepa_by_key.get(key)
                    if rushing_wepa_by_key is not None
                    else None
                ),
                kicker_paar_coverage=_coverage_for(key, kicker_paar_by_key),
                kicker_paar=(
                    kicker_paar_by_key.get(key)
                    if kicker_paar_by_key is not None
                    else None
                ),
            )
        )
    return sorted(
        rows,
        key=lambda row: (row.season, row.source_team.casefold(), row.athlete_id),
    )


@dataset(
    id="cfbd.player_seasons",
    revision=2,
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
    position: str | None = None,
    threshold: int | None = None,
    exclude_garbage_time: bool | None = None,
    include_usage: bool = False,
    include_ppa: bool = False,
    include_success: bool = False,
    include_passing_wepa: bool = False,
    include_rushing_wepa: bool = False,
    include_kicker_paar: bool = False,
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
    :param position: Optional usage and PPA position selector.
    :param threshold: Optional PPA and success play threshold.
    :param exclude_garbage_time: Optional enrichment source policy.
    :param include_usage: Request player-usage metrics.
    :param include_ppa: Request player-season PPA metrics.
    :param include_success: Request player success-rate metrics.
    :param include_passing_wepa: Request opponent-adjusted passing EPA.
    :param include_rushing_wepa: Request opponent-adjusted rushing EPA.
    :param include_kicker_paar: Request kicker points above replacement.
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
        usage=(
            player_usage(
                year=season,
                conference=conference,
                position=position,
                team=team,
                exclude_garbage_time=exclude_garbage_time,
            )
            if include_usage
            else None
        ),
        ppa=(
            player_season_ppa(
                year=season,
                conference=conference,
                team=team,
                position=position,
                threshold=threshold,
                exclude_garbage_time=exclude_garbage_time,
            )
            if include_ppa
            else None
        ),
        success=(
            player_season_success(
                year=season,
                conference=conference,
                team=team,
                season_type=season_type,
                start_week=start_week,
                end_week=end_week,
                threshold=threshold,
                exclude_garbage_time=exclude_garbage_time,
            )
            if include_success
            else None
        ),
        passing_wepa=(
            adjusted_player_passing(
                year=season,
                conference=conference,
                team=team,
                position=position,
            )
            if include_passing_wepa
            else None
        ),
        rushing_wepa=(
            adjusted_player_rushing(
                year=season,
                conference=conference,
                team=team,
                position=position,
            )
            if include_rushing_wepa
            else None
        ),
        kicker_paar=(
            kicker_paar_metrics(year=season, conference=conference, team=team)
            if include_kicker_paar
            else None
        ),
    )


def _identity_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _index_enrichment[EnrichmentT](
    rows: list[EnrichmentT] | None,
    *,
    base_keys: set[tuple[str, str]],
    season: int,
    label: str,
    identity: Callable[[EnrichmentT], tuple[int, str, str]],
) -> dict[tuple[str, str], EnrichmentT] | None:
    """Index optional player evidence without expanding the base universe.

    :param rows: Requested source rows, or ``None`` when omitted.
    :param base_keys: Authoritative roster/stat union keys.
    :param season: Requested player season.
    :param label: Safe enrichment label for validation errors.
    :param identity: Extract the source season, team, and athlete ID.
    :return: Indexed evidence, or ``None`` when not requested.
    :raises ValueError: If evidence is duplicated or outside the base universe.
    """
    if rows is None:
        return None
    indexed: dict[tuple[str, str], EnrichmentT] = {}
    for row in rows:
        row_season, row_team, row_id = identity(row)
        if row_season != season:
            raise ValueError(f"{label} contains a different season")
        key = (_identity_text(row_team), row_id)
        if key not in base_keys:
            raise ValueError(f"{label} falls outside the player-season universe")
        if key in indexed:
            raise ValueError(f"{label} contains duplicate athlete keys")
        indexed[key] = row
    return indexed


def _coverage_for(
    key: tuple[str, str],
    rows: Mapping[tuple[str, str], object] | None,
) -> PlayerSeasonCoverage:
    """Return explicit per-athlete enrichment availability.

    :param key: Authoritative player-season key.
    :param rows: Requested indexed rows, or ``None`` when omitted.
    :return: Not-requested, empty, or present coverage.
    """
    if rows is None:
        return PlayerSeasonCoverage.not_requested
    return PlayerSeasonCoverage.present if key in rows else PlayerSeasonCoverage.empty


__all__ = [
    "PlayerSeason",
    "PlayerSeasonCoverage",
    "PlayerSeasonStatistic",
    "player_seasons",
]
