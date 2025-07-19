# Drives API Implementation Plan

## Overview
This document provides a complete implementation plan to bring the drives API in line with the robust game API architecture. The drives API currently lacks critical request validation infrastructure and relies on hard-coded parameter checking instead of the established model-based validation patterns. This plan will create the missing validation components and integrate them with the existing shared validation utilities.

## Current State Analysis
- **Missing Component**: [`cfb_data/cfb_data/drives/models/pydantic/requests.py`](cfb_data/cfb_data/drives/models/pydantic/requests.py:1) - No request models exist
- **Hard-coded Validation**: [`cfb_data/cfb_data/drives/api/drives_api.py`](cfb_data/cfb_data/drives/api/drives_api.py:28) - Lines 28-29 contain manual year validation
- **No Enum Integration**: No use of [`SeasonType`](cfb_data/cfb_data/base/validation/request_validators.py:14) and [`Classification`](cfb_data/cfb_data/base/validation/request_validators.py:51) enums
- **Missing Tests**: No request model validation tests

## Phase 1: Utilize Existing Shared Validation Utilities

The drives API will integrate with the existing shared validation infrastructure from [`cfb_data/cfb_data/base/validation/request_validators.py`](cfb_data/cfb_data/base/validation/request_validators.py:1):

### Available Shared Components:
```python
from cfb_data.base.validation import (
    SeasonType,           # Enum with values: regular, postseason, both, allstar, spring_regular, spring_postseason
    Classification,       # Enum with values: fbs, fcs, ii, iii
    validate_year_or_id_required,  # Year validation utility
    RequestValidationMixin         # Common validation patterns
)
```

### Drives-Specific Validation Function:
Add to [`cfb_data/cfb_data/base/validation/request_validators.py`](cfb_data/cfb_data/base/validation/request_validators.py:185):

```python
def validate_drives_year_required(year: Optional[int]) -> None:
    """
    Validate that year is provided for drives API.

    Unlike games API which has conditional year requirements,
    drives API always requires year parameter per API specification.

    :param year: Year parameter value
    :type year: Optional[int]
    :raises ValueError: If year is not provided
    """
    if year is None:
        raise ValueError("year parameter is required for drives endpoint")

    # Validate year range using datetime
    from datetime import datetime
    current_year = datetime.now().year
    if year < 1869 or year > current_year:
        raise ValueError(f"year must be between 1869 and {current_year}")
```

## Phase 2: Create DrivesRequest Model

### File: `cfb_data/cfb_data/drives/models/pydantic/requests.py`

```python
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
    validate_drives_year_required,
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
    year: int = Field(ge=1869, le=2030, description="Required year filter")

    # Optional season and week filters
    season_type: Optional[SeasonType] = Field(
        default=None, alias="seasonType", description="Optional season type filter"
    )
    week: Optional[int] = Field(
        default=None, ge=1, le=20, description="Optional week filter"
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
    def validate_drives_parameters(self) -> "DrivesRequest":
        """
        Validate drives request parameters.

        Ensures year is provided and within valid range. Additional
        validation can be added here for parameter combinations.

        :return: Validated drives request instance
        :rtype: DrivesRequest
        :raises ValueError: If validation fails
        """
        # Validate year requirement and range
        validate_drives_year_required(self.year)

        # Validate week if provided
        if self.week is not None and self.week <= 0:
            raise ValueError("week must be a positive integer")

        return self

    def to_api_params(self) -> dict[str, str]:
        """
        Convert request model to API parameters dictionary.

        Excludes None values and uses field aliases for API parameter names.

        :return: Dictionary of API parameters
        :rtype: dict[str, str]
        """
        return self.model_dump(exclude_none=True, by_alias=True)
```

### Update: `cfb_data/cfb_data/drives/models/pydantic/__init__.py`

```python
"""Pydantic models for drives API endpoints."""

from .requests import DrivesRequest
from .responses import Drive

__all__ = [
    "Drive",
    "DrivesRequest",
]
```

## Phase 3: Update API Layer

### Updated `cfb_data/cfb_data/drives/api/drives_api.py`

Remove hard-coded validation and integrate request model validation:

