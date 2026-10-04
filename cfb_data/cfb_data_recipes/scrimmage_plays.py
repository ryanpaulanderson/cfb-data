"""Declare source-faithful play eligibility for calculated football metrics.

Exact source play types establish the action family. Documented text markers
only exclude administrative actions or retain ambiguity; they never silently
turn an unrecognized play into a valid rushing observation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

import narwhals.stable.v2 as nw
from cfb_data.analytics import RecipeRef, Table, concat_tables, dataset, step
from cfb_data.enums import Classification, SeasonType
from cfb_data.plays.sources import plays as plays_source
from pydantic import BaseModel, ConfigDict

from .team_games import team_games

_RUSH: Final = ("Rush", "Rushing Touchdown")
_DROPBACK: Final = (
    "Pass",
    "Pass Reception",
    "Pass Completion",
    "Pass Incompletion",
    "Passing Touchdown",
    "Pass Reception Touchdown",
    "Sack",
    "Sack Touchdown",
    "Interception Return",
    "Interception Return Touchdown",
    "Pass Interception Return",
    "Pass Interception Return Touchdown",
)
_INTERCEPTION: Final = (
    "Interception Return",
    "Interception Return Touchdown",
    "Pass Interception Return",
    "Pass Interception Return Touchdown",
)
_FUMBLE: Final = (
    "Fumble Recovery (Own)",
    "Fumble Recovery (Own) Touchdown",
    "Fumble Recovery (Opponent)",
    "Fumble Recovery (Opponent) Touchdown",
    "Fumble Return Touchdown",
)
_OTHER: Final = (
    "Kickoff",
    "Kickoff Return (Offense)",
    "Kickoff Return (Defense)",
    "Kickoff Return Touchdown",
    "Kickoff Touchdown",
    "Kickoff Team Fumble Recovery",
    "Kickoff Team Fumble Recovery Touchdown",
    "Kickoff (Safety)",
    "Penalty (Kickoff)",
    "Punt",
    "Punt Return",
    "Punt Touchdown",
    "Punt Return Touchdown",
    "Punt Team Fumble Recovery",
    "Punt Team Fumble Recovery Touchdown",
    "Blocked Punt",
    "Blocked Punt Touchdown",
    "Blocked Punt (Safety)",
    "Punt (Safety)",
    "Field Goal Good",
    "Field Goal Missed",
    "Blocked Field Goal",
    "Blocked Field Goal Touchdown",
    "Missed Field Goal Return",
    "Missed Field Goal Return Touchdown",
    "Extra Point Good",
    "Extra Point Missed",
    "Blocked PAT",
    "Two Point Pass",
    "Two Point Rush",
    "Defensive 2pt Conversion",
    "Penalty",
    "Penalty (Safety)",
    "Timeout",
    "End Period",
    "End of Half",
    "End of Game",
    "Start Period",
    "Start of Half",
)


class VenuePerspective(StrEnum):
    """Describe the offense's game venue perspective."""

    home = "home"
    away = "away"
    neutral = "neutral"


class PlayFamily(StrEnum):
    """Describe a proven action family or retained classification uncertainty."""

    rush = "rush"
    dropback = "dropback"
    unknown = "unknown"
    other = "other"


class EvaluationStatus(StrEnum):
    """Distinguish evaluated, excluded and unresolved metric observations."""

    evaluated = "evaluated"
    excluded = "excluded"
    unknown = "unknown"


class ContextCoverage(StrEnum):
    """Describe whether source evidence establishes the preplay score context."""

    known = "known"
    unknown = "unknown"


class TeamUnit(StrEnum):
    """Describe the offensive or defensive perspective on an observation."""

    offense = "offense"
    defense = "defense"


class MetricCoverage(StrEnum):
    """Describe observed metric population coverage without asserting feed completeness."""

    present = "present"
    partial = "partial"
    empty = "empty"
    unavailable = "unavailable"


