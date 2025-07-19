# Request Validation Implementation Plan

## Overview
This document provides a complete implementation plan to fix all request validation issues identified in the College Football Data API models. The plan includes code specifications, implementation steps, and validation logic.

## Phase 1: Create Shared Validation Utilities

### File: `cfb_data/cfb_data/base/validation/request_validators.py`

```python
"""
Shared validation utilities for College Football Data API request models.

This module provides reusable validators and enums for consistent
request validation across all endpoints.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import model_validator


class SeasonType(str, Enum):
    """Season type enumeration for API requests."""
    regular = "regular"
    postseason = "postseason"
    both = "both"
    allstar = "allstar"
    spring_regular = "spring_regular"
    spring_postseason = "spring_postseason"


class Classification(str, Enum):
    """Division classification enumeration for API requests."""
    fbs = "fbs"
    fcs = "fcs"
    ii = "ii"
    iii = "iii"


def validate_year_or_id_required(
    year: Optional[int],
    id_field: Optional[int],
    id_field_name: str = "id"
) -> None:
    """Validate that either year or id field is provided."""
    if year is None and id_field is None:
        raise ValueError(f"year is required when {id_field_name} is not specified")


def validate_at_least_one_of(
    values: Dict[str, Any],
    field_names: List[str],
    context_message: str = "At least one of the following fields is required"
) -> None:
    """Validate that at least one of the specified fields has a value."""
    if not any(values.get(field) is not None for field in field_names):
        field_list = ", ".join(field_names)
        raise ValueError(f"{context_message}: {field_list}")


def validate_team_game_stats_logic(
    year: Optional[int],
    week: Optional[int],
    team: Optional[str],
    conference: Optional[str],
    game_id: Optional[int]
) -> None:
    """Validate the complex conditional logic for /games/teams endpoint."""
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
```

### File: `cfb_data/cfb_data/base/validation/__init__.py`

```python
"""Validation utilities for CFBD API requests."""

from .request_validators import (
    Classification,
    SeasonType,
    validate_at_least_one_of,
    validate_team_game_stats_logic,
    validate_year_or_id_required,
)

__all__ = [
    "Classification",
    "SeasonType",
    "validate_at_least_one_of",
    "validate_team_game_stats_logic",
    "validate_year_or_id_required",
]
```

## Phase 2: Update Request Models

### Updated `cfb_data/cfb_data/game/models/pydantic/requests.py`

#### Key Changes:
1. Import shared validation utilities
2. Use proper enums for season_type and classification
3. Add `@model_validator` decorators for conditional logic
4. Fix field naming inconsistencies

#### Critical Model Updates:

##### 1. GamesRequest - Fix year/id conditional validation
```python
from cfb_data.base.validation import SeasonType, Classification, validate_year_or_id_required

class GamesRequest(BaseModel):
    """Request parameters for /games endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    home: Optional[str] = None
    away: Optional[str] = None
    conference: Optional[str] = None
    classification: Optional[Classification] = None  # Fixed from 'division'
    id: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode='after')
    def validate_year_or_id(self) -> 'GamesRequest':
        """Validate that year is required when id is not specified."""
        validate_year_or_id_required(self.year, self.id, "id")
        return self
```

##### 2. TeamGameStatsRequest - Fix complex conditional validation
```python
class TeamGameStatsRequest(BaseModel):
    """Request parameters for /games/teams endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    game_id: Optional[int] = Field(default=None, ge=0, alias="gameId")
    classification: Optional[Classification] = None

    @model_validator(mode='after')
    def validate_team_stats_requirements(self) -> 'TeamGameStatsRequest':
        """Validate complex conditional requirements for /games/teams."""
        validate_team_game_stats_logic(
            self.year, self.week, self.team, self.conference, self.game_id
        )
        return self
```

##### 3. Other Request Models - Add consistent validation

```python
class GameMediaRequest(BaseModel):
    """Request parameters for /games/media endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    year: int = Field(ge=1869, le=2030)  # Required - no conditional logic needed
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    media_type: Optional[str] = Field(default=None, alias="mediaType")
    classification: Optional[Classification] = None


class PlayerGameStatsRequest(BaseModel):
    """Request parameters for /games/players endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    year: Optional[int] = Field(default=None, ge=1869, le=2030)
    week: Optional[int] = Field(default=None, ge=0, le=20)
    season_type: Optional[SeasonType] = Field(default=None, alias="seasonType")
    team: Optional[str] = None
    conference: Optional[str] = None
    category: Optional[str] = None
    game_id: Optional[int] = Field(default=None, ge=0, alias="gameId")

    # Note: API spec unclear on exact requirements - may need year validation
```

## Phase 3: Update API Layer

### Updated `cfb_data/cfb_data/game/api/game_api.py`

#### Key Changes:
1. Remove hard-coded validation logic
2. Rely on request model validation
3. Use request models consistently
4. Uncomment disabled validations

#### Critical Updates:

