"""Provide the independently authored team-seasons dataset recipe.

``team_seasons`` uses ``/records`` as its authoritative row universe. Common
and advanced season statistics are required validated enrichments attached by
season-scoped team identity. Dynamic conventional statistics remain ordered
typed records rather than being implicitly pivoted into a changing schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from cfb_data.adjusted_metrics.models.pydantic.responses import AdjustedTeamMetrics
from cfb_data.adjusted_metrics.sources import adjusted_team_metrics
from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.games.models.pydantic.responses import TeamRecord, TeamRecords
from cfb_data.games.sources import team_records
from cfb_data.metrics.models.pydantic.responses import TeamSeasonPredictedPointsAdded
from cfb_data.metrics.sources import team_season_ppa
from cfb_data.players.models.pydantic.responses import ReturningProduction
from cfb_data.players.sources import returning_production
from cfb_data.ratings.models.pydantic.responses import (
    TeamCoreRating,
    TeamElo,
    TeamFPI,
    TeamSP,
    TeamSRS,
)
from cfb_data.ratings.sources import (
    core_ratings,
    elo_ratings,
    fpi_ratings,
    sp_ratings,
    srs_ratings,
)
from cfb_data.stats.models.pydantic.responses import AdvancedSeasonStat, TeamStat
from cfb_data.stats.sources import advanced_season_stats, team_season_stats
from cfb_data.teams.models.pydantic.responses import TeamATS, TeamTalent
from cfb_data.teams.sources import team_ats, team_talent
from pydantic import BaseModel, ConfigDict, Field


class TeamSeasonStatistic(BaseModel):
    """Preserve one dynamic conventional statistic in source order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    value: str | int | float = Field(json_schema_extra={"semantic_type": "measure"})
    source_conference: str = Field(json_schema_extra={"semantic_type": "dimension"})
    source_ordinal: int = Field(ge=0)


class TeamSeasonCoverage(StrEnum):
    """Describe whether an optional team-season enrichment produced evidence."""

    not_requested = "not_requested"
    empty = "empty"
    present = "present"


class _TeamRating(Protocol):
    """Describe identity fields shared by attachable team ratings."""

    @property
    def year(self) -> int: ...

    @property
    def team(self) -> str: ...

    @property
    def conference(self) -> str | None: ...


