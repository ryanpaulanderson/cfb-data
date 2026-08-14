"""Validate responses from implemented CFBD Plays endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data._catalog.models import DriveFact, PlayFact, VocabularyFact
from cfb_data._catalog.projection import (
    CatalogSink,
    ObservationAuthority,
    ProjectionContext,
    observe_athlete,
    observe_game,
    observe_team,
)


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to response models."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def require_utc_datetimes(cls, value: object) -> object:
        """Require aware response timestamps and normalize them to UTC.

        :param value: Validated response field value.
        :return: UTC-normalized datetime or the unchanged non-datetime value.
        :raises ValueError: If a datetime does not identify an instant.
        """
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Response timestamps must be timezone-aware")
        return value.astimezone(UTC)


class PlayClock(_ResponseModel):
    """Represent time remaining in a play's period."""

    minutes: int | None = Field(ge=0)
    seconds: int | None = Field(ge=0)


class Play(_ResponseModel):
    """Represent one historical play returned by ``GET /plays``."""

    id: str
    drive_id: str = Field(alias="driveId")
    game_id: int = Field(alias="gameId", gt=0)
    drive_number: int | None = Field(alias="driveNumber", ge=0)
    play_number: int | None = Field(alias="playNumber", ge=0)
    offense: str
    offense_conference: str | None = Field(alias="offenseConference")
    offense_score: int = Field(alias="offenseScore", ge=0)
    defense: str
    home: str
    away: str
    defense_conference: str | None = Field(alias="defenseConference")
    defense_score: int = Field(alias="defenseScore", ge=0)
    period: int = Field(ge=0)
    clock: PlayClock
    offense_timeouts: int | None = Field(alias="offenseTimeouts")
    defense_timeouts: int | None = Field(alias="defenseTimeouts")
    yardline: int = Field(ge=0)
    yards_to_goal: int = Field(alias="yardsToGoal", ge=0)
    down: int = Field(ge=0)
    distance: int = Field(ge=0)
    yards_gained: int = Field(alias="yardsGained")
    scoring: bool
    play_type: str = Field(alias="playType")
    play_text: str | None = Field(alias="playText")
    ppa: float | None
    wallclock: datetime | None

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one historical play and its drive relationship."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        sink.add(
            PlayFact(self.id, self.game_id, self.drive_id, None, self.play_type),
            source=source,
        )
        sink.add(DriveFact(self.drive_id, self.game_id), source=source)


