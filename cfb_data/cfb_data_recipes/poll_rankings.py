"""Provide the independently authored poll-rankings dataset recipe.

``poll_rankings`` flattens validated poll-week nesting into one team/poll
snapshot row. Source poll order, rank order, nullable rank, final-state
evidence, votes, and points are preserved without inferring a preferred poll.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import RankingPoll, SeasonType
from cfb_data.rankings.models.pydantic.responses import PollWeek
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
    revision=1,
    output=PollRanking,
    deterministic=True,
)
def flatten_poll_rankings(rows: list[PollWeek]) -> list[PollRanking]:
    """Flatten validated poll nesting while retaining source ordinals.

    :param rows: Validated poll weeks in upstream order.
    :return: Poll ranking rows in deterministic snapshot/source order.
    """
    flattened: list[PollRanking] = []
    for snapshot in rows:
        for poll_ordinal, poll in enumerate(snapshot.polls):
            for rank_ordinal, rank in enumerate(poll.ranks):
                flattened.append(
                    PollRanking(
                        season=snapshot.season,
                        season_type=snapshot.season_type,
                        week=snapshot.week,
                        poll=poll.poll,
                        is_final=poll.is_final,
                        team_id=rank.team_id,
                        school=rank.school,
                        conference=rank.conference,
                        rank=rank.rank,
                        first_place_votes=rank.first_place_votes,
                        points=rank.points,
                        poll_ordinal=poll_ordinal,
                        rank_ordinal=rank_ordinal,
                    )
                )
    return sorted(
        flattened,
        key=lambda row: (
            row.season,
            row.season_type.value,
            row.week,
            row.poll_ordinal,
            row.rank_ordinal,
            row.team_id,
        ),
    )


@dataset(
    id="cfbd.poll_rankings",
    revision=1,
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
) -> RecipeRef[list[PollRanking]]:
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
