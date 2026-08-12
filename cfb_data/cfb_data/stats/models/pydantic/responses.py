"""Validate responses from implemented CFBD Stats endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data.enums import SeasonType


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Stats responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PlayerStat(_ResponseModel):
    """Represent one player statistic aggregated by season."""

    season: int = Field(ge=1869)
    player_id: str = Field(alias="playerId")
    player: str
    position: str
    team: str
    conference: str
    category: str
    stat_type: str = Field(alias="statType")
    stat: str


class PlayerSuccessRateSplit(_ResponseModel):
    """Represent passing or rushing success-rate totals."""

    plays: int = Field(ge=0)
    successes: int = Field(ge=0)
    success_rate: float | None = Field(alias="successRate")


class PlayerSeasonSuccessRate(_ResponseModel):
    """Represent one player's passing and rushing season success rates."""

    season: int = Field(ge=1869)
    id: str
    name: str
    position: str
    team: str
    conference: str
    passing: PlayerSuccessRateSplit
    rushing: PlayerSuccessRateSplit


class PlayerGameSuccessRate(_ResponseModel):
    """Represent one player's passing and rushing success rates for a game."""

    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    game_id: int = Field(alias="gameId", gt=0)
    id: str
    name: str
    position: str
    team: str
    conference: str
    opponent: str
    passing: PlayerSuccessRateSplit
    rushing: PlayerSuccessRateSplit


class TeamStat(_ResponseModel):
    """Represent one season-level team statistic without scalar coercion."""

    season: int = Field(ge=1869)
    team: str
    conference: str
    stat_name: str = Field(alias="statName")
    stat_value: str | int | float = Field(alias="statValue")

    @field_validator("stat_value", mode="before")
    @classmethod
    def reject_non_stat_scalars(cls, value: object) -> object:
        """Accept only upstream string and numeric statistic values."""
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise ValueError("statValue must be a string or number")
        return value


class StatCategory(_ResponseModel):
    """Represent one team-stat category for tabular presentation."""

    category: str


class FieldPosition(_ResponseModel):
    """Represent average starting field position and predicted points."""

    average_start: float | None = Field(alias="averageStart")
    average_predicted_points: float | None = Field(alias="averagePredictedPoints")


class Havoc(_ResponseModel):
    """Represent aggregate havoc rates by position group."""

    total: float | None
    front_seven: float | None = Field(alias="frontSeven")
    db: float | None


class SeasonDownStats(_ResponseModel):
    """Represent advanced season metrics for one down classification."""

    rate: float
    ppa: float
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None


class SeasonPassingDownStats(SeasonDownStats):
    """Represent defensive passing-down season metrics."""

    total_ppa: float = Field(alias="totalPPA")


class SeasonPlayStats(_ResponseModel):
    """Represent advanced season metrics for one play classification."""

    rate: float
    ppa: float
    total_ppa: float = Field(alias="totalPPA")
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None


class AdvancedSeasonOffense(_ResponseModel):
    """Represent a team's advanced season offense metrics."""

    plays: int = Field(ge=0)
    drives: int = Field(ge=0)
    ppa: float
    total_ppa: float = Field(alias="totalPPA")
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None
    power_success: float | None = Field(alias="powerSuccess")
    stuff_rate: float = Field(alias="stuffRate")
    line_yards: float = Field(alias="lineYards")
    line_yards_total: int = Field(alias="lineYardsTotal")
    second_level_yards: float = Field(alias="secondLevelYards")
    second_level_yards_total: int = Field(alias="secondLevelYardsTotal")
    open_field_yards: float = Field(alias="openFieldYards")
    open_field_yards_total: int = Field(alias="openFieldYardsTotal")
    total_opportunities: int = Field(alias="totalOpportunies")
    points_per_opportunity: float = Field(alias="pointsPerOpportunity")
    field_position: FieldPosition = Field(alias="fieldPosition")
    havoc: Havoc
    standard_downs: SeasonDownStats = Field(alias="standardDowns")
    passing_downs: SeasonDownStats = Field(alias="passingDowns")
    rushing_plays: SeasonPlayStats = Field(alias="rushingPlays")
    passing_plays: SeasonPlayStats = Field(alias="passingPlays")


