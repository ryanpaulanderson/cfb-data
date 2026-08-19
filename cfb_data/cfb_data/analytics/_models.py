"""Define authoritative row and parameter models for built-in analytics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.betting.models.pydantic.responses import GameLine
from cfb_data.coaches.models.pydantic.responses import DetailedCoachSeason
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.enums import Classification, RankingPoll, SeasonType
from cfb_data.games.models.pydantic.responses import (
    Game,
    TeamGameStat,
    TeamRecords,
)
from cfb_data.plays.models.pydantic.responses import Play
from cfb_data.recruiting.models.pydantic.responses import Recruit
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
)
from cfb_data.teams.models.pydantic.responses import RosterPlayer


class _AnalyticsModel(BaseModel):
    """Apply a closed, name-populated contract to analytical models."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class GameResultState(StrEnum):
    """Describe whether game result metrics are semantically available."""

    scheduled = "scheduled"
    incomplete = "incomplete"
    completed = "completed"
    tie = "tie"


class GameSummary(Game):
    """Preserve one game and add conservative result semantics."""

    result_state: GameResultState
    home_margin: int | None
    total_points: int | None = Field(ge=0)
    winner_id: int | None = Field(ge=0)
    loser_id: int | None = Field(ge=0)


class TeamGameRow(_AnalyticsModel):
    """Represent one team perspective in one game."""

    game_id: int = Field(gt=0)
    season: int = Field(ge=1869)
    week: int = Field(ge=0)
    season_type: SeasonType
    start_date: datetime
    team_id: int = Field(ge=0)
    team: str
    conference: str | None
    classification: Classification | None
    home_away: str = Field(pattern="^(home|away)$")
    opponent_id: int = Field(ge=0)
    opponent: str
    points_for: int | None = Field(ge=0)
    points_against: int | None = Field(ge=0)
    point_differential: int | None
    result: str | None = Field(pattern="^(W|L|T)$")
    completed: bool
    stats: list[TeamGameStat]


class PlayerGameStatRow(_AnalyticsModel):
    """Represent one athlete display statistic in one game."""

    game_id: int = Field(gt=0)
    team_id: int = Field(ge=0)
    team: str
    home_away: str = Field(pattern="^(home|away)$")
    conference: str | None
    team_points: int | None = Field(ge=0)
    athlete_id: str
    athlete_name: str
    category: str
    stat_type: str
    stat: str


class DriveRow(Drive):
    """Add explicit clock and score arithmetic to one drive."""

    start_clock_seconds: int | None = Field(ge=0)
    end_clock_seconds: int | None = Field(ge=0)
    elapsed_seconds: int | None = Field(ge=0)
    points_gained: int
    end_score_differential: int


class PlayRow(Play):
    """Add explicit clock and team-perspective arithmetic to one play."""

    clock_seconds: int | None = Field(ge=0)
    score_differential: int
    is_home_offense: bool


class RosterMembership(RosterPlayer):
    """Attach the requested roster season without conflating class year."""

    season: int = Field(ge=1869)


class TeamSeasonRow(TeamRecords):
    """Compose a record-established team season with typed stat groups."""

    stats: list[TeamStat]
    advanced: AdvancedSeasonStat | None


class PlayerSeasonRow(_AnalyticsModel):
    """Compose roster and season-stat evidence for one athlete membership."""

    season: int = Field(ge=1869)
    team: str
    athlete_id: str
    athlete_name: str
    position: str | None
    conference: str | None
    roster: RosterPlayer | None
    stats: list[PlayerStat]
    roster_present: bool
    stats_present: bool


class PollRankingRow(_AnalyticsModel):
    """Represent one team position in one poll snapshot."""

    season: int = Field(ge=1869)
    season_type: SeasonType
    week: int = Field(ge=0)
    poll: str
    poll_ordinal: int = Field(ge=0)
    is_final: bool | None
    rank_ordinal: int = Field(ge=0)
    rank: int | None = Field(ge=1)
    team_id: int = Field(gt=0)
    school: str
    conference: str | None
    first_place_votes: int | None = Field(ge=0)
    points: int | None = Field(ge=0)


class BettingLineRow(_AnalyticsModel):
    """Represent one provider quote for one game without quote selection."""

    game_id: int = Field(gt=0)
    season: int = Field(ge=1869)
    season_type: SeasonType
    week: int = Field(ge=0)
    start_date: datetime
    home_team_id: int = Field(gt=0)
    home_team: str
    home_score: int | None = Field(ge=0)
    away_team_id: int = Field(gt=0)
    away_team: str
    away_score: int | None = Field(ge=0)
    source_ordinal: int = Field(ge=0)
    provider: str
    quote: GameLine


class RecruitingClassRow(_AnalyticsModel):
    """Represent one team recruiting class with explicit commitment coverage."""

    class_year: int = Field(ge=1869)
    source_team: str
    rank: int | None = Field(ge=1)
    points: float | None
    recruits: list[Recruit]
    committed_recruits: int = Field(ge=0)
    uncommitted_recruits: int = Field(ge=0)


class CoachSeasonRow(DetailedCoachSeason):
    """Provide a stable analytical contract for one coach-team season."""


