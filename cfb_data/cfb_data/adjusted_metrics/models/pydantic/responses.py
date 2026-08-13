"""Validate responses from implemented CFBD Adjusted Metrics endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to adjusted metric responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AdjustedTeamMetricsEPA(_ResponseModel):
    """Represent opponent-adjusted EPA by play type."""

    total: float
    passing: float
    rushing: float


class AdjustedTeamMetricsSuccessRate(_ResponseModel):
    """Represent opponent-adjusted success rate by down context."""

    total: float = Field(ge=0, le=1)
    standard_downs: float = Field(alias="standardDowns", ge=0, le=1)
    passing_downs: float = Field(alias="passingDowns", ge=0, le=1)


class AdjustedTeamMetricsRushing(_ResponseModel):
    """Represent opponent-adjusted rushing yard components."""

    line_yards: float = Field(alias="lineYards")
    second_level_yards: float = Field(alias="secondLevelYards")
    open_field_yards: float = Field(alias="openFieldYards")
    highlight_yards: float = Field(alias="highlightYards")


class AdjustedTeamMetrics(_ResponseModel):
    """Represent opponent-adjusted team metrics for one season."""

    year: int = Field(ge=1869)
    team_id: int = Field(alias="teamId", gt=0)
    team: str
    conference: str
    epa: AdjustedTeamMetricsEPA
    epa_allowed: AdjustedTeamMetricsEPA = Field(alias="epaAllowed")
    success_rate: AdjustedTeamMetricsSuccessRate = Field(alias="successRate")
    success_rate_allowed: AdjustedTeamMetricsSuccessRate = Field(
        alias="successRateAllowed"
    )
    rushing: AdjustedTeamMetricsRushing
    rushing_allowed: AdjustedTeamMetricsRushing = Field(alias="rushingAllowed")
    explosiveness: float
    explosiveness_allowed: float = Field(alias="explosivenessAllowed")


class PlayerWeightedEPA(_ResponseModel):
    """Represent opponent-adjusted player EPA for one season."""

    year: int = Field(ge=1869)
    athlete_id: str = Field(alias="athleteId", min_length=1)
    athlete_name: str = Field(alias="athleteName")
    position: str
    team: str
    conference: str
    wepa: float
    plays: int = Field(ge=0)


class KickerPAAR(_ResponseModel):
    """Represent a kicker's Points Added Above Replacement rating."""

    year: int = Field(ge=1869)
    athlete_id: str = Field(alias="athleteId", min_length=1)
    athlete_name: str = Field(alias="athleteName")
    team: str
    conference: str
    paar: float
    attempts: int = Field(ge=0)


__all__ = [
    "AdjustedTeamMetrics",
    "AdjustedTeamMetricsEPA",
    "AdjustedTeamMetricsRushing",
    "AdjustedTeamMetricsSuccessRate",
    "KickerPAAR",
    "PlayerWeightedEPA",
]
