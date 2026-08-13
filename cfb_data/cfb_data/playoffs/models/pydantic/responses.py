"""Validate responses from implemented CFBD Playoffs endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data.enums import PlayoffCompetition, PlayoffRound


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Playoffs responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def require_utc_datetimes(cls, value: object) -> object:
        """Require aware response timestamps and normalize them to UTC."""
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Response timestamps must be timezone-aware")
        return value.astimezone(UTC)


class PlayoffStatus(StrEnum):
    """Identify the lifecycle state of one playoff bracket."""

    scheduled = "scheduled"
    selected = "selected"
    in_progress = "in_progress"
    completed = "completed"


class PlayoffBidType(StrEnum):
    """Identify how a team qualified for the playoff."""

    automatic = "automatic"
    at_large = "at_large"


class PlayoffOutcome(StrEnum):
    """Identify a participant's current or final playoff outcome."""

    active = "active"
    eliminated = "eliminated"
    champion = "champion"


class PlayoffSlotOutcome(StrEnum):
    """Identify the prior-matchup result that feeds a bracket slot."""

    winner = "winner"


class PlayoffTeam(_ResponseModel):
    """Represent one team referenced within a playoff bracket."""

    id: int = Field(gt=0)
    school: str
    conference: str | None


class PlayoffParticipant(_ResponseModel):
    """Represent one team selected for a College Football Playoff."""

    team: PlayoffTeam
    committee_rank: int | None = Field(alias="committeeRank", gt=0)
    seed: int = Field(gt=0)
    bid_type: PlayoffBidType = Field(alias="bidType")
    qualification_reason: str | None = Field(alias="qualificationReason")
    conference_champion: bool = Field(alias="conferenceChampion")
    qualifying_conference: str | None = Field(alias="qualifyingConference")
    first_round_bye: bool = Field(alias="firstRoundBye")
    outcome: PlayoffOutcome
    eliminated_round: PlayoffRound | None = Field(alias="eliminatedRound")


class PlayoffMatchupSlotSource(_ResponseModel):
    """Represent the prior matchup feeding one bracket slot."""

    matchup_id: int = Field(alias="matchupId", gt=0)
    bracket_slot: str = Field(alias="bracketSlot")
    outcome: PlayoffSlotOutcome


class PlayoffMatchupSlot(_ResponseModel):
    """Represent one team position within a playoff matchup."""

    position: int = Field(gt=0)
    seed: int | None = Field(gt=0)
    participant: PlayoffTeam | None
    source: PlayoffMatchupSlotSource | None


class PlayoffLinkedGame(_ResponseModel):
    """Represent the played or scheduled game linked to a matchup."""

    id: int = Field(gt=0)
    start_date: datetime = Field(alias="startDate")
    completed: bool
    home_team: PlayoffTeam = Field(alias="homeTeam")
    home_points: int | None = Field(alias="homePoints", ge=0)
    away_team: PlayoffTeam = Field(alias="awayTeam")
    away_points: int | None = Field(alias="awayPoints", ge=0)
    venue_id: int | None = Field(alias="venueId", gt=0)
    venue: str | None


class PlayoffAdvancement(_ResponseModel):
    """Represent the next bracket position awarded to a matchup winner."""

    matchup_id: int = Field(alias="matchupId", gt=0)
    bracket_slot: str = Field(alias="bracketSlot")
    position: int = Field(gt=0)


class PlayoffMatchup(_ResponseModel):
    """Represent one scheduled or completed playoff matchup."""

    id: int = Field(gt=0)
    bracket_slot: str = Field(alias="bracketSlot")
    round: PlayoffRound
    round_name: str = Field(alias="roundName")
    round_order: int = Field(alias="roundOrder", gt=0)
    matchup_order: int = Field(alias="matchupOrder", gt=0)
    start_date: datetime | None = Field(alias="startDate")
    bowl_name: str | None = Field(alias="bowlName")
    slots: list[PlayoffMatchupSlot]
    game: PlayoffLinkedGame | None
    advances_to: PlayoffAdvancement | None = Field(alias="advancesTo")


class PlayoffRoundRecord(_ResponseModel):
    """Represent one ordered round in the playoff bracket."""

    code: PlayoffRound
    name: str
    order: int = Field(gt=0)
    matchups: list[PlayoffMatchup]


class CfpPlayoff(_ResponseModel):
    """Represent one complete College Football Playoff bracket."""

    season: int = Field(ge=2014)
    competition: PlayoffCompetition
    format: str
    team_count: int = Field(alias="teamCount", gt=0)
    status: PlayoffStatus
    participants: list[PlayoffParticipant]
    rounds: list[PlayoffRoundRecord]
    champion: PlayoffTeam | None


__all__ = [
    "CfpPlayoff",
    "PlayoffAdvancement",
    "PlayoffBidType",
    "PlayoffLinkedGame",
    "PlayoffMatchup",
    "PlayoffMatchupSlot",
    "PlayoffMatchupSlotSource",
    "PlayoffOutcome",
    "PlayoffParticipant",
    "PlayoffRoundRecord",
    "PlayoffSlotOutcome",
    "PlayoffStatus",
    "PlayoffTeam",
]