class PlayType(_ResponseModel):
    """Represent one available historical play type."""

    id: int = Field(gt=0)
    text: str
    abbreviation: str | None

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one play-type vocabulary value."""
        sink.add(
            VocabularyFact("play_type", str(self.id), self.text, self.abbreviation),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class PlayStat(_ResponseModel):
    """Represent one athlete statistic associated with a play."""

    game_id: int = Field(alias="gameId", gt=0)
    season: int = Field(ge=1869)
    week: int = Field(ge=0)
    team: str
    conference: str
    opponent: str
    team_score: int = Field(alias="teamScore", ge=0)
    opponent_score: int = Field(alias="opponentScore", ge=0)
    drive_id: str = Field(alias="driveId")
    play_id: str = Field(alias="playId")
    period: int = Field(ge=0)
    clock: PlayClock
    yards_to_goal: int = Field(alias="yardsToGoal", ge=0)
    down: int = Field(ge=0)
    distance: int = Field(ge=0)
    athlete_id: str = Field(alias="athleteId")
    athlete_name: str = Field(alias="athleteName")
    stat_type: str = Field(alias="statType")
    stat: int

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project play, drive, and athlete membership from one stat row."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        sink.add(PlayFact(self.play_id, self.game_id, self.drive_id), source=source)
        sink.add(DriveFact(self.drive_id, self.game_id), source=source)
        observe_athlete(
            sink,
            id=self.athlete_id,
            name=self.athlete_name,
            team=self.team,
            season=self.season,
            source=source,
        )


class PlayStatType(_ResponseModel):
    """Represent one available athlete play-stat type."""

    id: int = Field(gt=0)
    name: str

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one play-stat vocabulary value."""
        sink.add(
            VocabularyFact("play_stat_type", str(self.id), self.name),
            authority=ObservationAuthority.authoritative,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class HomeAway(StrEnum):
    """Identify whether a live-game team is home or away."""

    home = "home"
    away = "away"


class RushPass(StrEnum):
    """Classify a live play by its offensive action."""

    rush = "rush"
    pass_ = "pass"
    other = "other"


class DownType(StrEnum):
    """Classify a live play's down and distance."""

    passing = "passing"
    standard = "standard"


class LiveGamePlay(_ResponseModel):
    """Represent one play nested within a live drive."""

    id: str
    home_score: int = Field(alias="homeScore", ge=0)
    away_score: int = Field(alias="awayScore", ge=0)
    period: int = Field(ge=0)
    clock: str | None
    wall_clock: datetime = Field(alias="wallClock")
    team_id: int = Field(alias="teamId", gt=0)
    team: str
    down: int = Field(ge=0)
    distance: int = Field(ge=0)
    yards_to_goal: int = Field(alias="yardsToGoal", ge=0)
    yards_gained: int = Field(alias="yardsGained")
    play_type_id: int = Field(alias="playTypeId", gt=0)
    play_type: str = Field(alias="playType")
    epa: float | None
    garbage_time: bool = Field(alias="garbageTime")
    success: bool
    rush_pass: RushPass = Field(alias="rushPass")
    down_type: DownType = Field(alias="downType")
    play_text: str = Field(alias="playText")

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project a live play using its ancestor drive and game."""
        game = context.parent(LiveGame)
        drive = context.parent(LiveGameDrive)
        if not isinstance(game, LiveGame):
            return
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        drive_id = drive.id if isinstance(drive, LiveGameDrive) else None
        sink.add(
            PlayFact(
                self.id,
                game.id,
                drive_id,
                self.play_type_id,
                self.play_type,
            ),
            source=source,
        )
        observe_team(sink, id=self.team_id, school=self.team, source=source)
        sink.add(
            VocabularyFact("play_type", str(self.play_type_id), self.play_type),
            source=source,
        )


class LiveGameDrive(_ResponseModel):
    """Represent one drive nested within a live game."""

    id: str
    offense_id: int = Field(alias="offenseId", gt=0)
    offense: str
    defense_id: int = Field(alias="defenseId", gt=0)
    defense: str
    play_count: int = Field(alias="playCount", ge=0)
    yards: int
    start_period: int = Field(alias="startPeriod", ge=0)
    start_clock: str | None = Field(alias="startClock")
    start_yards_to_goal: int = Field(alias="startYardsToGoal", ge=0)
    end_period: int | None = Field(alias="endPeriod", ge=0)
    end_clock: str | None = Field(alias="endClock")
    end_yards_to_goal: int | None = Field(alias="endYardsToGoal", ge=0)
    duration: str | None
    scoring_opportunity: bool = Field(alias="scoringOpportunity")
    result: str
    points_gained: int = Field(alias="pointsGained")
    plays: list[LiveGamePlay]

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project a live drive using its ancestor game."""
        game = context.parent(LiveGame)
        if not isinstance(game, LiveGame):
            return
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        sink.add(
            DriveFact(
                self.id,
                game.id,
                self.offense_id,
                self.offense,
                self.defense_id,
                self.defense,
            ),
            source=source,
        )
        observe_team(sink, id=self.offense_id, school=self.offense, source=source)
        observe_team(sink, id=self.defense_id, school=self.defense, source=source)


class LiveGameTeam(_ResponseModel):
    """Represent one team's live-game aggregate metrics."""

    team_id: int = Field(alias="teamId", gt=0)
    team: str
    home_away: HomeAway = Field(alias="homeAway")
    line_scores: list[int] = Field(alias="lineScores")
    points: int = Field(ge=0)
    drives: int = Field(ge=0)
    scoring_opportunities: int = Field(alias="scoringOpportunities", ge=0)
    points_per_opportunity: float = Field(alias="pointsPerOpportunity")
    average_start_yard_line: float | None = Field(alias="averageStartYardLine")
    plays: int = Field(ge=0)
    line_yards: float = Field(alias="lineYards")
    line_yards_per_rush: float = Field(alias="lineYardsPerRush")
    second_level_yards: float = Field(alias="secondLevelYards")
    second_level_yards_per_rush: float = Field(alias="secondLevelYardsPerRush")
    open_field_yards: float = Field(alias="openFieldYards")
    open_field_yards_per_rush: float = Field(alias="openFieldYardsPerRush")
    epa_per_play: float = Field(alias="epaPerPlay")
    total_epa: float = Field(alias="totalEpa")
    passing_epa: float = Field(alias="passingEpa")
    epa_per_pass: float = Field(alias="epaPerPass")
    rushing_epa: float = Field(alias="rushingEpa")
    epa_per_rush: float = Field(alias="epaPerRush")
    success_rate: float = Field(alias="successRate", ge=0, le=1)
    standard_down_success_rate: float = Field(
        alias="standardDownSuccessRate", ge=0, le=1
    )
    passing_down_success_rate: float = Field(alias="passingDownSuccessRate", ge=0, le=1)
    explosiveness: float
    deserve_to_win: float | None = Field(
        default=None,
        alias="deserveToWin",
        ge=0,
        le=1,
    )

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one team from a live-game aggregate."""
        observe_team(
            sink,
            id=self.team_id,
            school=self.team,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )


class LiveGame(_ResponseModel):
    """Represent the nested response returned by ``GET /live/plays``."""

    id: int = Field(gt=0)
    status: str
    period: int | None = Field(ge=0)
    clock: str
    possession: str
    down: int | None = Field(ge=0)
    distance: int | None = Field(ge=0)
    yards_to_goal: int | None = Field(alias="yardsToGoal", ge=0)
    teams: list[LiveGameTeam]
    drives: list[LiveGameDrive]

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project a live game and side-specific team relationships."""
        home_id = next(
            (team.team_id for team in self.teams if team.home_away is HomeAway.home),
            None,
        )
        away_id = next(
            (team.team_id for team in self.teams if team.home_away is HomeAway.away),
            None,
        )
        observe_game(
            sink,
            id=self.id,
            status=self.status,
            home_team_id=home_id,
            away_team_id=away_id,
            authority=ObservationAuthority.canonical,
            source=f"{type(self).__module__}.{type(self).__qualname__}",
        )