```python
"""Drive endpoint handlers for the CFBD API."""

from __future__ import annotations

from typing import Any, Dict, List

from cfb_data.base.api.base_api import CFBDAPIBase, route
from cfb_data.drives.models.pandera.responses import DriveSchema
from cfb_data.drives.models.pydantic.requests import DrivesRequest
from cfb_data.drives.models.pydantic.responses import Drive


class CFBDDrivesAPI(CFBDAPIBase):
    """Drives endpoint for the College Football Data API."""

    @route("/drives", response_model=Drive, dataframe_schema=DriveSchema)
    async def _get_drives(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retrieve historical drive data.

        :param params: Query parameters including year (required) and optional
            filters such as week, team, offense, defense, conference, and
            classification.
        :type params: Dict[str, Any]
        :return: List of drive dictionaries.
        :rtype: List[Dict[str, Any]]
        :raises ValidationError: If request parameters are invalid.
        """
        # Validate using request model instead of hard-coded check
        request = DrivesRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/drives", validated_params)
```

**Key Changes:**
1. **Import DrivesRequest**: Added import for the new request model
2. **Remove hard-coded validation**: Deleted lines 28-29 with manual year check
3. **Model validation**: Use `DrivesRequest.model_validate(params)` for validation
4. **Parameter conversion**: Use `request.model_dump(exclude_none=True, by_alias=True)` for API parameters
5. **Updated docstring**: Changed exception type from ValueError to ValidationError

## Phase 4: Comprehensive Test Suite

### File: `cfb_data/cfb_data/tests/drives/models/pydantic/test_requests.py`

```python
"""Test drives request model validation."""

import pytest
from pydantic import ValidationError

from cfb_data.base.validation import Classification, SeasonType
from cfb_data.drives.models.pydantic.requests import DrivesRequest


class TestDrivesRequestValidation:
    """Test DrivesRequest validation logic."""

    def test_valid_request_year_only(self):
        """Test valid request with only required year parameter."""
        request = DrivesRequest(year=2024)
        assert request.year == 2024
        assert request.season_type is None
        assert request.week is None

    def test_valid_request_with_optional_parameters(self):
        """Test valid request with multiple optional parameters."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            week=5,
            team="Alabama",
            conference="SEC",
            classification=Classification.fbs,
        )
        assert request.year == 2023
        assert request.season_type == SeasonType.regular
        assert request.week == 5
        assert request.team == "Alabama"
        assert request.conference == "SEC"
        assert request.classification == Classification.fbs

    def test_missing_year_parameter(self):
        """Test that missing year parameter raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(week=1)

        errors = exc_info.value.errors()
        assert any("year" in str(error) for error in errors)

    def test_year_range_validation(self):
        """Test year range validation."""
        # Valid year
        request = DrivesRequest(year=2023)
        assert request.year == 2023

        # Year too low
        with pytest.raises(ValidationError):
            DrivesRequest(year=1800)

        # Year too high
        with pytest.raises(ValidationError):
            DrivesRequest(year=2050)

    def test_week_validation(self):
        """Test week parameter validation."""
        # Valid week
        request = DrivesRequest(year=2023, week=15)
        assert request.week == 15

        # Invalid week (zero)
        with pytest.raises(ValidationError):
            DrivesRequest(year=2023, week=0)

        # Invalid week (negative)
        with pytest.raises(ValidationError):
            DrivesRequest(year=2023, week=-1)

        # Invalid week (too high)
        with pytest.raises(ValidationError):
            DrivesRequest(year=2023, week=25)

    def test_season_type_enum_validation(self):
        """Test season type enum validation."""
        # Valid enum values
        for season_type in SeasonType:
            request = DrivesRequest(year=2023, season_type=season_type)
            assert request.season_type == season_type

        # Invalid enum value
        with pytest.raises(ValidationError):
            DrivesRequest(year=2023, season_type="invalid_season")

    def test_classification_enum_validation(self):
        """Test classification enum validation."""
        # Valid enum values
        for classification in Classification:
            request = DrivesRequest(year=2023, classification=classification)
            assert request.classification == classification

        # Invalid enum value
        with pytest.raises(ValidationError):
            DrivesRequest(year=2023, classification="invalid_classification")

    def test_team_and_conference_filters(self):
        """Test team and conference filter combinations."""
        # Test offense/defense team filters
        request = DrivesRequest(
            year=2023, offense="Alabama", defense="Georgia"
        )
        assert request.offense == "Alabama"
        assert request.defense == "Georgia"

        # Test offense/defense conference filters
        request = DrivesRequest(
            year=2023,
            offense_conference="SEC",
            defense_conference="Big Ten",
        )
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "Big Ten"

    def test_field_aliases(self):
        """Test that field aliases work correctly for API parameters."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.postseason,
            offense_conference="SEC",
            defense_conference="Big Ten",
        )

        # Test model dump with aliases
        params = request.model_dump(exclude_none=True, by_alias=True)

        # Should use camelCase aliases for API
        assert "seasonType" in params
        assert "season_type" not in params
        assert "offenseConference" in params
        assert "offense_conference" not in params
        assert "defenseConference" in params
        assert "defense_conference" not in params
        assert params["seasonType"] == "postseason"
        assert params["year"] == 2023

    def test_to_api_params_method(self):
        """Test the to_api_params convenience method."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            week=1,
            team="Alabama",
        )

        params = request.to_api_params()

        assert params["year"] == 2023
        assert params["seasonType"] == "regular"
        assert params["week"] == 1
        assert params["team"] == "Alabama"
        # Should exclude None values
        assert "offense" not in params
        assert "conference" not in params


class TestDrivesRequestEdgeCases:
    """Test edge cases and boundary conditions for DrivesRequest."""

    def test_empty_string_parameters(self):
        """Test handling of empty string parameters."""
        # Empty strings should be accepted (API will handle them)
        request = DrivesRequest(
            year=2023,
            team="",
            conference="",
        )
        assert request.team == ""
        assert request.conference == ""

    def test_boundary_years(self):
        """Test boundary year values."""
        # Minimum valid year
        request = DrivesRequest(year=1869)
        assert request.year == 1869

        # Maximum valid year (current implementation allows up to 2030)
        request = DrivesRequest(year=2030)
        assert request.year == 2030

    def test_boundary_weeks(self):
        """Test boundary week values."""
        # Minimum valid week
        request = DrivesRequest(year=2023, week=1)
        assert request.week == 1

        # Maximum valid week
        request = DrivesRequest(year=2023, week=20)
        assert request.week == 20

    def test_all_parameters_combination(self):
        """Test request with all parameters provided."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            week=1,
            team="Alabama",
            offense="Alabama",
            defense="Georgia",
            conference="SEC",
            offense_conference="SEC",
            defense_conference="SEC",
            classification=Classification.fbs,
        )

        # Verify all parameters are set
        assert request.year == 2023
        assert request.season_type == SeasonType.regular
        assert request.week == 1
        assert request.team == "Alabama"
        assert request.offense == "Alabama"
        assert request.defense == "Georgia"
        assert request.conference == "SEC"
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "SEC"
        assert request.classification == Classification.fbs

        # Verify API parameter generation
        params = request.to_api_params()
        assert len(params) == 10  # All parameters should be included
```

