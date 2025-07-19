"""
Request models for College Football Data API drives endpoints.

This module provides Pydantic models for validating request parameters
to the drives API endpoints, ensuring proper parameter validation and
type safety before making API calls.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cfb_data.base.validation import (
    Classification,
    SeasonType,
)


class DrivesRequest(BaseModel):
    """
    Request parameters for /drives endpoint.

    Validates parameters for retrieving historical drive data from college
    football games. Year parameter is always required per API specification.

    :param year: Required year filter (1869-current year)
    :type year: int
    :param season_type: Optional season type filter
    :type season_type: Optional[SeasonType]
    :param week: Optional week filter (positive integer)
    :type week: Optional[int]
    :param team: Optional team filter (either offense or defense)
    :type team: Optional[str]
    :param offense: Optional offensive team filter
    :type offense: Optional[str]
    :param defense: Optional defensive team filter
    :type defense: Optional[str]
    :param conference: Optional conference filter
    :type conference: Optional[str]
    :param offense_conference: Optional offensive team conference filter
    :type offense_conference: Optional[str]
    :param defense_conference: Optional defensive team conference filter
    :type defense_conference: Optional[str]
    :param classification: Optional division classification filter
    :type classification: Optional[Classification]
    """

    model_config = ConfigDict(populate_by_name=True)

    # Required parameter
    year: int = Field(ge=1869, le=2025, description="Required year filter")

    # Optional season and week filters
    season_type: Optional[SeasonType] = Field(
        default=None, alias="seasonType", description="Optional season type filter"
    )
    week: Optional[int] = Field(
        default=None, gt=0, le=20, description="Optional week filter"
    )

    # Team filters
    team: Optional[str] = Field(
        default=None, description="Optional team filter (either offense or defense)"
    )
    offense: Optional[str] = Field(
        default=None, description="Optional offensive team filter"
    )
    defense: Optional[str] = Field(
        default=None, description="Optional defensive team filter"
    )

    # Conference filters
    conference: Optional[str] = Field(
        default=None, description="Optional conference filter"
    )
    offense_conference: Optional[str] = Field(
        default=None,
        alias="offenseConference",
        description="Optional offensive team conference filter",
    )
    defense_conference: Optional[str] = Field(
        default=None,
        alias="defenseConference",
        description="Optional defensive team conference filter",
    )

    # Classification filter
    classification: Optional[Classification] = Field(
        default=None, description="Optional division classification filter"
    )

    @model_validator(mode="after")
    def validate_drives_parameters(self) -> "DrivesRequest":  # noqa: DAR402
        """
        Validate drives request parameters.

        Additional validation can be added here for parameter combinations.
        Year validation is handled by Pydantic Field constraints.

        :return: Validated drives request instance
        :rtype: DrivesRequest # noqa: DAR402
        """
        # Week validation is handled by Pydantic Field constraints (gt=0, le=20)
        # Additional complex validation logic can be added here if needed

        return self

    def to_api_params(self) -> dict[str, str]:
        """
        Convert request model to API parameters dictionary.

        Excludes None values and uses field aliases for API parameter names.

        :return: Dictionary of API parameters
        :rtype: dict[str, str]
        """
        return self.model_dump(exclude_none=True, by_alias=True)
