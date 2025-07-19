"""
Shared validation utilities for College Football Data API request models.

This module provides reusable validators and enums for consistent
request validation across all endpoints.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import model_validator


class SeasonType(str, Enum):
    """
    Season type enumeration for API requests.

    Values match the API specification exactly as observed from
    https://apinext.collegefootballdata.com/ Swagger documentation.

    :param regular: Regular season games
    :type regular: str
    :param postseason: Postseason games (bowls, playoffs)
    :type postseason: str
    :param both: Both regular and postseason games
    :type both: str
    :param allstar: All-star games
    :type allstar: str
    :param spring_regular: Spring regular season games
    :type spring_regular: str
    :param spring_postseason: Spring postseason games
    :type spring_postseason: str
    """

    regular = "regular"
    postseason = "postseason"
    both = "both"
    allstar = "allstar"
    spring_regular = "spring_regular"
    spring_postseason = "spring_postseason"

    def __str__(self) -> str:
        """Return the enum value as string.

        :return: The string value of the enum
        :rtype: str
        """
        return self.value


class Classification(str, Enum):
    """
    Division classification enumeration for API requests.

    Values match the API specification exactly as observed from
    https://apinext.collegefootballdata.com/ Swagger documentation.

    :param fbs: Football Bowl Subdivision (Division I FBS)
    :type fbs: str
    :param fcs: Football Championship Subdivision (Division I FCS)
    :type fcs: str
    :param ii: Division II
    :type ii: str
    :param iii: Division III
    :type iii: str
    """

    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    iii = "iii"

    def __str__(self) -> str:
        """Return the enum value as string.

        :return: The string value of the enum
        :rtype: str
        """
        return self.value


def validate_year_or_id_required(
    year: Optional[int], id_field: Optional[int], id_field_name: str = "id"
) -> None:
    """
    Validate that either year or id field is provided.

    Used for endpoints where year is required except when a specific
    id is provided to retrieve a single record.

    :param year: Year parameter value
    :type year: Optional[int]
    :param id_field: ID field value (e.g., id, game_id)
    :type id_field: Optional[int]
    :param id_field_name: Name of the ID field for error messages
    :type id_field_name: str
    :raises ValueError: If neither year nor id_field is provided
    """
    if year is None and id_field is None:
        raise ValueError(f"year is required when {id_field_name} is not specified")


def validate_at_least_one_of(
    values: Dict[str, Any],
    field_names: List[str],
    context_message: str = "At least one of the following fields is required",
) -> None:
    """
    Validate that at least one of the specified fields has a value.

    :param values: Dictionary of field values
    :type values: Dict[str, Any]
    :param field_names: List of field names to check
    :type field_names: List[str]
    :param context_message: Context message for error
    :type context_message: str
    :raises ValueError: If none of the specified fields have values
    """
    if not any(values.get(field) is not None for field in field_names):
        field_list = ", ".join(field_names)
        raise ValueError(f"{context_message}: {field_list}")


def validate_team_game_stats_logic(
    year: Optional[int],
    week: Optional[int],
    team: Optional[str],
    conference: Optional[str],
    game_id: Optional[int],
) -> None:
    """
    Validate the complex conditional logic for /games/teams endpoint.

    API Rules from https://apinext.collegefootballdata.com/:
    - year is required (along with one of week, team, or conference), unless id is specified
    - At least one of week, team, or conference must be specified when year is provided

    :param year: Year parameter
    :type year: Optional[int]
    :param week: Week parameter
    :type week: Optional[int]
    :param team: Team parameter
    :type team: Optional[str]
    :param conference: Conference parameter
    :type conference: Optional[str]
    :param game_id: Game ID parameter
    :type game_id: Optional[int]
    :raises ValueError: If validation rules are violated
    """
    # If game_id is specified, no other validation needed
    if game_id is not None:
        return

    # year is required when game_id is not specified
    if year is None:
        raise ValueError("year is required when game_id is not specified")

    # At least one of week, team, or conference must be specified
    if week is None and team is None and conference is None:
        raise ValueError(
            "At least one of week, team, or conference is required "
            "when game_id is not specified"
        )


class RequestValidationMixin:
    """
    Mixin class providing common validation patterns for request models.

    This mixin can be inherited by request models that need standard
    validation patterns like year/id requirements.
    """

    @model_validator(mode="after")
    def validate_request_constraints(self) -> "RequestValidationMixin":
        """
        Apply request-specific validation constraints.

        This method should be overridden by subclasses to implement
        their specific validation logic.

        :return: Validated model instance
        :rtype: RequestValidationMixin
        """
        return self
