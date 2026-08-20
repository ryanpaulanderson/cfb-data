"""Provide the independently authored plays dataset recipe.

``plays`` reads the public historical Plays source and produces one row per
game-scoped play. Source PPA remains nullable and is never reinterpreted.
Play-by-play win probability is an explicit exact-game enrichment whose
validated source object is attached without changing the base row universe.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability
from cfb_data.metrics.sources import play_win_probabilities
from cfb_data.plays.models.pydantic.responses import Play, PlayClock
from cfb_data.plays.sources import plays as plays_source
from pydantic import BaseModel, ConfigDict, Field


class WinProbabilityCoverage(StrEnum):
    """Describe whether exact play-probability enrichment was requested."""

    not_requested = "not_requested"
    present = "present"


class PlayRow(BaseModel):
    """Represent one source-faithful game-scoped historical play."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    play_id: str = Field(
        description="Game-scoped source play identifier, normalized from id.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    drive_id: str = Field(json_schema_extra={"semantic_type": "identifier"})
    game_id: int = Field(gt=0, json_schema_extra={"semantic_type": "identifier"})
    drive_number: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "dimension"},
    )
    play_number: int | None = Field(
        default=None,
        ge=0,
        json_schema_extra={"semantic_type": "dimension"},
    )
    offense: str = Field(json_schema_extra={"semantic_type": "dimension"})
    offense_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    offense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    defense: str = Field(json_schema_extra={"semantic_type": "dimension"})
    home: str = Field(json_schema_extra={"semantic_type": "dimension"})
    away: str = Field(json_schema_extra={"semantic_type": "dimension"})
    defense_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    defense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    period: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    clock: PlayClock = Field(description="Validated source period clock.")
    clock_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Seconds remaining when both clock components are reported.",
        json_schema_extra={"semantic_type": "measure", "unit": "seconds"},
    )
    offense_timeouts: int | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure"},
    )
    defense_timeouts: int | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "measure"},
    )
    yardline: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    yards_to_goal: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    down: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    distance: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    yards_gained: int = Field(
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    scoring: bool = Field(description="Source scoring-play indicator.")
    play_type: str = Field(json_schema_extra={"semantic_type": "dimension"})
    play_text: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "text"},
    )
    ppa: float | None = Field(
        default=None,
        description="Nullable source predicted points added.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    wallclock: datetime | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "time"},
    )
    win_probability_coverage: WinProbabilityCoverage = Field(
        description="Whether exact game-scoped probability enrichment is present."
    )
    win_probability: PlayWinProbability | None = Field(
        default=None,
        description="Validated source probability observation for this play.",
    )


@step(
    id="cfbd.plays.normalize",
    revision=1,
    output=PlayRow,
    deterministic=True,
)
def normalize_plays(
    rows: list[Play],
    game_id: int | None,
) -> list[PlayRow]:
    """Normalize plays, optionally selecting one explicit game.

    :param rows: Validated source plays in upstream order.
    :param game_id: Optional exact game retained from the containing partition.
    :return: Base play rows in deterministic source sequence.
    """
    selected = (row for row in rows if game_id is None or row.game_id == game_id)
    return _sort_rows([_normalize_play(row) for row in selected])


@step(
    id="cfbd.plays.attach_win_probability",
    revision=1,
    output=PlayRow,
    deterministic=True,
)
def attach_win_probability(
    rows: list[Play],
    probabilities: list[PlayWinProbability],
    game_id: int,
) -> list[PlayRow]:
    """Attach exact ID-keyed probabilities without changing the play universe.

    :param rows: Validated plays from the smallest selectable partition.
    :param probabilities: Validated exact-game probability observations.
    :param game_id: Explicit game whose rows may enter the output.
    :return: Enriched play rows in deterministic source sequence.
    :raises ValueError: If enrichment is incomplete, duplicated, or mismatched.
    """
    selected = [row for row in rows if row.game_id == game_id]
    base_ids = [row.id for row in selected]
    if len(base_ids) != len(set(base_ids)):
        raise ValueError("Historical plays contain duplicate game/play keys")

    by_play: dict[str, PlayWinProbability] = {}
    for probability in probabilities:
        if probability.game_id != game_id:
            raise ValueError("Win probability contains a different game")
        if probability.play_id in by_play:
            raise ValueError("Win probability contains duplicate game/play keys")
        by_play[probability.play_id] = probability

    if set(by_play) != set(base_ids):
        raise ValueError("Requested win probability does not exactly cover plays")

    enriched = [
        _normalize_play(row, win_probability=by_play[row.id]) for row in selected
    ]
    return _sort_rows(enriched)


