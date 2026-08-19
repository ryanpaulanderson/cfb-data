"""Provide the independently authored team-seasons dataset recipe.

``team_seasons`` uses ``/records`` as its authoritative row universe. Common
and advanced season statistics are required validated enrichments attached by
season-scoped team identity. Dynamic conventional statistics remain ordered
typed records rather than being implicitly pivoted into a changing schema.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification
from cfb_data.games.models.pydantic.responses import TeamRecord, TeamRecords
from cfb_data.games.sources import team_records
from cfb_data.stats.models.pydantic.responses import AdvancedSeasonStat, TeamStat
from cfb_data.stats.sources import advanced_season_stats, team_season_stats
from pydantic import BaseModel, ConfigDict, Field


class TeamSeasonStatistic(BaseModel):
    """Preserve one dynamic conventional statistic in source order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(json_schema_extra={"semantic_type": "dimension"})
    value: str | int | float = Field(json_schema_extra={"semantic_type": "measure"})
    source_conference: str = Field(json_schema_extra={"semantic_type": "dimension"})
    source_ordinal: int = Field(ge=0)


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


@step(
    id="cfbd.team_seasons.compose",
    revision=1,
    output=TeamSeason,
    deterministic=True,
)
def compose_team_seasons(
    records: list[TeamRecords],
    statistics: list[TeamStat],
    advanced: list[AdvancedSeasonStat],
) -> list[TeamSeason]:
    """Attach required season statistics to the records-defined universe.

    :param records: Validated authoritative team-season rows.
    :param statistics: Validated dynamic conventional statistics.
    :param advanced: Validated nested advanced season metrics.
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
            )
        )
    return sorted(rows, key=lambda row: (row.season, row.team_id))


@dataset(
    id="cfbd.team_seasons",
    revision=1,
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
) -> RecipeRef[list[TeamSeason]]:
    """Build complete team-season records and core statistics.

    :param season: Required season year.
    :param team: Optional team selector.
    :param conference: Optional records and conventional-stat selector.
    :param classification: Optional statistics classification selector.
    :param start_week: Optional inclusive statistics starting week.
    :param end_week: Optional inclusive statistics ending week.
    :param exclude_garbage_time: Optional advanced-statistics source policy.
    :return: A reference to the validated team-seasons dataset.
    """
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
    )


def _identity_text(value: str) -> str:
    return " ".join(value.split()).casefold()


__all__ = ["TeamSeason", "TeamSeasonStatistic", "team_seasons"]