class ScrimmagePlay(BaseModel):
    """Retain one source play with independent metric eligibility evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    season: int
    week: int
    season_type: SeasonType
    game_id: int
    play_id: str
    drive_id: str
    source_ordinal: int
    start_date: datetime
    completed: bool
    offense_id: int
    offense: str
    defense_id: int
    defense: str
    venue_perspective: VenuePerspective
    drive_number: int | None
    play_number: int | None
    period: int
    clock_seconds: int | None
    down: int
    distance: int
    yards_to_goal: int
    yards_gained: int
    play_type: str
    play_family: PlayFamily
    success_status: EvaluationStatus
    success_reason: str
    successful: bool | None
    rush_status: EvaluationStatus
    rush_reason: str
    line_yards: float | None
    preplay_score_margin: int | None
    score_context: ContextCoverage


def validate_partitions(year: int, weeks: tuple[int, ...]) -> None:
    """Require finite unique historical source partitions before external I/O.

    :param year: Requested season year.
    :param weeks: Explicit season weeks, including possible week zero.
    :raises ValueError: If the season or source partitions are invalid.
    """
    if isinstance(year, bool) or not isinstance(year, int) or year < 1869:
        raise ValueError("year must be a supported integer season")
    if not isinstance(weeks, tuple) or not weeks or len(weeks) > 32:
        raise ValueError("weeks must be a nonempty tuple of at most 32 partitions")
    if any(
        isinstance(week, bool) or not isinstance(week, int) or not 0 <= week <= 32
        for week in weeks
    ):
        raise ValueError("weeks must contain integer partitions from zero to 32")
    if len(set(weeks)) != len(weeks):
        raise ValueError("weeks must not repeat a source partition")


@step(id="cfbd.scrimmage_plays.partition", revision=1, output=ScrimmagePlay)
def classify_partition(rows: Table, games: Table, *, week: int) -> Table:
    """Resolve participants and calculate independently validated play features.

    :param rows: Unfiltered validated raw plays for one requested week.
    :param games: Authoritative team-game participants for the selected season.
    :param week: Source partition week, validated against game metadata.
    :return: Every source play with metric decisions and original ordinal.
    :raises CFBDTransformError: If identities, duplicate keys or state contradict.
    """
    participants = (
        games.normalize_text("team", into="__offense_key")
        .select(
            "game_id",
            "season",
            "week",
            "season_type",
            "start_date",
            "completed",
            "neutral_site",
            "home_away",
            "__offense_key",
            nw.col("team_id").alias("offense_id"),
            nw.col("opponent_id").alias("defense_id"),
            nw.col("opponent").alias("__expected_defense"),
        )
        .normalize_text("__expected_defense", into="__defense_key")
    )
    base = rows.with_row_index("source_ordinal").rename({"id": "play_id"})
    base = (
        base.normalize_text("offense", into="__offense_key")
        .normalize_text("defense", into="__observed_defense")
        .join(participants, on=("game_id", "__offense_key"), cardinality="many_to_one")
    )
    base = (
        base.require_unique(
            ("game_id", "play_id"),
            message="Calculated metrics received duplicate play keys",
        )
        .require(
            ~nw.col("offense_id").is_null()
            & (nw.col("__observed_defense") == nw.col("__defense_key"))
            & (nw.col("week") == week),
            message="Play participants or source week conflict with game evidence",
        )
        .nested(
            "clock",
            fields={"minutes": "__minutes", "seconds": "__seconds"},
            dtypes={"__minutes": "Int64", "__seconds": "Int64"},
        )
        .with_columns(
            nw.col("completed").cast(nw.Boolean),
            nw.col("scoring").cast(nw.Boolean),
            (nw.col("__minutes") * 60 + nw.col("__seconds")).alias("clock_seconds"),
            nw.when(nw.col("neutral_site"))
            .then(nw.lit("neutral"))
            .otherwise(nw.col("home_away"))
            .alias("venue_perspective"),
            nw.when(nw.col("play_type").is_in(_RUSH))
            .then(nw.lit("rush"))
            .when(nw.col("play_type").is_in(_DROPBACK))
            .then(nw.lit("dropback"))
            .when(nw.col("play_type").is_in(_OTHER))
            .then(nw.lit("other"))
            .otherwise(nw.lit("unknown"))
            .alias("play_family"),
        )
    )
    text = nw.col("play_text").fill_null("").str.to_lowercase()
    fumble = nw.col("play_type").is_in(_FUMBLE)
    rush_text = text.str.contains(r"\b(?:run|rush|rushed)\b")
    pass_text = text.str.contains(r"\b(?:pass|passed|sacked)\b")
    kicking_text = text.str.contains(r"\b(?:kickoff|punt|muffed|field goal)\b")
    base = base.with_columns(
        nw.when(fumble & ~kicking_text & rush_text & ~pass_text)
        .then(nw.lit("rush"))
        .when(fumble & ~kicking_text & pass_text & ~rush_text)
        .then(nw.lit("dropback"))
        .otherwise(nw.col("play_family"))
        .alias("play_family"),
    )
    lost_fumble = nw.col("play_type").is_in(
        (
            "Fumble Recovery (Opponent)",
            "Fumble Recovery (Opponent) Touchdown",
            "Fumble Return Touchdown",
        )
    ) & nw.col("play_family").is_in(("rush", "dropback"))
    administrative = text.str.contains(
        r"\b(?:no play|nullified|kneel|kneels|kneeling|knee|spike|spikes|spiked)\b"
    )
    ambiguous = text.str.contains(r"\bpenalty\b") | (
        (fumble | text.str.contains(r"\b(?:fumble|fumbled|fumbles)\b")) & ~lost_fumble
    )
    regulation = nw.col("period").is_in((1, 2, 3, 4))
    known_action = nw.col("play_family").is_in(("rush", "dropback"))
    evaluated = (
        known_action & ~administrative & ~ambiguous & regulation & nw.col("completed")
    )
    base = base.require(
        ~evaluated
        | (
            nw.col("down").is_in((1, 2, 3, 4))
            & (nw.col("distance") > 0)
            & (nw.col("yards_to_goal") > 0)
            & (nw.col("yards_to_goal") < 100)
            & (nw.col("distance") <= nw.col("yards_to_goal"))
            & (
                nw.col("play_type").is_in(_INTERCEPTION)
                | lost_fumble
                | (
                    (nw.col("yards_gained") <= nw.col("yards_to_goal"))
                    & (nw.col("yards_gained") >= nw.col("yards_to_goal") - 100)
                )
            )
        ),
        message="Evaluated scrimmage play has contradictory down or field position",
    ).require(
        ~evaluated
        | nw.col("clock_seconds").is_null()
        | ((nw.col("__seconds") < 60) & (nw.col("clock_seconds") <= 900)),
        message="Scrimmage play has an invalid regulation clock",
    )
    reason = (
        nw.when(~nw.col("completed"))
        .then(nw.lit("incomplete_game"))
        .when(~regulation)
        .then(nw.lit("outside_regulation"))
        .when(administrative)
        .then(nw.lit("administrative_action"))
        .when(nw.col("play_family") == "other")
        .then(nw.lit("outside_scrimmage"))
        .when(ambiguous | (nw.col("play_family") == "unknown"))
        .then(nw.lit("ambiguous_action_or_enforcement"))
        .otherwise(nw.lit("evaluated"))
    )
    success = (
        nw.when(nw.col("play_type").is_in(_INTERCEPTION) | lost_fumble)
        .then(nw.lit(False))
        .when(nw.col("down") == 1)
        .then(2 * nw.col("yards_gained") >= nw.col("distance"))
        .when(nw.col("down") == 2)
        .then(10 * nw.col("yards_gained") >= 7 * nw.col("distance"))
        .otherwise(nw.col("yards_gained") >= nw.col("distance"))
    )
    base = (
        base.with_columns(reason.alias("success_reason"))
        .with_columns(
            nw.when(nw.col("success_reason") == "evaluated")
            .then(nw.lit("evaluated"))
            .when(nw.col("success_reason") == "ambiguous_action_or_enforcement")
            .then(nw.lit("unknown"))
            .otherwise(nw.lit("excluded"))
            .alias("success_status"),
            nw.when(nw.col("success_reason") == "evaluated")
            .then(success)
            .otherwise(nw.lit(None))
            .alias("successful"),
            nw.when(nw.col("play_type").is_in(_FUMBLE))
            .then(nw.lit("fumble_event"))
            .when(nw.col("play_family") == "dropback")
            .then(nw.lit("outside_rushing"))
            .otherwise(nw.col("success_reason"))
            .alias("rush_reason"),
        )
        .with_columns(
            nw.when(nw.col("rush_reason") == "evaluated")
            .then(nw.lit("evaluated"))
            .when(nw.col("rush_reason") == "ambiguous_action_or_enforcement")
            .then(nw.lit("unknown"))
            .otherwise(nw.lit("excluded"))
            .alias("rush_status"),
        )
    )
    yards = nw.col("yards_gained").cast(nw.Float64)
    line = (
        nw.when(yards < 0)
        .then(1.2 * yards)
        .when(yards <= 4)
        .then(yards)
        .when(yards <= 10)
        .then(4 + 0.5 * (yards - 4))
        .otherwise(nw.lit(7.0))
    )
    base = base.with_columns(
        nw.when(nw.col("rush_status") == "evaluated")
        .then(line)
        .otherwise(nw.lit(None))
        .alias("line_yards"),
        nw.when(nw.col("home_away") == "home")
        .then(nw.col("offense_score"))
        .otherwise(nw.col("defense_score"))
        .alias("__home_score"),
        nw.when(nw.col("home_away") == "away")
        .then(nw.col("offense_score"))
        .otherwise(nw.col("defense_score"))
        .alias("__away_score"),
    )
    base = _preplay_scores(base)
    return base.select(*ScrimmagePlay.model_fields).sort("game_id", "source_ordinal")


def _preplay_scores(rows: Table) -> Table:
    """Establish source score timing from globally adjacent scoring evidence."""
    sequenced = rows.sort(
        "game_id", "drive_number", "play_number", "source_ordinal"
    ).with_group_index("__ordinal", keys=("game_id",))
    previous = sequenced.select(
        "game_id",
        (nw.col("__ordinal") + 1).alias("__ordinal"),
        nw.col("__home_score").alias("__previous_home"),
        nw.col("__away_score").alias("__previous_away"),
        nw.col("scoring").alias("__previous_scoring"),
        nw.col("drive_number").alias("__previous_drive"),
        nw.col("play_number").alias("__previous_play"),
        nw.col("period").alias("__previous_period"),
        nw.col("clock_seconds").alias("__previous_clock"),
    )
    joined = sequenced.join(
        previous, on=("game_id", "__ordinal"), cardinality="one_to_one"
    )
    changed = (~nw.col("__previous_home").is_null()) & (
        (nw.col("__home_score") != nw.col("__previous_home"))
        | (nw.col("__away_score") != nw.col("__previous_away"))
    )
    joined = joined.with_columns(
        changed.cast(nw.Int64).alias("__changed"),
        (changed & ~nw.col("scoring")).cast(nw.Int64).alias("__after_failure"),
        (changed & ~nw.col("__previous_scoring").fill_null(False).cast(nw.Boolean))
        .cast(nw.Int64)
        .alias("__before_failure"),
        (nw.col("drive_number").is_null() | nw.col("play_number").is_null())
        .cast(nw.Int64)
        .alias("__sequence_missing"),
        (nw.col("__home_score") + nw.col("__away_score")).alias("__score_total"),
        (
            (nw.col("__home_score") < nw.col("__previous_home"))
            | (nw.col("__away_score") < nw.col("__previous_away"))
        )
        .fill_null(False)
        .cast(nw.Int64)
        .alias("__score_decline"),
        (
            (nw.col("__ordinal") > 0)
            & ~(
                (
                    (nw.col("drive_number") == nw.col("__previous_drive"))
                    & (nw.col("play_number") == nw.col("__previous_play") + 1)
                )
                | (
                    (nw.col("drive_number") == nw.col("__previous_drive") + 1)
                    & (
                        nw.col("play_number").is_in((0, 1))
                        | (nw.col("play_number") == nw.col("__previous_play") + 1)
                    )
                )
            )
        )
        .fill_null(False)
        .cast(nw.Int64)
        .alias("__sequence_gap"),
        (
            (nw.col("period") < nw.col("__previous_period"))
            | (
                (nw.col("period") == nw.col("__previous_period"))
                & (nw.col("clock_seconds") > nw.col("__previous_clock"))
            )
        )
        .fill_null(False)
        .cast(nw.Int64)
        .alias("__clock_reversal"),
    )
    evidence = joined.aggregate(
        keys=("game_id",),
        expressions=(
            nw.col("__changed").sum().alias("__changes"),
            nw.col("__after_failure").sum().alias("__after_failures"),
            nw.col("__before_failure").sum().alias("__before_failures"),
            nw.col("__sequence_missing").sum().alias("__missing_sequence"),
            nw.col("__score_total").max().alias("__maximum_score"),
            nw.col("__score_decline").sum().alias("__score_declines"),
            nw.col("__sequence_gap").sum().alias("__sequence_gaps"),
            nw.col("__clock_reversal").sum().alias("__clock_reversals"),
        ),
    )
    joined = joined.join(evidence, on=("game_id",), cardinality="many_to_one")
    after = (
        (nw.col("__changes") > 0)
        & (nw.col("__after_failures") == 0)
        & (nw.col("__before_failures") > 0)
    )
    before = (
        (nw.col("__changes") > 0)
        & (nw.col("__before_failures") == 0)
        & (nw.col("__after_failures") > 0)
    )
    zero = nw.col("__maximum_score") == 0
    ordered = (
        (nw.col("__missing_sequence") == 0)
        & (nw.col("__sequence_gaps") == 0)
        & (nw.col("__clock_reversals") == 0)
        & (nw.col("__score_declines") == 0)
    )
    first_anchor = (
        (nw.col("period") == 1)
        & (nw.col("clock_seconds") == 900)
        & nw.col("drive_number").is_in((0, 1))
        & nw.col("play_number").is_in((0, 1))
    )
    known = (
        ordered
        & (after | before | zero)
        & (~after | (nw.col("__ordinal") > 0) | first_anchor)
    )
    home = (
        nw.when(after)
        .then(nw.col("__previous_home").fill_null(0))
        .otherwise(nw.col("__home_score"))
    )
    away = (
        nw.when(after)
        .then(nw.col("__previous_away").fill_null(0))
        .otherwise(nw.col("__away_score"))
    )
    margin = (
        nw.when(nw.col("home_away") == "home").then(home - away).otherwise(away - home)
    )
    return joined.with_columns(
        nw.when(known)
        .then(margin)
        .otherwise(nw.lit(None))
        .alias("preplay_score_margin"),
        nw.when(known)
        .then(nw.lit("known"))
        .otherwise(nw.lit("unknown"))
        .alias("score_context"),
    )


@step(id="cfbd.scrimmage_plays.combine", revision=1, output=ScrimmagePlay)
def combine_partitions(partitions: tuple[Table, ...]) -> Table:
    """Concatenate finite play partitions with global duplicate protection.

    :param partitions: Tables from explicit source selectors.
    :return: Combined native plays retaining partition source ordinals.
    """
    return (
        concat_tables(partitions)
        .require_unique(
            ("game_id", "play_id"),
            message="Play source partitions overlap or repeat keys",
        )
        .sort("week", "game_id", "source_ordinal")
    )


@dataset(
    id="cfbd.scrimmage_plays",
    revision=1,
    row=ScrimmagePlay,
    grain="one source play with calculated metric eligibility",
    keys=("game_id", "play_id"),
    order_by=("week", "game_id", "source_ordinal"),
    partition_by=("game_id",),
    event_time="start_date",
)
def scrimmage_plays(
    *,
    year: int,
    weeks: tuple[int, ...],
    team: str | None = None,
    season_type: SeasonType = SeasonType.regular,
    classification: Classification | None = None,
) -> RecipeRef[Table]:
    """Build calculated play features from finite unfiltered source partitions.

    :param year: Season year.
    :param weeks: Unique explicit source weeks; no runtime source fan-out occurs.
    :param team: Optional participating-team filter for unadjusted summaries.
    :param season_type: Season phase defining each source partition.
    :param classification: Optional source classification selector.
    :return: A validated dataset reference with explicit unknown/excluded evidence.
    :raises cfb_data.analytics.CFBDRecipeCompilationError: If source selectors are invalid.
    """
    validate_partitions(year, weeks)
    games = team_games(
        year=year, team=team, season_type=season_type, classification=classification
    )
    partitions = tuple(
        classify_partition.as_(f"classify-week-{week}")(
            plays_source.as_(f"source-week-{week}")(
                year=year,
                week=week,
                team=team,
                season_type=season_type,
                classification=classification,
            ),
            games,
            week=week,
        )
        for week in sorted(weeks)
    )
    return combine_partitions(partitions)


__all__ = ["ScrimmagePlay", "scrimmage_plays"]
