"""Base validation module for CFB Data API.

This module provides validation utilities, mixins, and APIs for validating
College Football Data API requests. It includes common validation patterns,
enums for standardized values, and reusable validation functions that ensure
API requests meet the required constraints and business rules.

The module exports:

- **Enums**: Classification and SeasonType for standardized values
- **Mixins**: RequestValidationMixin for adding validation to request models
- **Functions**: Validation utilities for common patterns like year/ID requirements
- **API**: CFBDValidationAPI for validation-enabled API interactions

Example:
    Basic usage of validation components::

        from cfb_data.base.validation import (
            SeasonType,
            validate_year_or_id_required,
            CFBDValidationAPI
        )

        # Use validation function
        validate_year_or_id_required(year=2023, game_id=None)

        # Use validation API
        api = CFBDValidationAPI()
"""

from .request_validators import (
    Classification,
    RequestValidationMixin,
    SeasonType,
    validate_at_least_one_of,
    validate_team_game_stats_logic,
    validate_year_or_id_required,
)
from .validation_api import CFBDValidationAPI

__all__ = [
    "CFBDValidationAPI",
    "Classification",
    "RequestValidationMixin",
    "SeasonType",
    "validate_at_least_one_of",
    "validate_team_game_stats_logic",
    "validate_year_or_id_required",
]