```python
from cfb_data.game.models.pydantic.requests import (
    GamesRequest,
    TeamGameStatsRequest,
    PlayerGameStatsRequest,
    GameMediaRequest,
    CalendarRequest,
    GameWeatherRequest,
    AdvancedBoxScoreRequest,
)

class CFBDGamesAPI(CFBDAPIBase):
    """Games-specific endpoints for the College Football Data API."""

    @route("/games", response_model=Game, dataframe_schema=GameSchema)
    async def _get_games(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get game information."""
        # Validate using request model instead of hard-coded check
        request = GamesRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/games", validated_params)

    @route("/games/teams", response_model=TeamGameStats, dataframe_schema=TeamGameStatsSchema)
    async def _get_team_game_stats(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get team statistics by game."""
        # Use model validation instead of commented-out hard-coded check
        request = TeamGameStatsRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/games/teams", validated_params)

    @route("/games/players", response_model=PlayerGameStats, dataframe_schema=PlayerGameStatsSchema)
    async def _get_player_game_stats(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get player statistics by game."""
        # Use model validation instead of commented-out hard-coded check
        request = PlayerGameStatsRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/games/players", validated_params)

    @route("/calendar", response_model=CalendarWeek, dataframe_schema=CalendarWeekSchema)
    async def _get_calendar(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get calendar/weeks for a given year."""
        # CalendarRequest already requires year - no change needed
        request = CalendarRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/calendar", validated_params)

    @route("/games/media", response_model=GameMedia, dataframe_schema=GameMediaSchema)
    async def _get_game_media(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get game media information and types."""
        # GameMediaRequest already requires year - no change needed
        request = GameMediaRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/games/media", validated_params)

    @route("/games/box/advanced", response_model=AdvancedBoxScore, dataframe_schema=None)
    async def _get_box_scores(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get box score data for a specific game."""
        # AdvancedBoxScoreRequest already requires gameId - no change needed
        request = AdvancedBoxScoreRequest.model_validate(params)
        validated_params = request.model_dump(exclude_none=True, by_alias=True)
        return await self._make_request("/games/box/advanced", validated_params)
```

## Phase 4: Comprehensive Test Suite

### File: `cfb_data/tests/test_request_validation.py`

```python
"""Test request validation logic."""

import pytest
from pydantic import ValidationError

from cfb_data.game.models.pydantic.requests import (
    GamesRequest,
    TeamGameStatsRequest,
    PlayerGameStatsRequest,
)
from cfb_data.base.validation import SeasonType, Classification


class TestGamesRequestValidation:
    """Test GamesRequest validation logic."""

    def test_valid_request_with_year(self):
        """Test valid request with year parameter."""
        request = GamesRequest(year=2023, week=1, season_type=SeasonType.regular)
        assert request.year == 2023
        assert request.week == 1

    def test_valid_request_with_id(self):
        """Test valid request with id parameter (no year required)."""
        request = GamesRequest(id=123456)
        assert request.id == 123456
        assert request.year is None

    def test_invalid_request_no_year_no_id(self):
        """Test invalid request with neither year nor id."""
        with pytest.raises(ValidationError) as exc_info:
            GamesRequest(week=1)

        errors = exc_info.value.errors()
        assert any("year is required when id is not specified" in str(error) for error in errors)

    def test_season_type_enum_validation(self):
        """Test season type enum validation."""
        # Valid enum value
        request = GamesRequest(year=2023, season_type=SeasonType.postseason)
        assert request.season_type == SeasonType.postseason

        # Invalid enum value should raise ValidationError
        with pytest.raises(ValidationError):
            GamesRequest(year=2023, season_type="invalid_season")

    def test_classification_enum_validation(self):
        """Test classification enum validation."""
        # Valid enum value
        request = GamesRequest(year=2023, classification=Classification.fbs)
        assert request.classification == Classification.fbs

        # Invalid enum value should raise ValidationError
        with pytest.raises(ValidationError):
            GamesRequest(year=2023, classification="invalid_classification")


class TestTeamGameStatsRequestValidation:
    """Test TeamGameStatsRequest complex validation logic."""

    def test_valid_request_with_game_id(self):
        """Test valid request with game_id (no other requirements)."""
        request = TeamGameStatsRequest(game_id=123456)
        assert request.game_id == 123456

    def test_valid_request_year_and_week(self):
        """Test valid request with year and week."""
        request = TeamGameStatsRequest(year=2023, week=1)
        assert request.year == 2023
        assert request.week == 1

    def test_valid_request_year_and_team(self):
        """Test valid request with year and team."""
        request = TeamGameStatsRequest(year=2023, team="Alabama")
        assert request.year == 2023
        assert request.team == "Alabama"

    def test_valid_request_year_and_conference(self):
        """Test valid request with year and conference."""
        request = TeamGameStatsRequest(year=2023, conference="SEC")
        assert request.year == 2023
        assert request.conference == "SEC"

    def test_invalid_request_no_game_id_no_year(self):
        """Test invalid request without game_id and without year."""
        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(week=1)

        errors = exc_info.value.errors()
        assert any("year is required when game_id is not specified" in str(error) for error in errors)

    def test_invalid_request_year_but_no_filters(self):
        """Test invalid request with year but no week/team/conference."""
        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(year=2023)

        errors = exc_info.value.errors()
        assert any("At least one of week, team, or conference is required" in str(error) for error in errors)

    def test_year_range_validation(self):
        """Test year range validation."""
        # Valid year range
        request = TeamGameStatsRequest(year=2023, week=1)
        assert request.year == 2023

        # Invalid year (too low)
        with pytest.raises(ValidationError):
            TeamGameStatsRequest(year=1800, week=1)

        # Invalid year (too high)
        with pytest.raises(ValidationError):
            TeamGameStatsRequest(year=2050, week=1)

    def test_week_range_validation(self):
        """Test week range validation."""
        # Valid week range
        request = TeamGameStatsRequest(year=2023, week=15)
        assert request.week == 15

        # Invalid week (negative)
        with pytest.raises(ValidationError):
            TeamGameStatsRequest(year=2023, week=-1)

        # Invalid week (too high)
        with pytest.raises(ValidationError):
            TeamGameStatsRequest(year=2023, week=25)


class TestRequestModelAliases:
    """Test that request models generate correct API parameters."""

    def test_games_request_aliases(self):
        """Test GamesRequest generates correct camelCase aliases."""
        request = GamesRequest(
            year=2023,
            season_type=SeasonType.regular,
            id=123
        )

        params = request.model_dump(exclude_none=True, by_alias=True)

        # Should use camelCase for API
        assert "seasonType" in params
        assert "season_type" not in params
        assert params["seasonType"] == "regular"
        assert params["year"] == 2023
        assert params["id"] == 123

    def test_team_stats_request_aliases(self):
        """Test TeamGameStatsRequest generates correct camelCase aliases."""
        request = TeamGameStatsRequest(
            year=2023,
            season_type=SeasonType.postseason,
            game_id=456
        )

        params = request.model_dump(exclude_none=True, by_alias=True)

        # Should use camelCase for API
        assert "gameId" in params
        assert "game_id" not in params
        assert "seasonType" in params
        assert "season_type" not in params
        assert params["gameId"] == 456
        assert params["seasonType"] == "postseason"
```