### Update Base Validation Tests

Add to [`cfb_data/cfb_data/tests/base/validation/test_request_validators.py`](cfb_data/cfb_data/tests/base/validation/test_request_validators.py:1):

```python
class TestDrivesValidationFunctions:
    """Test drives-specific validation functions."""

    def test_validate_drives_year_required_success(self):
        """Test successful year validation for drives."""
        # Should not raise for valid years
        validate_drives_year_required(2023)
        validate_drives_year_required(1869)
        validate_drives_year_required(2030)

    def test_validate_drives_year_required_none(self):
        """Test year validation fails when None."""
        with pytest.raises(ValueError) as exc_info:
            validate_drives_year_required(None)
        assert "year parameter is required for drives endpoint" in str(exc_info.value)

    def test_validate_drives_year_required_range(self):
        """Test year validation fails for out-of-range years."""
        # Year too low
        with pytest.raises(ValueError) as exc_info:
            validate_drives_year_required(1800)
        assert "year must be between 1869 and" in str(exc_info.value)

        # Year too high
        with pytest.raises(ValueError) as exc_info:
            validate_drives_year_required(2050)
        assert "year must be between 1869 and" in str(exc_info.value)
```

## Phase 5: Implementation Steps

### Step 1: Update Base Validation Infrastructure
1. **Add drives-specific validation function** to [`cfb_data/cfb_data/base/validation/request_validators.py`](cfb_data/cfb_data/base/validation/request_validators.py:185)
2. **Export new function** in [`cfb_data/cfb_data/base/validation/__init__.py`](cfb_data/cfb_data/base/validation/__init__.py:48)
3. **Test validation function** in [`cfb_data/cfb_data/tests/base/validation/test_request_validators.py`](cfb_data/cfb_data/tests/base/validation/test_request_validators.py:1)

### Step 2: Create Drives Request Models
1. **Create requests.py** with `DrivesRequest` model at [`cfb_data/cfb_data/drives/models/pydantic/requests.py`](cfb_data/cfb_data/drives/models/pydantic/requests.py:1)
2. **Update __init__.py** to export `DrivesRequest` in [`cfb_data/cfb_data/drives/models/pydantic/__init__.py`](cfb_data/cfb_data/drives/models/pydantic/__init__.py:1)
3. **Test request model** individually before API integration

