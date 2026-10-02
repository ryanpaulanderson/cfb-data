"""Provide the independently authored team-seasons dataset recipe.

``team_seasons`` uses ``/records`` as its authoritative row universe. Common
and advanced season statistics are required validated enrichments attached by
season-scoped team identity. Dynamic conventional statistics remain ordered
typed records rather than being implicitly pivoted into a changing schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

import narwhals.stable.v2 as nw
from cfb_data.adjusted_metrics.models.pydantic.responses import AdjustedTeamMetrics
from cfb_data.adjusted_metrics.sources import adjusted_team_metrics
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.analytics.tables import SOURCE_ORDINAL
from cfb_data.enums import Classification, SeasonType
from cfb_data.games.models.pydantic.responses import TeamRecord
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
from cfb_data.stats.models.pydantic.responses import AdvancedSeasonStat
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
    revision=6,
    output=TeamSeason,
    deterministic=True,
)
def compose_team_seasons(
    records: Table,
    statistics: Table,
    advanced: Table,
    *,
    ppa: Table | None,
    talent: Table | None,
    ats: Table | None,
    returning: Table | None,
    core: Table | None,
    sp: Table | None,
    srs: Table | None,
    elo: Table | None,
    fpi: Table | None,
    adjusted: Table | None,
) -> Table:
    """Compose the records universe with declared native enrichment policies.

    :param records: Authoritative validated team-season table.
    :param statistics: Long-form conventional statistics.
    :param advanced: Required advanced metrics.
    :param ppa: Optional team-season PPA.
    :param talent: Optional talent evidence.
    :param ats: Optional ATS records.
    :param returning: Optional returning production.
    :param core: Optional CORE rating.
    :param sp: Optional SP+ rating.
    :param srs: Optional SRS rating.
    :param elo: Optional Elo rating.
    :param fpi: Optional FPI rating.
    :param adjusted: Optional adjusted metrics.
    :return: Native team seasons with globally checked row-universe policies.
    """
    keys = ("season", "__team_key")
    base = (
        records.with_columns(nw.col("year").alias("season"))
        .normalize_text("team", into="__team_key")
        .require_unique(keys, message="Records contain ambiguous season/team identity")
    )
    conventional = statistics.normalize_text("team", into="__team_key").join(
        base.distinct(*keys), on=keys, how="semi", cardinality="many_to_one"
    )
    conventional = conventional.require_unique(
        (*keys, "stat_name"), message="Conventional statistics contain duplicate keys"
    )
    conventional = conventional.pack(
        columns={
            "stat_name": "name",
            "stat_value": "value",
            "conference": "source_conference",
            SOURCE_ORDINAL: "source_ordinal",
        },
        into="__statistic",
    )
    grouped = conventional.ordered_records(
        keys=keys,
        column="__statistic",
        into="statistics",
        ordinal_field="source_ordinal",
        keep_ordinal=True,
    ).with_columns(nw.lit(True).alias("__statistics_present"))
    base = base.join(grouped, on=keys, cardinality="one_to_one").require(
        nw.col("__statistics_present").fill_null(False),
        message="Conventional statistics do not cover the records universe",
    )
    context = base.select("season", "team_id", "__team_key", "conference")
    base = _attach_season_source(
        base,
        advanced,
        context=context,
        model=AdvancedSeasonStat,
        output="advanced",
        year_field="season",
        outside="ignore",
        required=True,
    )
    specs: tuple[
        tuple[
            str, Table | None, type[BaseModel], str, bool, Literal["ignore", "reject"]
        ],
        ...,
    ] = (
        ("ppa", ppa, TeamSeasonPredictedPointsAdded, "season", False, "reject"),
        ("talent", talent, TeamTalent, "year", False, "ignore"),
        ("ats", ats, TeamATS, "year", True, "ignore"),
        (
            "returning_production",
            returning,
            ReturningProduction,
            "season",
            False,
            "reject",
        ),
        ("core_rating", core, TeamCoreRating, "year", False, "ignore"),
        ("sp_rating", sp, TeamSP, "year", False, "ignore"),
        ("srs_rating", srs, TeamSRS, "year", False, "ignore"),
        ("elo_rating", elo, TeamElo, "year", False, "ignore"),
        ("fpi_rating", fpi, TeamFPI, "year", False, "ignore"),
        ("adjusted_metrics", adjusted, AdjustedTeamMetrics, "year", True, "ignore"),
    )
    for output, source, model, year_field, stable_id, outside in specs:
        base = _attach_season_source(
            base,
            source,
            context=context,
            model=model,
            output=output,
            year_field=year_field,
            stable_id=stable_id,
            outside=outside,
        )
    return base.select(*TeamSeason.model_fields).sort("season", "team_id")


@dataset(
    id="cfbd.team_seasons",
    revision=6,
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
) -> RecipeRef[Table]:
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


def _attach_season_source(
    base: Table,
    source: Table | None,
    *,
    context: Table,
    model: type[BaseModel],
    output: str,
    year_field: str,
    stable_id: bool = False,
    outside: Literal["ignore", "reject"],
    required: bool = False,
) -> Table:
    """Apply explicit season identity/context policy through shared joins."""
    keys = ("season", "team_id") if stable_id else ("season", "__team_key")
    if source is not None:
        source = source.with_columns(nw.col(year_field).alias("season")).normalize_text(
            "team", into="__team_key"
        )
        source_context = context.select(
            *keys,
            nw.col("conference").alias("__expected_conference"),
            nw.col("__team_key").alias("__expected_name"),
        ).with_columns(nw.lit(True).alias("__base_match"))
        source = source.join(source_context, on=keys, cardinality="many_to_one")
        predicate = nw.col("__team_key") == nw.col("__expected_name")
        if "conference" in model.model_fields:
            predicate = predicate & (
                nw.col("conference").is_null()
                | (nw.col("conference") == nw.col("__expected_conference"))
            )
        source = source.require(
            (nw.col("__base_match").fill_null(False) == nw.lit(False)) | predicate,
            message=f"{output} conflicts with records identity",
        )
    result = base.enrich(
        source,
        on=keys,
        output=output,
        coverage=f"{output}_coverage",
        fields={name: name for name in model.model_fields},
        outside=outside,
        completeness="required" if required else "if_nonempty",
        message=f"Requested {output} is duplicated, outside the records universe, or incomplete",
    )
    return result


__all__ = [
    "TeamSeason",
    "TeamSeasonCoverage",
    "TeamSeasonStatistic",
    "team_seasons",
]
