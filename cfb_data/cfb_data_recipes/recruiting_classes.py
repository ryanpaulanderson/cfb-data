"""Provide the independently authored recruiting-classes dataset recipe.

``recruiting_classes`` unions validated team rankings with individual recruit
commitments. Ranked teams with no returned commitments and commitment-only
teams both survive. Recruits without a commitment are retained in one explicit
uncommitted class bucket rather than dropped or assigned to a team.
"""

from __future__ import annotations

from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import RecruitClassification
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)
from cfb_data.recruiting.sources import recruiting_players, recruiting_teams
from pydantic import BaseModel, ConfigDict, Field


class RecruitingClassStatus(StrEnum):
    """Classify how a recruiting-class row entered the union."""

    ranked = "ranked"
    commitments_only = "commitments_only"
    uncommitted = "uncommitted"


class RecruitingClass(BaseModel):
    """Represent one team class or explicit uncommitted bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    class_year: int = Field(
        ge=1869,
        json_schema_extra={"semantic_type": "dimension"},
    )
    class_key: str = Field(
        description="Stable normalized team or uncommitted identity within a year.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    class_ordinal: int = Field(
        ge=0,
        description="Deterministic rank-aware class order within the year.",
    )
    source_team: str | None = Field(
        default=None,
        description="Source team name; null only for the uncommitted bucket.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    status: RecruitingClassStatus
    rank: int | None = Field(
        default=None,
        ge=1,
        json_schema_extra={"semantic_type": "measure"},
    )
    points: float | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    recruits: list[Recruit] = Field(
        description="Validated recruits preserved in source order."
    )
    recruit_count: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "recruits"},
    )


@step(
    id="cfbd.recruiting_classes.compose",
    revision=1,
    output=RecruitingClass,
    deterministic=True,
)
def compose_recruiting_classes(
    rankings: list[TeamRecruitingRanking],
    recruits: list[Recruit],
) -> list[RecruitingClass]:
    """Union ranked teams, commitments, and explicit uncommitted recruits.

    :param rankings: Validated team class rankings.
    :param recruits: Validated individual recruits.
    :return: Complete recruiting-class rows in deterministic year/rank order.
    :raises ValueError: If a source candidate key is duplicated.
    """
    ranking_by_key: dict[tuple[int, str], TeamRecruitingRanking] = {}
    source_team_by_key: dict[tuple[int, str], str | None] = {}
    for source_ranking in rankings:
        key = (source_ranking.year, _team_key(source_ranking.team))
        if key in ranking_by_key:
            raise ValueError("Recruiting rankings contain duplicate team classes")
        ranking_by_key[key] = source_ranking
        source_team_by_key[key] = source_ranking.team

    recruits_by_key: dict[tuple[int, str], list[Recruit]] = {}
    recruit_ids: set[str] = set()
    for recruit in recruits:
        if recruit.id in recruit_ids:
            raise ValueError("Recruiting players contain duplicate recruit IDs")
        recruit_ids.add(recruit.id)
        normalized_team = (
            _team_key(recruit.committed_to)
            if recruit.committed_to is not None
            else "uncommitted"
        )
        key = (recruit.year, normalized_team)
        recruits_by_key.setdefault(key, []).append(recruit)
        source_team_by_key.setdefault(key, recruit.committed_to)

    rows: list[RecruitingClass] = []
    for key in set(ranking_by_key) | set(recruits_by_key):
        selected_ranking = ranking_by_key.get(key)
        source_team = source_team_by_key[key]
        if key[1] == "uncommitted":
            status = RecruitingClassStatus.uncommitted
        elif selected_ranking is None:
            status = RecruitingClassStatus.commitments_only
        else:
            status = RecruitingClassStatus.ranked
        selected_recruits = recruits_by_key.get(key, [])
        rows.append(
            RecruitingClass(
                class_year=key[0],
                class_key=key[1],
                class_ordinal=0,
                source_team=source_team,
                status=status,
                rank=(selected_ranking.rank if selected_ranking is not None else None),
                points=(
                    selected_ranking.points if selected_ranking is not None else None
                ),
                recruits=selected_recruits,
                recruit_count=len(selected_recruits),
            )
        )
    ordered = sorted(
        rows,
        key=lambda row: (
            row.class_year,
            row.status is RecruitingClassStatus.uncommitted,
            row.rank is None,
            row.rank if row.rank is not None else 0,
            row.class_key,
        ),
    )
    return [
        row.model_copy(update={"class_ordinal": ordinal})
        for ordinal, row in enumerate(ordered)
    ]


@dataset(
    id="cfbd.recruiting_classes",
    revision=1,
    row=RecruitingClass,
    grain="one team recruiting class or uncommitted year bucket",
    keys=("class_year", "class_key"),
    order_by=("class_year", "class_ordinal"),
    partition_by=("class_year",),
)
def recruiting_classes(
    *,
    class_year: int,
    team: str | None = None,
    position: str | None = None,
    state: str | None = None,
    classification: RecruitClassification | None = None,
) -> RecipeRef[list[RecruitingClass]]:
    """Build recruiting classes from rankings and individual recruits.

    :param class_year: Required recruiting class year.
    :param team: Optional ranked and committed-team selector.
    :param position: Optional recruit position selector.
    :param state: Optional recruit home-state selector.
    :param classification: Optional recruit-type selector.
    :return: A reference to the validated recruiting-classes dataset.
    """
    return compose_recruiting_classes(
        recruiting_teams(year=class_year, team=team),
        recruiting_players(
            year=class_year,
            team=team,
            position=position,
            state=state,
            classification=classification,
        ),
    )


def _team_key(value: str) -> str:
    return f"team:{' '.join(value.split()).casefold()}"


__all__ = ["RecruitingClass", "RecruitingClassStatus", "recruiting_classes"]