### Step 3: Update Drives API Layer
1. **Import DrivesRequest** in [`cfb_data/cfb_data/drives/api/drives_api.py`](cfb_data/cfb_data/drives/api/drives_api.py:1)
2. **Replace hard-coded validation** on lines 28-29 with model validation
3. **Use model.model_dump()** for API parameter generation
4. **Update docstrings** to reflect ValidationError instead of ValueError

### Step 4: Create Comprehensive Test Suite
1. **Create test file** at [`cfb_data/cfb_data/tests/drives/models/pydantic/test_requests.py`](cfb_data/cfb_data/tests/drives/models/pydantic/test_requests.py:1)
2. **Test all validation scenarios** (positive and negative cases)
3. **Test field aliases** and API parameter generation
4. **Test edge cases** and boundary conditions

### Step 5: Integration Testing
1. **Test API integration** with request model validation
2. **Verify error handling** produces clear ValidationError messages
3. **Test backwards compatibility** with existing API usage
4. **Performance testing** for validation overhead

## Expected Outcomes

### Immediate Benefits:
- ✅ **Consistent architecture** - Drives API follows same pattern as games API
- ✅ **Robust validation** - Request validation happens at model level with clear error messages
- ✅ **Enum safety** - Proper validation for season types and classifications
- ✅ **Type safety** - Full type hints and Pydantic validation for all parameters
- ✅ **Field aliases** - Automatic conversion between snake_case and camelCase

### Long-term Benefits:
- ✅ **Maintainable validation** - Centralized validation logic in request models
- ✅ **Better developer experience** - Clear validation errors before API calls
- ✅ **Reduced API failures** - Invalid parameters caught early
- ✅ **Testable validation** - Comprehensive test coverage for all parameter combinations
- ✅ **Documentation** - Self-documenting request models with field descriptions

## Risk Mitigation

### Breaking Changes:
- **ValidationError vs ValueError**: API now raises `ValidationError` instead of `ValueError` for invalid parameters
- **Stricter validation**: Previously accepted invalid enum values will now be rejected
- **Parameter type checking**: Parameters now have strict type validation

### Mitigation Strategies:
- **Clear error messages**: ValidationError provides detailed information about what's invalid
- **Backwards compatibility**: Existing valid API calls will continue to work unchanged
- **Comprehensive testing**: All scenarios tested before deployment
- **Documentation updates**: Clear migration guide for any breaking changes

## Success Criteria

1. **Complete request model** - `DrivesRequest` model handles all API parameters with proper validation
2. **No hard-coded validation** - API layer uses model validation instead of manual checks
3. **Shared utilities integration** - Uses existing `SeasonType` and `Classification` enums
4. **100% test coverage** - All validation logic thoroughly tested
5. **API parameter compatibility** - Generates correct camelCase parameters for API calls
6. **Clear error messages** - ValidationError provides actionable feedback for invalid requests
7. **Performance** - Validation overhead is minimal and acceptable

## Files Modified/Created

### New Files:
- [`cfb_data/cfb_data/drives/models/pydantic/requests.py`](cfb_data/cfb_data/drives/models/pydantic/requests.py:1) - Primary drives request models
- [`cfb_data/cfb_data/tests/drives/models/pydantic/test_requests.py`](cfb_data/cfb_data/tests/drives/models/pydantic/test_requests.py:1) - Request model validation tests

### Modified Files:
- [`cfb_data/cfb_data/drives/api/drives_api.py`](cfb_data/cfb_data/drives/api/drives_api.py:28) - Remove hard-coded validation, add model integration
- [`cfb_data/cfb_data/drives/models/pydantic/__init__.py`](cfb_data/cfb_data/drives/models/pydantic/__init__.py:1) - Export `DrivesRequest`
- [`cfb_data/cfb_data/base/validation/request_validators.py`](cfb_data/cfb_data/base/validation/request_validators.py:185) - Add `validate_drives_year_required`
- [`cfb_data/cfb_data/base/validation/__init__.py`](cfb_data/cfb_data/base/validation/__init__.py:48) - Export drives validation function
- [`cfb_data/cfb_data/tests/base/validation/test_request_validators.py`](cfb_data/cfb_data/tests/base/validation/test_request_validators.py:1) - Add drives validation tests

This implementation plan provides a comprehensive blueprint for bringing the drives API validation infrastructure to the same level of robustness and consistency as the games API, ensuring proper parameter validation, type safety, and maintainable code architecture.
