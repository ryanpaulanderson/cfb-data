"""Provide the independently authored drives dataset recipe.

``drives`` reads the public ``cfb_data.drives.sources.drives`` source and
produces one row per game-scoped drive. The recipe preserves the validated
source clock and score fields, then adds only direct arithmetic whose inputs
are present. It deliberately does not infer drive success from a result label.
"""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset, step
from cfb_data.drives.models.pydantic.responses import Drive, DriveTime
from cfb_data.drives.sources import drives as drives_source
from cfb_data.enums import Classification, SeasonType
from pydantic import BaseModel, ConfigDict, Field


class DriveRow(BaseModel):
    """Represent one source-faithful, game-scoped drive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    offense: str = Field(json_schema_extra={"semantic_type": "dimension"})
    offense_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    defense: str = Field(json_schema_extra={"semantic_type": "dimension"})
    defense_conference: str | None = Field(
        default=None,
        json_schema_extra={"semantic_type": "dimension"},
    )
    game_id: int = Field(ge=0, json_schema_extra={"semantic_type": "identifier"})
    drive_id: str = Field(
        description="Game-scoped source drive identifier, normalized from id.",
        json_schema_extra={"semantic_type": "identifier"},
    )
    drive_number: int | None = Field(
        default=None,
        ge=0,
        description="Nullable source drive sequence number.",
        json_schema_extra={"semantic_type": "dimension"},
    )
    scoring: bool = Field(description="Source scoring-drive indicator.")
    start_period: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    start_yardline: int = Field(json_schema_extra={"semantic_type": "measure"})
    start_yards_to_goal: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    start_time: DriveTime = Field(description="Validated source start clock.")
    end_period: int = Field(ge=0, json_schema_extra={"semantic_type": "dimension"})
    end_yardline: int = Field(json_schema_extra={"semantic_type": "measure"})
    end_yards_to_goal: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    end_time: DriveTime = Field(description="Validated source end clock.")
    elapsed: DriveTime = Field(description="Validated source elapsed clock.")
    plays: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "plays"},
    )
    yards: int = Field(
        json_schema_extra={"semantic_type": "measure", "unit": "yards"},
    )
    drive_result: str = Field(json_schema_extra={"semantic_type": "dimension"})
    is_home_offense: bool = Field(description="Whether offense is the home team.")
    start_offense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    start_defense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    end_offense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    end_defense_score: int = Field(
        ge=0,
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    start_clock_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Seconds remaining in the start period when fully reported.",
        json_schema_extra={"semantic_type": "measure", "unit": "seconds"},
    )
    end_clock_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Seconds remaining in the end period when fully reported.",
        json_schema_extra={"semantic_type": "measure", "unit": "seconds"},
    )
    elapsed_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Elapsed drive seconds when both source components exist.",
        json_schema_extra={"semantic_type": "measure", "unit": "seconds"},
    )
    offense_score_change: int = Field(
        description="End offense score minus start offense score.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )
    defense_score_change: int = Field(
        description="End defense score minus start defense score.",
        json_schema_extra={"semantic_type": "measure", "unit": "points"},
    )


@step(
    id="cfbd.drives.normalize",
    revision=1,
    output=DriveRow,
    deterministic=True,
)
def normalize_drives(rows: list[Drive]) -> list[DriveRow]:
    """Normalize validated drives and compute only direct arithmetic.

    :param rows: Validated source drives in upstream order.
    :return: Drive rows in deterministic game and source-sequence order.
    """
    normalized = [_normalize_drive(row) for row in rows]
    return sorted(
        normalized,
        key=lambda row: (
            row.game_id,
            row.drive_number is None,
            row.drive_number if row.drive_number is not None else 0,
            row.drive_id,
        ),
    )


@dataset(
    id="cfbd.drives",
    revision=1,
    row=DriveRow,
    grain="one game-scoped drive",
    keys=("game_id", "drive_id"),
    order_by=("game_id", "drive_number", "drive_id"),
    partition_by=("game_id",),
)
def drives(
    *,
    year: int,
    season_type: SeasonType | None = None,
    week: int | None = None,
    team: str | None = None,
    offense: str | None = None,
    defense: str | None = None,
    conference: str | None = None,
    offense_conference: str | None = None,
    defense_conference: str | None = None,
    classification: Classification | None = None,
) -> RecipeRef[list[DriveRow]]:
    """Build game-scoped drive rows from the registered Drives source.

    :param year: Required season year.
    :param season_type: Optional season phase.
    :param week: Optional season week.
    :param team: Optional participating-team selector.
    :param offense: Optional offensive-team selector.
    :param defense: Optional defensive-team selector.
    :param conference: Optional participating-conference selector.
    :param offense_conference: Optional offensive-conference selector.
    :param defense_conference: Optional defensive-conference selector.
    :param classification: Optional classification selector.
    :return: A reference to the validated drives dataset.
    """
    return normalize_drives(
        drives_source(
            year=year,
            season_type=season_type,
            week=week,
            team=team,
            offense=offense,
            defense=defense,
            conference=conference,
            offense_conference=offense_conference,
            defense_conference=defense_conference,
            classification=classification,
        )
    )


def _clock_seconds(value: DriveTime) -> int | None:
    if value.minutes is None or value.seconds is None:
        return None
    return value.minutes * 60 + value.seconds


def _normalize_drive(drive: Drive) -> DriveRow:
    return DriveRow(
        offense=drive.offense,
        offense_conference=drive.offense_conference,
        defense=drive.defense,
        defense_conference=drive.defense_conference,
        game_id=drive.game_id,
        drive_id=drive.id,
        drive_number=drive.drive_number,
        scoring=drive.scoring,
        start_period=drive.start_period,
        start_yardline=drive.start_yardline,
        start_yards_to_goal=drive.start_yards_to_goal,
        start_time=drive.start_time,
        end_period=drive.end_period,
        end_yardline=drive.end_yardline,
        end_yards_to_goal=drive.end_yards_to_goal,
        end_time=drive.end_time,
        elapsed=drive.elapsed,
        plays=drive.plays,
        yards=drive.yards,
        drive_result=drive.drive_result,
        is_home_offense=drive.is_home_offense,
        start_offense_score=drive.start_offense_score,
        start_defense_score=drive.start_defense_score,
        end_offense_score=drive.end_offense_score,
        end_defense_score=drive.end_defense_score,
        start_clock_seconds=_clock_seconds(drive.start_time),
        end_clock_seconds=_clock_seconds(drive.end_time),
        elapsed_seconds=_clock_seconds(drive.elapsed),
        offense_score_change=drive.end_offense_score - drive.start_offense_score,
        defense_score_change=drive.end_defense_score - drive.start_defense_score,
    )


__all__ = ["DriveRow", "drives"]
