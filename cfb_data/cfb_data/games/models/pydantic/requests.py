"""Validate request parameters for implemented Games endpoints."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data._request_rules import (
    _validate_at_least_one_of,
    _validate_game_stats_selectors,
    _validate_year_or_game_id,
)
from cfb_data.enums import (
    Classification,
    MediaType,
    PlayoffCompetition,
    PlayoffRound,
    SeasonType,
)


class GamesRequest(BaseModel):
    """Validate filters accepted by ``GET /games``.

    :param year: Season year, required unless ``game_id`` is supplied.
    :param week: Non-negative season week.
    :param season_type: Season phase.
    :param team: Team appearing on either side of the game.
    :param home: Home-team selector.
    :param away: Away-team selector.
    :param conference: Conference selector.
    :param classification: Division classification selector.
    :param game_id: Positive game identifier serialized as upstream ``id``.
    :param competition: Playoff competition selector.
    :param round: Playoff round, requiring ``competition``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    home: str | None = None
    away: str | None = None
    conference: str | None = None
    classification: Classification | None = None
    game_id: int | None = Field(default=None, gt=0, serialization_alias="id")
    competition: PlayoffCompetition | None = None
    round: PlayoffRound | None = None

    @model_validator(mode="after")
    def validate_selectors(self) -> Self:
        """Validate year/game and playoff selector relationships.

        :return: Validated request.
        :raises ValueError: If required selectors are absent or incompatible.
        """
        _validate_year_or_game_id(self.year, self.game_id)
        if self.round is not None and self.competition is None:
            raise ValueError(
                "competition parameter is required when round is specified"
            )
        if (
            self.competition is PlayoffCompetition.cfp
            and self.season_type is not None
            and self.season_type not in {SeasonType.postseason, SeasonType.both}
        ):
            raise ValueError("CFP games are postseason games")
        return self


class CalendarRequest(BaseModel):
    """Validate filters accepted by ``GET /calendar``.

    :param year: Required season year.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)


class RecordsRequest(BaseModel):
    """Validate filters accepted by ``GET /records``.

    :param year: Optional season year.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    team: str | None = None
    conference: str | None = None

    @model_validator(mode="after")
    def validate_year_or_team(self) -> Self:
        """Require one of the two upstream record selectors.

        :return: Validated request.
        :raises ValueError: If neither ``year`` nor ``team`` is supplied.
        """
        _validate_at_least_one_of(
            {"year": self.year, "team": self.team},
            ("year", "team"),
        )
        return self


class ScoreboardRequest(BaseModel):
    """Validate filters accepted by ``GET /scoreboard``.

    Omitting ``classification`` preserves the upstream ``fbs`` default.

    :param classification: Optional division classification selector.
    :param conference: Optional conference name or abbreviation.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    classification: Classification | None = None
    conference: str | None = None


class GameMediaRequest(BaseModel):
    """Validate filters accepted by ``GET /games/media``.

    :param year: Required season year.
    :param week: Optional non-negative season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param media_type: Optional broadcast-medium selector.
    :param classification: Optional division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int = Field(ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    media_type: MediaType | None = Field(default=None, alias="mediaType")
    classification: Classification | None = None


class GameWeatherRequest(BaseModel):
    """Validate filters accepted by ``GET /games/weather``.

    :param game_id: Positive game identifier serialized as upstream ``gameId``.
    :param year: Season year, required unless ``game_id`` is supplied.
    :param week: Optional non-negative season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param classification: Optional division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_id: int | None = Field(default=None, gt=0, serialization_alias="gameId")
    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_weather_requirements(self) -> Self:
        """Require a year when no game ID selects one game.

        :return: Validated request.
        :raises ValueError: If both ``game_id`` and ``year`` are absent.
        """
        if self.game_id is None and self.year is None:
            raise ValueError("year is required when game_id is not specified")
        return self


class PlayerGameStatsRequest(BaseModel):
    """Validate filters accepted by ``GET /games/players``.

    :param year: Season year used for a grouped selector.
    :param week: Optional non-negative season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param category: Optional player-stat category.
    :param game_id: Positive game identifier serialized as upstream ``id``.
    :param classification: Optional division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    category: str | None = None
    game_id: int | None = Field(default=None, gt=0, serialization_alias="id")
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_player_stats_requirements(self) -> Self:
        """Validate the game-ID or grouped-selector alternatives.

        :return: Validated request.
        :raises ValueError: If the grouped selector is incomplete.
        """
        _validate_game_stats_selectors(
            self.year, self.week, self.team, self.conference, self.game_id
        )
        return self


class TeamGameStatsRequest(BaseModel):
    """Validate filters accepted by ``GET /games/teams``.

    :param year: Season year used for a grouped selector.
    :param week: Optional non-negative season week.
    :param season_type: Optional season phase.
    :param team: Optional team selector.
    :param conference: Optional conference selector.
    :param game_id: Positive game identifier serialized as upstream ``id``.
    :param classification: Optional division classification selector.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    year: int | None = Field(default=None, ge=1869)
    week: int | None = Field(default=None, ge=0)
    season_type: SeasonType | None = Field(default=None, alias="seasonType")
    team: str | None = None
    conference: str | None = None
    game_id: int | None = Field(default=None, gt=0, serialization_alias="id")
    classification: Classification | None = None

    @model_validator(mode="after")
    def validate_team_stats_requirements(self) -> Self:
        """Validate the game-ID or grouped-selector alternatives.

        :return: Validated request.
        :raises ValueError: If the grouped selector is incomplete.
        """
        _validate_game_stats_selectors(
            self.year, self.week, self.team, self.conference, self.game_id
        )
        return self


class AdvancedBoxScoreRequest(BaseModel):
    """Validate filters accepted by ``GET /game/box/advanced``.

    :param game_id: Required positive game identifier serialized as upstream
        ``id``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_id: int = Field(gt=0, serialization_alias="id")
