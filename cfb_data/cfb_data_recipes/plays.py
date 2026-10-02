"""Provide the independently authored plays dataset recipe.

``plays`` reads the public historical Plays source and produces one row per
game-scoped play. Source PPA remains nullable and is never reinterpreted.
Play-by-play win probability is an explicit exact-game enrichment whose
validated source object is attached without changing the base row universe.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability
from cfb_data.metrics.sources import play_win_probabilities
from cfb_data.plays.models.pydantic.responses import PlayClock
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
    revision=2,
    output=PlayRow,
    deterministic=True,
)
def normalize_plays(rows: Table, game_id: int | None) -> Table:
    """Normalize native plays while preserving nullable source observations.

    :param rows: Validated native source table.
    :param game_id: Optional selected exact game.
    :return: Globally ordered base play table.
    """
    return _project_plays(rows, game_id)


@step(
    id="cfbd.plays.attach_win_probability",
    revision=2,
    output=PlayRow,
    deterministic=True,
)
def attach_win_probability(rows: Table, probabilities: Table, game_id: int) -> Table:
    """Join exact-cover probability evidence using global native checks.

    :param rows: Validated source plays for the containing API partition.
    :param probabilities: Requested exact-game probability table.
    :param game_id: Selected exact game identifier.
    :return: Native plays with exact one-to-one probability coverage.
    """
    base = _project_plays(rows, game_id)
    base = base.require_unique(
        ("game_id", "play_id"),
        message="Historical plays contain duplicate game/play keys",
    )
    probabilities = probabilities.require(
        nw.col("game_id") == game_id,
        message="Win probability contains a different game",
    )
    return (
        base.drop("win_probability", "win_probability_coverage")
        .enrich(
            probabilities,
            on=("game_id", "play_id"),
            output="win_probability",
            coverage="win_probability_coverage",
            fields={name: name for name in PlayWinProbability.model_fields},
            outside="reject",
            completeness="required",
            message="Requested win probability does not exactly cover plays",
        )
        .select(*PlayRow.model_fields)
        .sort("game_id", "drive_number", "play_number", "play_id")
    )


@dataset(
    id="cfbd.plays",
    revision=2,
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
) -> RecipeRef[Table]:
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


def _project_plays(rows: Table, game_id: int | None) -> Table:
    """Project historical plays through native nullable expressions.

    :param rows: Validated source play table.
    :param game_id: Optional exact game selector within the source partition.
    :return: Ordered native plays with source PPA and clocks preserved.
    """
    if game_id is not None:
        rows = rows.filter(nw.col("game_id") == game_id)
    rows = rows.rename({"id": "play_id"}).nested(
        "clock",
        fields={"minutes": "__minutes", "seconds": "__seconds"},
        dtypes={"__minutes": "Int64", "__seconds": "Int64"},
    )
    return (
        rows.with_columns(
            (nw.col("__minutes") * 60 + nw.col("__seconds")).alias("clock_seconds"),
            nw.lit("not_requested").alias("win_probability_coverage"),
            nw.lit(None).alias("win_probability"),
        )
        .select(*PlayRow.model_fields)
        .sort("game_id", "drive_number", "play_number", "play_id")
    )


__all__ = ["PlayRow", "WinProbabilityCoverage", "plays"]