class TeamSeason(BaseModel):
    """Represent one team season established by the records source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    season: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    team_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    team: str = Field(json_schema_extra={"semantic_type": "dimension"})
    classification: Classification | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    conference: str = Field(json_schema_extra={"semantic_type": "dimension"})
    division: str = Field(json_schema_extra={"semantic_type": "dimension"})
    expected_wins: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "wins"},
    )
    total: TeamRecord
    conference_games: TeamRecord
    home_games: TeamRecord
    away_games: TeamRecord
    neutral_site_games: TeamRecord
    regular_season: TeamRecord
    postseason: TeamRecord
    statistics: list[TeamSeasonStatistic] = Field(
        description="Ordered, source-faithful conventional season statistics."
    )
    advanced: AdvancedSeasonStat = Field(
        description="Validated nested advanced offense and defense metrics."
    )
    ppa_coverage: TeamSeasonCoverage = Field(
        description="Explicit team-season PPA enrichment availability."
    )
    ppa: TeamSeasonPredictedPointsAdded | None = Field(
        default=None,
        description="Source team-season PPA metrics when requested.",
    )
    talent_coverage: TeamSeasonCoverage = Field(
        description="Explicit team-talent enrichment availability."
    )
    talent: TeamTalent | None = Field(
        default=None,
        description="Source 247Sports team-talent composite when requested.",
    )
    ats_coverage: TeamSeasonCoverage = Field(
        description="Explicit against-the-spread enrichment availability."
    )
    ats: TeamATS | None = Field(
        default=None,
        description="Source against-the-spread season record when requested.",
    )
    returning_production_coverage: TeamSeasonCoverage = Field(
        description="Explicit returning-production enrichment availability."
    )
    returning_production: ReturningProduction | None = Field(
        default=None,
        description="Source team returning-production metrics when requested.",
    )
    core_rating_coverage: TeamSeasonCoverage = Field(
        description="Explicit CORE-rating enrichment availability."
    )
    core_rating: TeamCoreRating | None = Field(
        default=None,
        description="Source CORE rating when requested.",
    )
    sp_rating_coverage: TeamSeasonCoverage = Field(
        description="Explicit SP+ enrichment availability."
    )
    sp_rating: TeamSP | None = Field(
        default=None,
        description="Source team SP+ rating when requested.",
    )
    srs_rating_coverage: TeamSeasonCoverage = Field(
        description="Explicit SRS enrichment availability."
    )
    srs_rating: TeamSRS | None = Field(
        default=None,
        description="Source Simple Rating System result when requested.",
    )
    elo_rating_coverage: TeamSeasonCoverage = Field(
        description="Explicit Elo enrichment availability."
    )
    elo_rating: TeamElo | None = Field(
        default=None,
        description="Source Elo result for the requested period.",
    )
    fpi_rating_coverage: TeamSeasonCoverage = Field(
        description="Explicit FPI enrichment availability."
    )
    fpi_rating: TeamFPI | None = Field(
        default=None,
        description="Source Football Power Index result when requested.",
    )
    adjusted_metrics_coverage: TeamSeasonCoverage = Field(
        description="Explicit opponent-adjusted metric availability."
    )
    adjusted_metrics: AdjustedTeamMetrics | None = Field(
        default=None,
        description="Source opponent-adjusted team metrics when requested.",
    )


@step(
    id="cfbd.team_seasons.compose",
    revision=5,
    output=TeamSeason,
    deterministic=True,
)
def compose_team_seasons(
    records: list[TeamRecords],
    statistics: list[TeamStat],
    advanced: list[AdvancedSeasonStat],
    *,
    ppa: list[TeamSeasonPredictedPointsAdded] | None,
    talent: list[TeamTalent] | None,
    ats: list[TeamATS] | None,
    returning: list[ReturningProduction] | None,
    core: list[TeamCoreRating] | None,
    sp: list[TeamSP] | None,
    srs: list[TeamSRS] | None,
    elo: list[TeamElo] | None,
    fpi: list[TeamFPI] | None,
    adjusted: list[AdjustedTeamMetrics] | None,
) -> list[TeamSeason]:
    """Attach required season statistics to the records-defined universe.

    :param records: Validated authoritative team-season rows.
    :param statistics: Validated dynamic conventional statistics.
    :param advanced: Validated nested advanced season metrics.
    :param ppa: Requested team-season PPA rows, or ``None`` when omitted.
    :param talent: Requested team-talent rows, or ``None`` when omitted.
    :param ats: Requested against-the-spread rows, or ``None`` when omitted.
    :param returning: Requested returning-production rows, or ``None``.
    :param core: Requested CORE ratings, or ``None`` when omitted.
    :param sp: Requested team SP+ ratings, or ``None`` when omitted.
    :param srs: Requested SRS ratings, or ``None`` when omitted.
    :param elo: Requested Elo ratings, or ``None`` when omitted.
    :param fpi: Requested FPI ratings, or ``None`` when omitted.
    :param adjusted: Requested opponent-adjusted metrics, or ``None``.
    :return: Complete team seasons in stable season/team-ID order.
    :raises ValueError: If identity, coverage, or statistic keys are ambiguous.
    """
    record_keys: dict[tuple[int, str], TeamRecords] = {}
    for record in records:
        key = (record.year, _identity_text(record.team))
        if key in record_keys:
            raise ValueError("Records contain ambiguous season/team identity")
        record_keys[key] = record

    conventional: dict[tuple[int, str], list[TeamSeasonStatistic]] = {
        key: [] for key in record_keys
    }
    observed_stat_keys: set[tuple[int, str, str]] = set()
    for ordinal, conventional_statistic in enumerate(statistics):
        key = (
            conventional_statistic.season,
            _identity_text(conventional_statistic.team),
        )
        if key not in conventional:
            continue
        stat_key = (*key, conventional_statistic.stat_name)
        if stat_key in observed_stat_keys:
            raise ValueError("Conventional statistics contain duplicate keys")
        observed_stat_keys.add(stat_key)
        conventional[key].append(
            TeamSeasonStatistic(
                name=conventional_statistic.stat_name,
                value=conventional_statistic.stat_value,
                source_conference=conventional_statistic.conference,
                source_ordinal=ordinal,
            )
        )

    advanced_by_key: dict[tuple[int, str], AdvancedSeasonStat] = {}
    for advanced_statistic in advanced:
        key = (advanced_statistic.season, _identity_text(advanced_statistic.team))
        if key not in record_keys:
            continue
        if key in advanced_by_key:
            raise ValueError("Advanced statistics contain duplicate team seasons")
        advanced_by_key[key] = advanced_statistic

    ppa_by_key: dict[tuple[int, str], TeamSeasonPredictedPointsAdded] | None = None
    if ppa is not None:
        ppa_by_key = {}
        for ppa_statistic in ppa:
            key = (ppa_statistic.season, _identity_text(ppa_statistic.team))
            if key not in record_keys:
                raise ValueError("Team-season PPA falls outside the records universe")
            if key in ppa_by_key:
                raise ValueError("Team-season PPA contains duplicate team seasons")
            record = record_keys[key]
            if ppa_statistic.conference != record.conference:
                raise ValueError("Team-season PPA conflicts with record conference")
            ppa_by_key[key] = ppa_statistic
        if ppa_by_key and set(ppa_by_key) != set(record_keys):
            raise ValueError("Requested team-season PPA is incomplete")

    talent_by_key = _index_talent(record_keys, talent)
    ats_by_key = _index_ats(record_keys, ats)
    returning_by_key = _index_returning(record_keys, returning)
    core_by_key = _index_rating(record_keys, core, label="CORE ratings")
    sp_by_key = _index_rating(record_keys, sp, label="SP+ ratings")
    srs_by_key = _index_rating(record_keys, srs, label="SRS ratings")
    elo_by_key = _index_rating(record_keys, elo, label="Elo ratings")
    fpi_by_key = _index_rating(record_keys, fpi, label="FPI ratings")
    adjusted_by_key = _index_adjusted(record_keys, adjusted)

    rows: list[TeamSeason] = []
    for key, record in record_keys.items():
        if not conventional[key]:
            raise ValueError(
                "Conventional statistics do not cover the records universe"
            )
        attached_advanced = advanced_by_key.get(key)
        if attached_advanced is None:
            raise ValueError("Advanced statistics do not cover the records universe")
        rows.append(
            TeamSeason(
                season=record.year,
                team_id=record.team_id,
                team=record.team,
                classification=record.classification,
                conference=record.conference,
                division=record.division,
                expected_wins=record.expected_wins,
                total=record.total,
                conference_games=record.conference_games,
                home_games=record.home_games,
                away_games=record.away_games,
                neutral_site_games=record.neutral_site_games,
                regular_season=record.regular_season,
                postseason=record.postseason,
                statistics=conventional[key],
                advanced=attached_advanced,
                ppa_coverage=(
                    TeamSeasonCoverage.not_requested
                    if ppa_by_key is None
                    else (
                        TeamSeasonCoverage.present
                        if key in ppa_by_key
                        else TeamSeasonCoverage.empty
                    )
                ),
                ppa=ppa_by_key.get(key) if ppa_by_key is not None else None,
                talent_coverage=_coverage(talent_by_key, key),
                talent=(talent_by_key.get(key) if talent_by_key is not None else None),
                ats_coverage=_coverage(ats_by_key, key),
                ats=ats_by_key.get(key) if ats_by_key is not None else None,
                returning_production_coverage=_coverage(returning_by_key, key),
                returning_production=(
                    returning_by_key.get(key) if returning_by_key is not None else None
                ),
                core_rating_coverage=_coverage(core_by_key, key),
                core_rating=core_by_key.get(key) if core_by_key is not None else None,
                sp_rating_coverage=_coverage(sp_by_key, key),
                sp_rating=sp_by_key.get(key) if sp_by_key is not None else None,
                srs_rating_coverage=_coverage(srs_by_key, key),
                srs_rating=srs_by_key.get(key) if srs_by_key is not None else None,
                elo_rating_coverage=_coverage(elo_by_key, key),
                elo_rating=elo_by_key.get(key) if elo_by_key is not None else None,
                fpi_rating_coverage=_coverage(fpi_by_key, key),
                fpi_rating=fpi_by_key.get(key) if fpi_by_key is not None else None,
                adjusted_metrics_coverage=_coverage(adjusted_by_key, key),
                adjusted_metrics=(
                    adjusted_by_key.get(key) if adjusted_by_key is not None else None
                ),
            )
        )
    return sorted(rows, key=lambda row: (row.season, row.team_id))


@dataset(
    id="cfbd.team_seasons",
    revision=5,
    row=TeamSeason,
    grain="one team season established by the records source",
    keys=("season", "team_id"),
    order_by=("season", "team_id"),
    partition_by=("season",),
)
def team_seasons(
    *,
    season: int,
    team: str | None = None,
    conference: str | None = None,
    classification: Classification | None = None,
    start_week: int | None = None,
    end_week: int | None = None,
    exclude_garbage_time: bool | None = None,
    include_ppa: bool = False,
    include_talent: bool = False,
    include_ats: bool = False,
    include_returning_production: bool = False,
    include_core_rating: bool = False,
    include_sp_rating: bool = False,
    include_srs_rating: bool = False,
    include_elo_rating: bool = False,
    elo_week: int | None = None,
    elo_season_type: SeasonType | None = None,
    include_fpi_rating: bool = False,
    include_adjusted_metrics: bool = False,
) -> RecipeRef[list[TeamSeason]]:
    """Build complete team-season records and core statistics.

    :param season: Required season year.
    :param team: Optional team selector.
    :param conference: Optional records and conventional-stat selector.
    :param classification: Optional statistics classification selector.
    :param start_week: Optional inclusive statistics starting week.
    :param end_week: Optional inclusive statistics ending week.
    :param exclude_garbage_time: Optional advanced-statistics source policy.
    :param include_ppa: Request team-season predicted-points-added metrics.
    :param include_talent: Request the season's team-talent composites.
    :param include_ats: Request team against-the-spread records.
    :param include_returning_production: Request team returning-production metrics.
    :param include_core_rating: Request the CORE rating.
    :param include_sp_rating: Request the team SP+ rating.
    :param include_srs_rating: Request the Simple Rating System result.
    :param include_elo_rating: Request Elo for the declared period.
    :param elo_week: Optional week cutoff for requested Elo.
    :param elo_season_type: Optional season phase for requested Elo.
    :param include_fpi_rating: Request the Football Power Index result.
    :param include_adjusted_metrics: Request opponent-adjusted team metrics.
    :return: A reference to the validated team-seasons dataset.
    :raises ValueError: If Elo period selectors are supplied without Elo.
    """
    if (elo_week is not None or elo_season_type is not None) and not include_elo_rating:
        raise ValueError("Elo period selectors require include_elo_rating=True")
    return compose_team_seasons(
        team_records(year=season, team=team, conference=conference),
        team_season_stats(
            year=season,
            team=team,
            conference=conference,
            start_week=start_week,
            end_week=end_week,
            classification=classification,
        ),
        advanced_season_stats(
            year=season,
            team=team,
            exclude_garbage_time=exclude_garbage_time,
            start_week=start_week,
            end_week=end_week,
            classification=classification,
        ),
        ppa=(
            team_season_ppa(
                year=season,
                team=team,
                conference=conference,
                exclude_garbage_time=exclude_garbage_time,
                classification=classification,
            )
            if include_ppa
            else None
        ),
        talent=team_talent(year=season) if include_talent else None,
        ats=(
            team_ats(year=season, team=team, conference=conference)
            if include_ats
            else None
        ),
        returning=(
            returning_production(
                year=season,
                team=team,
                conference=conference,
            )
            if include_returning_production
            else None
        ),
        core=(
            core_ratings(year=season, team=team, conference=conference)
            if include_core_rating
            else None
        ),
        sp=sp_ratings(year=season, team=team) if include_sp_rating else None,
        srs=(
            srs_ratings(year=season, team=team, conference=conference)
            if include_srs_rating
            else None
        ),
        elo=(
            elo_ratings(
                year=season,
                week=elo_week,
                season_type=elo_season_type,
                team=team,
                conference=conference,
            )
            if include_elo_rating
            else None
        ),
        fpi=(
            fpi_ratings(year=season, team=team, conference=conference)
            if include_fpi_rating
            else None
        ),
        adjusted=(
            adjusted_team_metrics(year=season, team=team, conference=conference)
            if include_adjusted_metrics
            else None
        ),
    )


def _identity_text(value: str) -> str:
    """Return the comparison identity used within one validated season.

    :param value: Source-provided team name.
    :return: Whitespace-normalized, case-insensitive text.
    """
    return " ".join(value.split()).casefold()


def _index_talent(
    records: dict[tuple[int, str], TeamRecords],
    talent: list[TeamTalent] | None,
) -> dict[tuple[int, str], TeamTalent] | None:
    """Index name-only talent inside the records-defined season universe.

    The upstream talent route has no team selector or stable team ID. Rows
    outside the requested records universe are therefore an explicit unmatched
    right side of this enrichment join; they cannot add base rows.

    :param records: Authoritative team-season records keyed within season.
    :param talent: Requested source rows, or ``None`` when omitted.
    :return: Matching talent by records identity, or ``None`` when omitted.
    :raises ValueError: If matches are duplicated or non-empty coverage is partial.
    """
    if talent is None:
        return None
    indexed: dict[tuple[int, str], TeamTalent] = {}
    for item in talent:
        key = (item.year, _identity_text(item.team))
        if key not in records:
            continue
        if key in indexed:
            raise ValueError("Team talent contains duplicate team seasons")
        indexed[key] = item
    if talent and set(indexed) != set(records):
        raise ValueError("Requested team talent is incomplete")
    return indexed


def _index_ats(
    records: dict[tuple[int, str], TeamRecords],
    ats: list[TeamATS] | None,
) -> dict[tuple[int, str], TeamATS] | None:
    """Index ATS by stable team ID before validating display identity.

    :param records: Authoritative team-season records keyed within season.
    :param ats: Requested source rows, or ``None`` when omitted.
    :return: Matching ATS rows by records identity, or ``None`` when omitted.
    :raises ValueError: If identity conflicts, duplicates, or coverage is partial.
    """
    if ats is None:
        return None
    records_by_id = {
        (record.year, record.team_id): (key, record) for key, record in records.items()
    }
    indexed: dict[tuple[int, str], TeamATS] = {}
    for item in ats:
        match = records_by_id.get((item.year, item.team_id))
        if match is None:
            continue
        key, record = match
        if _identity_text(item.team) != _identity_text(record.team) or (
            item.conference is not None and item.conference != record.conference
        ):
            raise ValueError("Team ATS conflicts with records identity")
        if key in indexed:
            raise ValueError("Team ATS contains duplicate team seasons")
        indexed[key] = item
    if ats and set(indexed) != set(records):
        raise ValueError("Requested team ATS is incomplete")
    return indexed


def _index_returning(
    records: dict[tuple[int, str], TeamRecords],
    returning: list[ReturningProduction] | None,
) -> dict[tuple[int, str], ReturningProduction] | None:
    """Index returning production inside the records-defined season.

    :param records: Authoritative team-season records keyed within season.
    :param returning: Requested source rows, or ``None`` when omitted.
    :return: Matching returning metrics by records identity, or ``None``.
    :raises ValueError: If identity conflicts, duplicates, or coverage is partial.
    """
    if returning is None:
        return None
    indexed: dict[tuple[int, str], ReturningProduction] = {}
    for item in returning:
        key = (item.season, _identity_text(item.team))
        record = records.get(key)
        if record is None:
            raise ValueError("Returning production falls outside the records universe")
        if item.conference != record.conference:
            raise ValueError("Returning production conflicts with record conference")
        if key in indexed:
            raise ValueError("Returning production contains duplicate team seasons")
        indexed[key] = item
    if returning and set(indexed) != set(records):
        raise ValueError("Requested returning production is incomplete")
    return indexed


def _index_rating[RatingT: _TeamRating](
    records: dict[tuple[int, str], TeamRecords],
    ratings: list[RatingT] | None,
    *,
    label: str,
) -> dict[tuple[int, str], RatingT] | None:
    """Index one rating type within the records-defined season.

    Rating endpoints may return aggregate or other-team rows even with a team
    selector. Those are an explicit unmatched right side and cannot alter the
    records universe.

    :param records: Authoritative team-season records keyed within season.
    :param ratings: Requested source rows, or ``None`` when omitted.
    :param label: Safe rating label for validation errors.
    :return: Matching ratings by records identity, or ``None`` when omitted.
    :raises ValueError: If identity conflicts, duplicates, or coverage is partial.
    """
    if ratings is None:
        return None
    indexed: dict[tuple[int, str], RatingT] = {}
    for item in ratings:
        key = (item.year, _identity_text(item.team))
        record = records.get(key)
        if record is None:
            continue
        if item.conference is not None and item.conference != record.conference:
            raise ValueError(f"{label} conflict with record conference")
        if key in indexed:
            raise ValueError(f"{label} contain duplicate team seasons")
        indexed[key] = item
    if ratings and set(indexed) != set(records):
        raise ValueError(f"Requested {label} are incomplete")
    return indexed


def _index_adjusted(
    records: dict[tuple[int, str], TeamRecords],
    adjusted: list[AdjustedTeamMetrics] | None,
) -> dict[tuple[int, str], AdjustedTeamMetrics] | None:
    """Attach adjusted metrics by stable team ID within the records season.

    :param records: Authoritative team-season records keyed within season.
    :param adjusted: Requested adjusted rows, or ``None`` when omitted.
    :return: Matching metrics by records identity, or ``None`` when omitted.
    :raises ValueError: If identity conflicts, duplicates, or coverage is partial.
    """
    if adjusted is None:
        return None
    record_keys_by_id = {
        (record.year, record.team_id): key for key, record in records.items()
    }
    indexed: dict[tuple[int, str], AdjustedTeamMetrics] = {}
    for item in adjusted:
        key = record_keys_by_id.get((item.year, item.team_id))
        if key is None:
            continue
        record = records[key]
        if _identity_text(item.team) != _identity_text(record.team):
            raise ValueError("Adjusted metrics conflict with record team name")
        if item.conference != record.conference:
            raise ValueError("Adjusted metrics conflict with record conference")
        if key in indexed:
            raise ValueError("Adjusted metrics contain duplicate team seasons")
        indexed[key] = item
    if adjusted and set(indexed) != set(records):
        raise ValueError("Requested adjusted metrics are incomplete")
    return indexed


def _coverage[ValueT](
    values: dict[tuple[int, str], ValueT] | None,
    key: tuple[int, str],
) -> TeamSeasonCoverage:
    """Return explicit optional-enrichment coverage for one base key.

    :param values: Requested enrichment index, or ``None`` when omitted.
    :param key: Current records-defined team-season key.
    :return: Not-requested, present, or valid-empty coverage.
    """
    if values is None:
        return TeamSeasonCoverage.not_requested
    if key in values:
        return TeamSeasonCoverage.present
    return TeamSeasonCoverage.empty


__all__ = [
    "TeamSeason",
    "TeamSeasonCoverage",
    "TeamSeasonStatistic",
    "team_seasons",
]
