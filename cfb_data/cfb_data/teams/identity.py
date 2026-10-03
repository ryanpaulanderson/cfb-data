"""Resolve temporal team names against validated Teams domain evidence."""

from __future__ import annotations

from enum import StrEnum

import narwhals.stable.v2 as nw
from pydantic import BaseModel, ConfigDict, Field

from cfb_data.analytics.tables import Table, concat_tables
from cfb_data.teams.models.pydantic.responses import Team


class TeamIdentityStatus(StrEnum):
    """Classify season-scoped team identity evidence."""

    resolved = "resolved"
    unresolved = "unresolved"
    ambiguous = "ambiguous"


class TeamIdentityEvidence(BaseModel):
    """Describe the deterministic outcome of one temporal name lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: TeamIdentityStatus
    team_id: int | None = Field(default=None, gt=0)
    candidate_ids: tuple[int, ...]


class TeamIdentityIndex:
    """Own an immutable normalized index of validated team names and aliases."""

    __slots__ = ("_candidates",)

    def __init__(self, teams: list[Team]) -> None:
        """Index stable IDs under normalized school and alias values.

        :param teams: Validated temporal team rows.
        """
        mutable: dict[str, set[int]] = {}
        for team in teams:
            names = [team.school, *(team.alternate_names or [])]
            for name in names:
                normalized = normalize_team_identity_text(name)
                if normalized:
                    mutable.setdefault(normalized, set()).add(team.id)
        self._candidates = {name: tuple(sorted(ids)) for name, ids in mutable.items()}

    def resolve(self, source_name: str) -> TeamIdentityEvidence:
        """Return all season-scoped candidates for one source team name.

        :param source_name: Source-provided school or alias text.
        :return: Explicit resolved, ambiguous, or unresolved evidence.
        """
        candidates = self._candidates.get(normalize_team_identity_text(source_name), ())
        if len(candidates) == 1:
            return TeamIdentityEvidence(
                status=TeamIdentityStatus.resolved,
                team_id=candidates[0],
                candidate_ids=candidates,
            )
        return TeamIdentityEvidence(
            status=(
                TeamIdentityStatus.ambiguous
                if candidates
                else TeamIdentityStatus.unresolved
            ),
            candidate_ids=candidates,
        )


def normalize_team_identity_text(value: str) -> str:
    """Return the stable whitespace- and case-normalized identity key.

    :param value: Source team name or alias.
    :return: Deterministic lookup text.
    """
    return " ".join(value.split()).casefold()


def resolve_team_identity_table(
    rows: Table, teams: Table, *, source_name: str
) -> Table:
    """Attach temporal identity evidence through native joins and grouping.

    :param rows: Native base table retaining the source-provided team name.
    :param teams: Validated season-specific team identity evidence.
    :param source_name: Base text column to resolve without fuzzy matching.
    :return: Base universe with resolved, unresolved, or ambiguous evidence.
    """
    schools = teams.select(
        nw.col("id").alias("__candidate_id"), nw.col("school").alias("__alias")
    )
    aliases = teams.explode_values(
        "alternate_names", into="__alias", ordinal="__alias_position"
    ).select(nw.col("id").alias("__candidate_id"), "__alias")
    names = (
        concat_tables((schools, aliases))
        .normalize_text("__alias", into="__identity_key")
        .filter(nw.col("__identity_key") != "")
        .distinct("__identity_key", "__candidate_id")
    )
    candidates = names.ordered_values(
        keys=("__identity_key",),
        column="__candidate_id",
        into="team_identity_candidate_ids",
    )
    counts = names.aggregate(
        keys=("__identity_key",),
        expressions=(
            nw.len().alias("__candidate_count"),
            nw.col("__candidate_id").min().alias("__single_id"),
        ),
    )
    evidence = candidates.join(counts, on=("__identity_key",), cardinality="one_to_one")
    joined = (
        rows.normalize_text(source_name, into="__identity_key")
        .join(evidence, on=("__identity_key",), cardinality="many_to_one")
        .fill_empty_lists("team_identity_candidate_ids")
    )
    return joined.with_columns(
        nw.when(nw.col("__candidate_count").fill_null(0) == 1)
        .then(nw.col("__single_id"))
        .otherwise(nw.lit(None))
        .alias("team_id"),
        nw.when(nw.col("__candidate_count").fill_null(0) == 0)
        .then(nw.lit("unresolved"))
        .when(nw.col("__candidate_count") == 1)
        .then(nw.lit("resolved"))
        .otherwise(nw.lit("ambiguous"))
        .alias("team_identity_status"),
    )


__all__ = [
    "TeamIdentityEvidence",
    "TeamIdentityIndex",
    "TeamIdentityStatus",
    "normalize_team_identity_text",
    "resolve_team_identity_table",
]