@dataset(
    id="cfbd.plays",
    revision=1,
    row=PlayRow,
    grain="one game-scoped historical play",
    keys=("game_id", "play_id"),
    order_by=("game_id", "drive_number", "play_number", "play_id"),
    partition_by=("game_id",),
    event_time="wallclock",
)
def plays(
    *,
    year: int,
    week: int,
    team: str | None = None,
    offense: str | None = None,
    defense: str | None = None,
    offense_conference: str | None = None,
    defense_conference: str | None = None,
    conference: str | None = None,
    play_type: str | None = None,
    season_type: SeasonType | None = None,
    classification: Classification | None = None,
    game_id: int | None = None,
    include_win_probability: bool = False,
) -> RecipeRef[list[PlayRow]]:
    """Build historical play rows with optional exact-game probability.

    :param year: Required season year for the containing source partition.
    :param week: Required season week for the containing source partition.
    :param team: Optional participating-team selector.
    :param offense: Optional offensive-team selector.
    :param defense: Optional defensive-team selector.
    :param offense_conference: Optional offensive-conference selector.
    :param defense_conference: Optional defensive-conference selector.
    :param conference: Optional participating-conference selector.
    :param play_type: Optional source play-type selector.
    :param season_type: Optional season phase.
    :param classification: Optional classification selector.
    :param game_id: Optional exact game retained from the selected partition.
    :param include_win_probability: Request exact game-scoped probability data.
    :return: A reference to the validated plays dataset.
    :raises ValueError: If probability is requested without an exact game ID.
    """
    source_rows = plays_source(
        year=year,
        week=week,
        team=team,
        offense=offense,
        defense=defense,
        offense_conference=offense_conference,
        defense_conference=defense_conference,
        conference=conference,
        play_type=play_type,
        season_type=season_type,
        classification=classification,
    )
    if not include_win_probability:
        return normalize_plays(source_rows, game_id)
    if game_id is None:
        raise ValueError("include_win_probability requires an exact game_id")
    return attach_win_probability(
        source_rows,
        play_win_probabilities(game_id=game_id),
        game_id,
    )


def _clock_seconds(clock: PlayClock) -> int | None:
    if clock.minutes is None or clock.seconds is None:
        return None
    return clock.minutes * 60 + clock.seconds


def _normalize_play(
    play: Play,
    *,
    win_probability: PlayWinProbability | None = None,
) -> PlayRow:
    return PlayRow(
        play_id=play.id,
        drive_id=play.drive_id,
        game_id=play.game_id,
        drive_number=play.drive_number,
        play_number=play.play_number,
        offense=play.offense,
        offense_conference=play.offense_conference,
        offense_score=play.offense_score,
        defense=play.defense,
        home=play.home,
        away=play.away,
        defense_conference=play.defense_conference,
        defense_score=play.defense_score,
        period=play.period,
        clock=play.clock,
        clock_seconds=_clock_seconds(play.clock),
        offense_timeouts=play.offense_timeouts,
        defense_timeouts=play.defense_timeouts,
        yardline=play.yardline,
        yards_to_goal=play.yards_to_goal,
        down=play.down,
        distance=play.distance,
        yards_gained=play.yards_gained,
        scoring=play.scoring,
        play_type=play.play_type,
        play_text=play.play_text,
        ppa=play.ppa,
        wallclock=play.wallclock,
        win_probability_coverage=(
            WinProbabilityCoverage.present
            if win_probability is not None
            else WinProbabilityCoverage.not_requested
        ),
        win_probability=win_probability,
    )


def _sort_rows(rows: list[PlayRow]) -> list[PlayRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.game_id,
            row.drive_number is None,
            row.drive_number if row.drive_number is not None else 0,
            row.play_number is None,
            row.play_number if row.play_number is not None else 0,
            row.play_id,
        ),
    )


__all__ = ["PlayRow", "WinProbabilityCoverage", "plays"]
