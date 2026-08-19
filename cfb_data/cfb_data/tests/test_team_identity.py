"""Validate reusable temporal team identity resolution."""

from __future__ import annotations

from cfb_data.teams.identity import TeamIdentityIndex, TeamIdentityStatus
from cfb_data.teams.models.pydantic.responses import Team


def _team(team_id: int, school: str, aliases: list[str] | None) -> Team:
    return Team(
        id=team_id,
        school=school,
        mascot=None,
        abbreviation=None,
        alternate_names=aliases,
        conference=None,
        division=None,
        classification=None,
        color=None,
        alternate_color=None,
        logos=None,
        twitter=None,
        location=None,
    )


def test_identity_index_retains_all_deterministic_candidates() -> None:
    """Resolve normalized names without choosing an ambiguous alias."""
    index = TeamIdentityIndex(
        [
            _team(213, "Penn State", ["PSU", "State"]),
            _team(999, "Example State", ["State"]),
        ]
    )

    resolved = index.resolve("  pSu ")
    ambiguous = index.resolve("STATE")
    unresolved = index.resolve("Unknown College")

    assert resolved.status is TeamIdentityStatus.resolved
    assert resolved.team_id == 213
    assert resolved.candidate_ids == (213,)
    assert ambiguous.status is TeamIdentityStatus.ambiguous
    assert ambiguous.team_id is None
    assert ambiguous.candidate_ids == (213, 999)
    assert unresolved.status is TeamIdentityStatus.unresolved
    assert unresolved.candidate_ids == ()
