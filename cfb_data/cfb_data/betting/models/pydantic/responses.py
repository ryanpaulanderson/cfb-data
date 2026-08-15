"""Validate responses from implemented CFBD Betting endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cfb_data._catalog.projection import (
    CatalogSink,
    ProjectionContext,
    observe_game,
    observe_team,
)
from cfb_data.enums import Classification, SeasonType


class _ResponseModel(BaseModel):
    """Apply the upstream closed-object contract to Betting responses."""

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


class GameLine(_ResponseModel):
    """Represent one provider's line for a game."""

    provider: str
    spread: float | None
    formatted_spread: str = Field(alias="formattedSpread")
    spread_open: float | None = Field(alias="spreadOpen")
    over_under: float | None = Field(alias="overUnder")
    over_under_open: float | None = Field(alias="overUnderOpen")
    home_moneyline: int | None = Field(alias="homeMoneyline")
    away_moneyline: int | None = Field(alias="awayMoneyline")


class BettingGame(_ResponseModel):
    """Represent one game and all returned provider lines."""

    id: int = Field(gt=0)
    season: int = Field(ge=1869)
    season_type: SeasonType = Field(alias="seasonType")
    week: int = Field(ge=0)
    start_date: datetime = Field(alias="startDate")
    home_team_id: int = Field(alias="homeTeamId", gt=0)
    home_team: str = Field(alias="homeTeam")
    home_conference: str | None = Field(alias="homeConference")
    home_classification: Classification | None = Field(alias="homeClassification")
    home_score: int | None = Field(alias="homeScore", ge=0)
    away_team_id: int = Field(alias="awayTeamId", gt=0)
    away_team: str = Field(alias="awayTeam")
    away_conference: str | None = Field(alias="awayConference")
    away_classification: Classification | None = Field(alias="awayClassification")
    away_score: int | None = Field(alias="awayScore", ge=0)
    lines: list[GameLine]

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Project one betting game and both provider team identities."""
        source = f"{type(self).__module__}.{type(self).__qualname__}"
        observe_game(
            sink,
            id=self.id,
            season=self.season,
            week=self.week,
            season_type=self.season_type,
            start_date=self.start_date,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            source=source,
        )
        observe_team(sink, id=self.home_team_id, school=self.home_team, source=source)
        observe_team(sink, id=self.away_team_id, school=self.away_team, source=source)


__all__ = ["BettingGame", "GameLine"]