## Phase 5: Implementation Steps

### Step 1: Create Base Infrastructure
1. Create `cfb_data/cfb_data/base/validation/` directory
2. Create `request_validators.py` with shared utilities
3. Create `__init__.py` for proper imports
4. Update `cfb_data/cfb_data/base/__init__.py` if needed

### Step 2: Update Request Models
1. Update imports in `requests.py` to include validation utilities
2. Replace `season_type: Optional[str]` with `season_type: Optional[SeasonType]`
3. Replace `division: Optional[str]` with `classification: Optional[Classification]`
4. Add `@model_validator` decorators to `GamesRequest` and `TeamGameStatsRequest`
5. Test each model individually

### Step 3: Update API Layer
1. Import request models in `game_api.py`
2. Replace hard-coded validation with model validation
3. Use `request.model_dump(exclude_none=True, by_alias=True)` for API parameters
4. Remove commented-out validation code
5. Test each endpoint

### Step 4: Comprehensive Testing
1. Create test file with all validation scenarios
2. Test positive cases (valid requests)
3. Test negative cases (invalid requests)
4. Test edge cases and boundary conditions
5. Test API parameter generation with aliases

### Step 5: Integration Testing
1. Test with actual API calls (if possible)
2. Verify error messages are clear and helpful
3. Check backwards compatibility
4. Performance testing for validation overhead

## Expected Outcomes

### Immediate Benefits:
- ✅ Request validation happens at model level, not API level
- ✅ Clear, helpful error messages for invalid requests
- ✅ Consistent validation across all endpoints
- ✅ Proper enum validation for season types and classifications
- ✅ Complex conditional logic properly enforced

### Long-term Benefits:
- ✅ Reduced API call failures due to invalid parameters
- ✅ Better developer experience with early validation
- ✅ Maintainable validation logic in centralized utilities
- ✅ Type safety improvements with proper enums
- ✅ Automatic documentation of valid parameter combinations

## Risk Mitigation

### Breaking Changes:
- Request models with previously invalid combinations will now raise `ValidationError`
- API layer behavior changes from manual checks to model validation
- Enum types may require code updates for existing users

### Mitigation Strategies:
- Comprehensive testing before deployment
- Clear migration documentation
- Backwards compatibility period if needed
- Gradual rollout of validation features

## Success Criteria

1. **All API specification rules enforced** in request models
2. **No hard-coded validation** remaining in API layer
3. **100% test coverage** for validation logic
4. **Clear error messages** for all validation failures
5. **Consistent enum usage** across all request models
6. **Proper field aliases** generating correct API parameters

This implementation plan provides a complete blueprint for fixing all request validation issues while maintaining code quality and backwards compatibility.
