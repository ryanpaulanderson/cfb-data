"""Provide the independently authored drives dataset recipe.

``drives`` reads the public ``cfb_data.drives.sources.drives`` source and
produces one row per game-scoped drive. The recipe preserves the validated
source clock and score fields, then adds only direct arithmetic whose inputs
are present. It deliberately does not infer drive success from a result label.
"""

from __future__ import annotations

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, dataset, step
from cfb_data.drives.models.pydantic.responses import DriveTime
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
    revision=2,
    output=DriveRow,
    deterministic=True,
)
def normalize_drives(rows: Table, game_id: int | None) -> Table:
    """Project drives and direct arithmetic through native expressions.

    :param rows: Validated source drive table.
    :param game_id: Optional exact game retained from the source partition.
    :return: Globally ordered native drive table with null clocks preserved.
    """
    if game_id is not None:
        rows = rows.filter(nw.col("game_id") == game_id)
    rows = rows.rename({"id": "drive_id"})
    for source, target in (
        ("start_time", "start_clock_seconds"),
        ("end_time", "end_clock_seconds"),
        ("elapsed", "elapsed_seconds"),
    ):
        rows = rows.nested(
            source,
            fields={"minutes": f"__{source}_minutes", "seconds": f"__{source}_seconds"},
            dtypes={f"__{source}_minutes": "Int64", f"__{source}_seconds": "Int64"},
        )
        rows = rows.with_columns(
            (nw.col(f"__{source}_minutes") * 60 + nw.col(f"__{source}_seconds")).alias(
                target
            )
        )
    return (
        rows.with_columns(
            (nw.col("end_offense_score") - nw.col("start_offense_score")).alias(
                "offense_score_change"
            ),
            (nw.col("end_defense_score") - nw.col("start_defense_score")).alias(
                "defense_score_change"
            ),
        )
        .select(*DriveRow.model_fields)
        .sort("game_id", "drive_number", "drive_id")
    )


@dataset(
    id="cfbd.drives",
    revision=2,
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
    game_id: int | None = None,
) -> RecipeRef[Table]:
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
    :param game_id: Optional exact game retained from the containing partition.
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
        ),
        game_id,
    )


__all__ = ["DriveRow", "drives"]
