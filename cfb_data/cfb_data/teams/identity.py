"""Resolve temporal team names against validated Teams domain evidence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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


__all__ = [
    "TeamIdentityEvidence",
    "TeamIdentityIndex",
    "TeamIdentityStatus",
    "normalize_team_identity_text",
]
