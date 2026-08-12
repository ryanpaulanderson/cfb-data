"""Provide relational validation shared by endpoint request models."""

from collections.abc import Mapping, Sequence


def _validate_year_or_game_id(
    year: int | None,
    game_id: int | None,
) -> None:
    """Require either a year or game identifier."""
    if year is None and game_id is None:
        raise ValueError("year is required when game_id is not specified")


def _validate_at_least_one_of(
    values: Mapping[str, object],
    field_names: Sequence[str],
    context_message: str = "At least one of the following fields is required",
) -> None:
    """Require a non-null value for at least one named field."""
    if not any(values.get(field) is not None for field in field_names):
        field_list = ", ".join(field_names)
        raise ValueError(f"{context_message}: {field_list}")


def _validate_game_stats_selectors(
    year: int | None,
    week: int | None,
    team: str | None,
    conference: str | None,
    game_id: int | None,
) -> None:
    """Validate game-ID or grouped selectors for game-stat endpoints."""
    if game_id is not None:
        return
    _validate_year_or_game_id(year, game_id)
    if week is None and team is None and conference is None:
        raise ValueError(
            "At least one of week, team, or conference is required "
            "when game_id is not specified"
        )
