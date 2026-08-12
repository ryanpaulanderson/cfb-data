"""Validate responses from implemented CFBD Ratings endpoints."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import Classification


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Ratings responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CoreRatingSeasonType(StrEnum):
    """Identify the season phase through which CORE was calculated."""

    regular = "regular"
    postseason = "postseason"


class TeamCoreRating(_ResponseModel):
    """Represent one team's Context and Opponent-Relative Efficiency rating."""

    year: int = Field(ge=1869)
    through_season_type: CoreRatingSeasonType = Field(alias="throughSeasonType")
    through_week: int = Field(alias="throughWeek", ge=0)
    team: str
    conference: str | None
    overall: float
    offense: float
    defense: float
    offense_plays: int = Field(alias="offensePlays", ge=0)
    defense_plays: int = Field(alias="defensePlays", ge=0)
    model_version: str = Field(alias="modelVersion")


class SPHavoc(_ResponseModel):
    """Represent defensive SP+ havoc components."""

    total: float | None
    front_seven: float | None = Field(alias="frontSeven")
    db: float | None


class SPOffense(_ResponseModel):
    """Represent offensive SP+ components."""

    ranking: int | None = Field(ge=1)
    rating: float
    success: float | None
    explosiveness: float | None
    rushing: float | None
    passing: float | None
    standard_downs: float | None = Field(alias="standardDowns")
    passing_downs: float | None = Field(alias="passingDowns")
    run_rate: float | None = Field(alias="runRate")
    pace: float | None


class SPDefense(_ResponseModel):
    """Represent defensive SP+ components."""

    ranking: int | None = Field(ge=1)
    rating: float
    success: float | None
    explosiveness: float | None
    rushing: float | None
    passing: float | None
    standard_downs: float | None = Field(alias="standardDowns")
    passing_downs: float | None = Field(alias="passingDowns")
    havoc: SPHavoc


class SPSpecialTeams(_ResponseModel):
    """Represent special-teams SP+ components."""

    rating: float | None


class TeamSP(_ResponseModel):
    """Represent one team's SP+ rating for a season."""

    year: int = Field(ge=1869)
    team: str
    conference: str | None = None
    rating: float
    ranking: int | None = Field(ge=1)
    second_order_wins: float | None = Field(alias="secondOrderWins")
    sos: float | None
    offense: SPOffense
    defense: SPDefense
    special_teams: SPSpecialTeams = Field(alias="specialTeams")


class ConferenceSPOffense(_ResponseModel):
    """Represent conference-level offensive SP+ components."""

    rating: float
    success: float | None
    explosiveness: float | None
    rushing: float | None
    passing: float | None
    standard_downs: float | None = Field(alias="standardDowns")
    passing_downs: float | None = Field(alias="passingDowns")
    run_rate: float | None = Field(alias="runRate")
    pace: float | None


class ConferenceSPDefense(_ResponseModel):
    """Represent conference-level defensive SP+ components."""

    rating: float
    success: float | None
    explosiveness: float | None
    rushing: float | None
    passing: float | None
    standard_downs: float | None = Field(alias="standardDowns")
    passing_downs: float | None = Field(alias="passingDowns")
    havoc: SPHavoc


class ConferenceSP(_ResponseModel):
    """Represent aggregate SP+ ratings for one conference season."""

    year: int = Field(ge=1869)
    conference: str
    rating: float
    second_order_wins: float | None = Field(alias="secondOrderWins")
    sos: float | None
    offense: ConferenceSPOffense
    defense: ConferenceSPDefense
    special_teams: SPSpecialTeams = Field(alias="specialTeams")


class TeamSRS(_ResponseModel):
    """Represent one team's Simple Rating System result."""

    year: int = Field(ge=1869)
    team: str
    conference: str | None
    division: str | None
    rating: float
    ranking: int | None = Field(ge=1)


class ExpandedTeamSRS(TeamSRS):
    """Represent SRS with the team's division classification."""

    classification: Classification


class TeamElo(_ResponseModel):
    """Represent a team's latest Elo rating for the selected period."""

    year: int = Field(ge=1869)
    team: str
    conference: str
    elo: int | None


class FPIResumeRanks(_ResponseModel):
    """Represent résumé rank components associated with FPI."""

    strength_of_record: int | None = Field(alias="strengthOfRecord", ge=1)
    fpi: int | None = Field(ge=1)
    average_win_probability: int | None = Field(alias="averageWinProbability", ge=1)
    strength_of_schedule: int | None = Field(alias="strengthOfSchedule", ge=1)
    remaining_strength_of_schedule: int | None = Field(
        alias="remainingStrengthOfSchedule", ge=1
    )
    game_control: int | None = Field(alias="gameControl", ge=1)


class FPIEfficiencies(_ResponseModel):
    """Represent FPI efficiency components."""

    overall: float | None
    offense: float | None
    defense: float | None
    special_teams: float | None = Field(alias="specialTeams")


class TeamFPI(_ResponseModel):
    """Represent one team's Football Power Index result."""

    year: int = Field(ge=1869)
    team: str
    conference: str | None
    fpi: float | None
    resume_ranks: FPIResumeRanks = Field(alias="resumeRanks")
    efficiencies: FPIEfficiencies


__all__ = [
    "ConferenceSP",
    "ConferenceSPDefense",
    "ConferenceSPOffense",
    "CoreRatingSeasonType",
    "ExpandedTeamSRS",
    "FPIEfficiencies",
    "FPIResumeRanks",
    "SPDefense",
    "SPHavoc",
    "SPOffense",
    "SPSpecialTeams",
    "TeamCoreRating",
    "TeamElo",
    "TeamFPI",
    "TeamSP",
    "TeamSRS",
]