class GameDatasetParams(_AnalyticsModel):
    """Validate selectors shared by game-shaped analytical products."""

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = None
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    game_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_selector(self) -> Self:
        """Require a year or one game ID."""
        if self.year is None and self.game_id is None:
            raise ValueError("year is required when game_id is not specified")
        return self


class GameDetailParams(GameDatasetParams):
    """Require a bounded game-stat partition."""

    @model_validator(mode="after")
    def validate_detail_selector(self) -> Self:
        """Require a game ID or a bounded year partition."""
        if self.game_id is not None:
            return self
        if self.year is None or (
            self.week is None and self.team is None and self.conference is None
        ):
            raise ValueError(
                "game_id or year with week, team, or conference is required"
            )
        return self


class DriveDatasetParams(_AnalyticsModel):
    """Validate one bounded historical drive selection."""

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = None
    team: str | None = Field(default=None, min_length=1)
    offense: str | None = Field(default=None, min_length=1)
    defense: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    game_id: int | None = Field(default=None, gt=0)


class PlayDatasetParams(_AnalyticsModel):
    """Validate one exact historical play partition."""

    year: int = Field(ge=1869)
    week: int = Field(ge=0)
    season_type: SeasonType | None = None
    team: str | None = Field(default=None, min_length=1)
    offense: str | None = Field(default=None, min_length=1)
    defense: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    game_id: int | None = Field(default=None, gt=0)


class RosterDatasetParams(_AnalyticsModel):
    """Validate a roster season and optional team selector."""

    season: int = Field(ge=1869)
    team: str | None = Field(default=None, min_length=1)
    classification: Classification | None = None


class TeamSeasonParams(_AnalyticsModel):
    """Validate one season or team-shaped team-season selection."""

    season: int | None = Field(default=None, ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selector(self) -> Self:
        """Require a season or team."""
        if self.season is None and self.team is None:
            raise ValueError("season is required when team is not specified")
        return self


class PlayerSeasonParams(_AnalyticsModel):
    """Validate a player-season selection."""

    season: int = Field(ge=1869)
    team: str | None = Field(default=None, min_length=1)
    conference: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)


class RankingsParams(_AnalyticsModel):
    """Validate a historical poll selection."""

    season: int = Field(ge=1869)
    season_type: SeasonType | None = None
    week: int | None = Field(default=None, ge=0)
    poll: RankingPoll | None = None
    team: str | None = Field(default=None, min_length=1)


class BettingParams(_AnalyticsModel):
    """Validate a game or season betting-line selection."""

    game_id: int | None = Field(default=None, gt=0)
    season: int | None = Field(default=None, ge=1869)
    season_type: SeasonType | None = None
    week: int | None = Field(default=None, ge=0)
    team: str | None = Field(default=None, min_length=1)
    provider: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selector(self) -> Self:
        """Require a game or season."""
        if self.game_id is None and self.season is None:
            raise ValueError("season is required when game_id is not specified")
        return self


class RecruitingParams(_AnalyticsModel):
    """Validate a recruiting-class selection."""

    class_year: int = Field(ge=1869)
    team: str | None = Field(default=None, min_length=1)


class CoachSeasonParams(_AnalyticsModel):
    """Validate coach-season selectors without per-coach profile fan-out."""

    team: str | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, ge=1869)
    min_year: int | None = Field(default=None, ge=1869)
    max_year: int | None = Field(default=None, ge=1869)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Reject reversed ranges and require one bounded selector."""
        if (
            self.min_year is not None
            and self.max_year is not None
            and self.min_year > self.max_year
        ):
            raise ValueError("min_year cannot be greater than max_year")
        if self.team is None and self.year is None and self.min_year is None:
            raise ValueError("team, year, or min_year is required")
        return self


class TeamSeasonWorkflowParams(_AnalyticsModel):
    """Validate the built-in team-season workflow selection."""

    season: int = Field(ge=1869)
    team: str = Field(min_length=1)


class SingleGameWorkflowParams(_AnalyticsModel):
    """Validate one single-game workflow selection."""

    game_id: int = Field(gt=0)


class ProgramHistoryParams(_AnalyticsModel):
    """Validate one bounded multi-season program-history selection."""

    team: str = Field(min_length=1)
    start_year: int = Field(ge=1869)
    end_year: int = Field(ge=1869)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Reject a reversed program-history range."""
        if self.start_year > self.end_year:
            raise ValueError("start_year cannot be greater than end_year")
        return self


__all__ = [
    "BettingLineRow",
    "BettingParams",
    "CoachSeasonParams",
    "CoachSeasonRow",
    "DriveDatasetParams",
    "DriveRow",
    "GameDatasetParams",
    "GameDetailParams",
    "GameResultState",
    "GameSummary",
    "PlayerGameStatRow",
    "PlayerSeasonParams",
    "PlayerSeasonRow",
    "PlayDatasetParams",
    "PlayRow",
    "PollRankingRow",
    "ProgramHistoryParams",
    "RankingsParams",
    "RecruitingClassRow",
    "RecruitingParams",
    "RosterDatasetParams",
    "RosterMembership",
    "SingleGameWorkflowParams",
    "TeamGameRow",
    "TeamSeasonParams",
    "TeamSeasonRow",
    "TeamSeasonWorkflowParams",
]