class AdvancedSeasonDefense(AdvancedSeasonOffense):
    """Represent a team's advanced season defense metrics."""

    passing_downs: SeasonPassingDownStats = Field(alias="passingDowns")


class AdvancedSeasonStat(_ResponseModel):
    """Represent advanced team metrics aggregated by season."""

    season: int = Field(ge=1869)
    team: str
    conference: str
    offense: AdvancedSeasonOffense
    defense: AdvancedSeasonDefense


class GameDownStats(_ResponseModel):
    """Represent advanced game metrics for one down classification."""

    ppa: float
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None


class GamePlayStats(_ResponseModel):
    """Represent advanced game metrics for one play classification."""

    ppa: float
    total_ppa: float = Field(alias="totalPPA")
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None


class _AdvancedGameUnit(_ResponseModel):
    """Represent fields shared by advanced game offense and defense."""

    plays: int = Field(ge=0)
    drives: int = Field(ge=0)
    ppa: float
    total_ppa: float = Field(alias="totalPPA")
    success_rate: float = Field(alias="successRate")
    explosiveness: float | None
    power_success: float | None = Field(alias="powerSuccess")
    stuff_rate: float = Field(alias="stuffRate")
    line_yards: float = Field(alias="lineYards")
    line_yards_total: int = Field(alias="lineYardsTotal")
    second_level_yards: float = Field(alias="secondLevelYards")
    second_level_yards_total: int = Field(alias="secondLevelYardsTotal")
    open_field_yards: float | None = Field(alias="openFieldYards")
    open_field_yards_total: int | None = Field(alias="openFieldYardsTotal")
    standard_downs: GameDownStats = Field(alias="standardDowns")
    passing_downs: GameDownStats = Field(alias="passingDowns")
    rushing_plays: GamePlayStats = Field(alias="rushingPlays")
    passing_plays: GamePlayStats = Field(alias="passingPlays")


class AdvancedGameOffense(_AdvancedGameUnit):
    """Represent a team's advanced offense metrics for one game."""

    open_field_yards_total: int = Field(alias="openFieldYardsTotal")


class AdvancedGameDefense(_AdvancedGameUnit):
    """Represent a team's advanced defense metrics for one game."""

    explosiveness: float
    open_field_yards: float = Field(alias="openFieldYards")
    open_field_yards_total: int | None = Field(alias="openFieldYardsTotal")


class AdvancedGameStat(_ResponseModel):
    """Represent advanced team metrics for one game."""

    game_id: int = Field(alias="gameId", gt=0)
    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    team: str
    opponent: str
    offense: AdvancedGameOffense
    defense: AdvancedGameDefense


class GameHavocUnit(_ResponseModel):
    """Represent havoc event counts and rates for one side of a game."""

    total_plays: float = Field(alias="totalPlays", ge=0)
    total_havoc_events: float = Field(alias="totalHavocEvents", ge=0)
    front_seven_havoc_events: float = Field(alias="frontSevenHavocEvents", ge=0)
    db_havoc_events: float = Field(alias="dbHavocEvents", ge=0)
    havoc_rate: float = Field(alias="havocRate")
    front_seven_havoc_rate: float = Field(alias="frontSevenHavocRate")
    db_havoc_rate: float = Field(alias="dbHavocRate")


class GameHavocStats(_ResponseModel):
    """Represent team havoc statistics for one game."""

    game_id: int = Field(alias="gameId", gt=0)
    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    team: str
    conference: str | None
    opponent: str
    opponent_conference: str | None = Field(alias="opponentConference")
    offense: GameHavocUnit
    defense: GameHavocUnit


__all__ = [
    "AdvancedGameDefense",
    "AdvancedGameOffense",
    "AdvancedGameStat",
    "AdvancedSeasonDefense",
    "AdvancedSeasonOffense",
    "AdvancedSeasonStat",
    "FieldPosition",
    "GameDownStats",
    "GameHavocStats",
    "GameHavocUnit",
    "GamePlayStats",
    "Havoc",
    "PlayerGameSuccessRate",
    "PlayerSeasonSuccessRate",
    "PlayerStat",
    "PlayerSuccessRateSplit",
    "SeasonDownStats",
    "SeasonPassingDownStats",
    "SeasonPlayStats",
    "StatCategory",
    "TeamStat",
]
