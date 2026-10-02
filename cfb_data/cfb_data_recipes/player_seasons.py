"""Provide the independently authored player-seasons dataset recipe.

``player_seasons`` composes the public ``rosters`` dataset with the public
long-form player-season statistics and temporal Teams source. It unions their
athlete memberships so roster-only and stats-only athletes survive, while
display statistics remain ordered strings rather than inferred numbers.
"""

from __future__ import annotations

from enum import StrEnum

import narwhals.stable.v2 as nw
from cfb_data.adjusted_metrics.models.pydantic.responses import (
    KickerPAAR,
    PlayerWeightedEPA,
)
from cfb_data.adjusted_metrics.sources import (
    adjusted_player_passing,
    adjusted_player_rushing,
    kicker_paar_metrics,
)
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.analytics.tables import SOURCE_ORDINAL
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics.models.pydantic.responses import PlayerSeasonPredictedPointsAdded
from cfb_data.metrics.sources import player_season_ppa
from cfb_data.players.models.pydantic.responses import PlayerUsage
from cfb_data.players.sources import player_usage
from cfb_data.stats.models.pydantic.responses import (
    PlayerSeasonSuccessRate,
)
from cfb_data.stats.sources import (
    player_season_stats,
    player_season_success,
)
from cfb_data.teams.identity import TeamIdentityStatus, resolve_team_identity_table
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
    revision=3,
    output=PlayerSeason,
    deterministic=True,
)
def compose_player_seasons(
    season: int,
    memberships: Table,
    statistics: Table,
    teams: Table,
    *,
    usage: Table | None,
    ppa: Table | None,
    success: Table | None,
    passing_wepa: Table | None,
    rushing_wepa: Table | None,
    kicker_paar: Table | None,
) -> Table:
    """Union native roster and statistic memberships with explicit evidence.

    :param season: Requested player season.
    :param memberships: Validated public roster table.
    :param statistics: Validated long-form statistic table.
    :param teams: Temporal team identity evidence.
    :param usage: Requested usage evidence or omitted source.
    :param ppa: Requested PPA evidence or omitted source.
    :param success: Requested success evidence or omitted source.
    :param passing_wepa: Requested passing evidence or omitted source.
    :param rushing_wepa: Requested rushing evidence or omitted source.
    :param kicker_paar: Requested kicking evidence or omitted source.
    :return: Native union retaining roster-only and statistics-only athletes.
    """
    keys = ("season", "__team_key", "athlete_id")
    roster = (
        memberships.normalize_text("source_team", into="__team_key")
        .require(
            nw.col("season") == season,
            message="Roster memberships contain a different season",
        )
        .require_unique(
            keys, message="Roster memberships contain duplicate athlete keys"
        )
    )
    roster = roster.pack(
        columns={name: name for name in RosterMembership.model_fields}, into="roster"
    ).select(
        *keys,
        "roster",
        nw.col("source_team").alias("__roster_team"),
        nw.when(
            (~nw.col("first_name").is_null())
            & (nw.col("first_name") != "")
            & (~nw.col("last_name").is_null())
            & (nw.col("last_name") != "")
        )
        .then(nw.concat_str(nw.col("first_name"), nw.col("last_name"), separator=" "))
        .when((~nw.col("first_name").is_null()) & (nw.col("first_name") != ""))
        .then(nw.col("first_name"))
        .when((~nw.col("last_name").is_null()) & (nw.col("last_name") != ""))
        .then(nw.col("last_name"))
        .otherwise(nw.lit(""))
        .alias("__roster_name"),
        nw.col("position").alias("__roster_position"),
        nw.lit(True).alias("roster_present"),
    )
    stats = (
        statistics.rename({"player_id": "athlete_id"})
        .normalize_text("team", into="__team_key")
        .require(
            nw.col("season") == season,
            message="Player statistics contain a different season",
        )
        .require_unique(
            (*keys, "category", "stat_type"),
            message="Player statistics contain duplicate candidate keys",
        )
    )
    identities = (
        stats.distinct(*keys, "player", "position")
        .aggregate(
            keys=keys,
            expressions=(
                nw.len().alias("__identity_count"),
                nw.col("player").min().alias("__stat_name"),
                nw.col("position").min().alias("__stat_position"),
            ),
        )
        .require(
            nw.col("__identity_count") == 1,
            message="Player statistics disagree on athlete identity",
        )
    )
    first = (
        stats.aggregate(
            keys=keys, expressions=(nw.col(SOURCE_ORDINAL).min().alias(SOURCE_ORDINAL),)
        )
        .join(
            stats.select(*keys, SOURCE_ORDINAL, nw.col("team").alias("__stat_team")),
            on=(*keys, SOURCE_ORDINAL),
            cardinality="one_to_one",
        )
        .select(*keys, "__stat_team")
    )
    packed = stats.pack(
        columns={
            "category": "category",
            "stat_type": "stat_type",
            "stat": "stat",
            "conference": "source_conference",
            SOURCE_ORDINAL: "source_ordinal",
        },
        into="__statistic",
    )
    grouped = (
        packed.ordered_records(
            keys=keys,
            column="__statistic",
            into="statistics",
            ordinal_field="source_ordinal",
            keep_ordinal=True,
        )
        .join(identities, on=keys, cardinality="one_to_one")
        .join(first, on=keys, cardinality="one_to_one")
        .with_columns(nw.lit(True).alias("statistics_present"))
    )
    base = (
        roster.join(grouped, on=keys, how="full", cardinality="one_to_one")
        .with_columns(
            nw.coalesce(nw.col("__roster_team"), nw.col("__stat_team")).alias(
                "source_team"
            ),
            nw.coalesce(nw.col("__roster_name"), nw.col("__stat_name")).alias(
                "athlete_name"
            ),
            nw.when(nw.col("roster_present").fill_null(False))
            .then(nw.col("__roster_position"))
            .otherwise(nw.col("__stat_position"))
            .alias("position"),
            nw.col("roster_present").fill_null(False),
            nw.col("statistics_present").fill_null(False),
        )
        .with_columns(nw.col("season").cast(nw.Int64))
        .fill_empty_lists("statistics")
    )
    base = resolve_team_identity_table(base, teams, source_name="source_team")
    specs: tuple[tuple[str, Table | None, type[BaseModel], str, str], ...] = (
        ("usage", usage, PlayerUsage, "season", "id"),
        ("ppa", ppa, PlayerSeasonPredictedPointsAdded, "season", "id"),
        ("success", success, PlayerSeasonSuccessRate, "season", "id"),
        ("passing_wepa", passing_wepa, PlayerWeightedEPA, "year", "athlete_id"),
        ("rushing_wepa", rushing_wepa, PlayerWeightedEPA, "year", "athlete_id"),
        ("kicker_paar", kicker_paar, KickerPAAR, "year", "athlete_id"),
    )
    for output, source, model, year_field, id_field in specs:
        if source is not None:
            source = (
                source.with_columns(
                    nw.col(year_field).alias("season"),
                    nw.col(id_field).alias("athlete_id"),
                )
                .normalize_text("team", into="__team_key")
                .require(
                    nw.col("season") == season,
                    message=f"{output} contains a different season",
                )
            )
        base = base.enrich(
            source,
            on=keys,
            output=output,
            coverage=f"{output}_coverage",
            fields={name: name for name in model.model_fields},
            message=f"{output} contains duplicate or outside athlete keys",
        )
    return base.select(*PlayerSeason.model_fields).sort(
        "season", "source_team", "athlete_id"
    )


@dataset(
    id="cfbd.player_seasons",
    revision=3,
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
) -> RecipeRef[Table]:
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


__all__ = [
    "PlayerSeason",
    "PlayerSeasonCoverage",
    "PlayerSeasonStatistic",
    "player_seasons",
]
