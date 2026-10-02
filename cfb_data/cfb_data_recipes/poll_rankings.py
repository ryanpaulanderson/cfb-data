"""Provide the independently authored poll-rankings dataset recipe.

``poll_rankings`` flattens validated poll-week nesting into one team/poll
snapshot row. Source poll order, rank order, nullable rank, final-state
evidence, votes, and points are preserved without inferring a preferred poll.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.enums import RankingPoll, SeasonType
from cfb_data.rankings.sources import rankings as rankings_source
from pydantic import BaseModel, ConfigDict, Field


class PollRanking(BaseModel):
    """Represent one team within one poll snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    season: int = Field(ge=1869, json_schema_extra={"semantic_type": "dimension"})
    season_type: SeasonType = Field(json_schema_extra={"semantic_type": "dimension"})
    week: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    poll: str = Field(json_schema_extra={"semantic_type": "dimension"})
    is_final: bool | None = Field(
        default=None,
        description="Nullable source final-state evidence.",
    )
    team_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    school: str = Field(json_schema_extra={"semantic_type": "dimension"})
    conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    rank: int | None = Field(
        default=None,
        ge=1,
        description="Nullable source rank; source order remains separate.",
        json_schema_extra={"semantic_type": "measure"},
    )
    first_place_votes: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "votes"},
    )
    points: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    poll_ordinal: int = Field(ge=0)
    rank_ordinal: int = Field(ge=0)


@step(
    id="cfbd.poll_rankings.flatten",
    revision=2,
    output=PollRanking,
    deterministic=True,
)
def flatten_poll_rankings(rows: Table) -> Table:
    """Explode native poll tables while retaining original source order.

    :param rows: Validated snapshot table.
    :return: Native rank observations preserving null and empty-list semantics.
    """
    ranks = ("team_id", "school", "conference", "rank", "first_place_votes", "points")
    return (
        rows.explode_records(
            "polls",
            fields={"poll": "poll", "is_final": "is_final", "ranks": "__ranks"},
            ordinal="poll_ordinal",
        )
        .explode_records(
            "__ranks",
            fields={name: name for name in ranks},
            ordinal="rank_ordinal",
        )
        .select(*PollRanking.model_fields)
        .sort(
            "season", "season_type", "week", "poll_ordinal", "rank_ordinal", "team_id"
        )
    )


@dataset(
    id="cfbd.poll_rankings",
    revision=2,
    row=PollRanking,
    grain="one team within one poll snapshot",
    keys=("season", "season_type", "week", "poll", "team_id"),
    order_by=(
        "season",
        "season_type",
        "week",
        "poll_ordinal",
        "rank_ordinal",
        "team_id",
    ),
    partition_by=("season",),
)
def poll_rankings(
    *,
    season: int,
    season_type: SeasonType | None = None,
    week: int | None = None,
    poll: RankingPoll | None = None,
    latest: bool | None = None,
    final: bool | None = None,
) -> RecipeRef[Table]:
    """Build flattened poll ranking snapshots.

    :param season: Required season year.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param poll: Optional upstream poll selector.
    :param latest: Optional latest-CFP selector.
    :param final: Optional final-CFP selector.
    :return: A reference to the validated poll-rankings dataset.
    """
    return flatten_poll_rankings(
        rankings_source(
            year=season,
            season_type=season_type,
            week=week,
            poll=poll,
            latest=latest,
            final=final,
        )
    )


__all__ = ["PollRanking", "poll_rankings"]
