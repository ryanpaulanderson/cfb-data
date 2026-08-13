"""Validate responses from implemented CFBD Recruiting endpoints."""

from pydantic import BaseModel, ConfigDict, Field

from cfb_data.enums import RecruitClassification


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Recruiting responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class RecruitHometown(_ResponseModel):
    """Represent normalized geographic details for a recruit's hometown."""

    latitude: float | None
    longitude: float | None
    fips_code: str | None = Field(alias="fipsCode")


class Recruit(_ResponseModel):
    """Represent one ranked recruiting prospect."""

    id: str
    athlete_id: str | None = Field(alias="athleteId")
    recruit_type: RecruitClassification = Field(alias="recruitType")
    year: int = Field(ge=1869)
    ranking: int | None = Field(ge=1)
    name: str
    school: str | None
    committed_to: str | None = Field(alias="committedTo")
    position: str | None
    height: float | None = Field(ge=0)
    weight: int | None = Field(ge=0)
    stars: int | None = Field(ge=0, le=5)
    rating: float | None = Field(ge=0)
    city: str | None
    state_province: str | None = Field(alias="stateProvince")
    country: str | None
    hometown_info: RecruitHometown = Field(alias="hometownInfo")


class TeamRecruitingRanking(_ResponseModel):
    """Represent one team's recruiting class ranking."""

    year: int = Field(ge=1869)
    rank: int = Field(ge=1)
    team: str
    points: float


class AggregatedTeamRecruiting(_ResponseModel):
    """Represent recruiting quality aggregated by team and position group."""

    team: str
    conference: str
    position_group: str | None = Field(alias="positionGroup")
    average_rating: float = Field(alias="averageRating")
    total_rating: float = Field(alias="totalRating")
    commits: int = Field(ge=0)
    average_stars: float = Field(alias="averageStars", ge=0, le=5)


__all__ = [
    "AggregatedTeamRecruiting",
    "Recruit",
    "RecruitHometown",
    "TeamRecruitingRanking",
]
