# College Football Data API Request Validation Analysis

## Executive Summary
The current request models have several critical validation gaps that allow invalid API requests to be created. The API specification defines complex conditional validation rules that are not enforced in our Pydantic models.

## Critical Issues Found

### 1. `/games` Endpoint - [`GamesRequest`](cfb_data/cfb_data/game/models/pydantic/requests.py:10)

**API Rule**:
- `year`: "Required year filter (except when id is specified)"

**Current Implementation Issues**:
- ❌ `year: Optional[int]` - Should be required when `id` is not provided
- ❌ No conditional validation logic
- ❌ Missing enum validation for `season_type`
- ❌ Missing enum validation for `division` (should be `classification`)

**API Validation Logic Required**:
```python
if id is None and year is None:
    raise ValueError("year is required when id is not specified")
```

### 2. `/games/teams` Endpoint - [`TeamGameStatsRequest`](cfb_data/cfb_data/game/models/pydantic/requests.py:169)

**API Rules**:
- `year`: "Required year filter (along with one of week, team, or conference), unless id is specified"
- `week`: "Optional week filter, required if team and conference not specified"
- `team`: "Optional team filter, required if week and conference not specified"
- `conference`: "Optional conference filter, required if week and team not specified"

**Current Implementation Issues**:
- ❌ All fields are `Optional` with no conditional logic
- ❌ Complex "one of" requirements not enforced
- ❌ No validation for required combinations

**API Validation Logic Required**:
```python
# If id is not specified:
if game_id is None:
    # year is required along with at least one of week, team, or conference
    if year is None:
        raise ValueError("year is required when game_id is not specified")

    # At least one of week, team, or conference must be specified
    if week is None and team is None and conference is None:
        raise ValueError("At least one of week, team, or conference is required when game_id is not specified")
```

### 3. Inconsistent API Implementation - [`CFBDGamesAPI`](cfb_data/cfb_data/game/api/game_api.py:29)

**Implementation Issues**:
- ❌ Line 47: Hard-coded `year` requirement check instead of using model validation
- ❌ Lines 141-142, 163-164: Commented out year validation for `/games/players` and `/games/teams`
- ❌ Inconsistent validation between different endpoints
- ❌ Validation happens at API layer instead of model layer

### 4. Missing Enum Validation

**`seasonType` Parameter Issues**:
- ❌ Current: `season_type: Optional[str]`
- ✅ Should be: Enum with values `["regular", "postseason", "both", "allstar", "spring_regular", "spring_postseason"]`

**`classification` Parameter Issues**:
- ❌ Current: `classification: Optional[str]`
- ✅ Should be: Enum with values `["fbs", "fcs", "ii", "iii"]`

### 5. Missing Field Name Mismatch

**API vs Model Field Names**:
- ❌ API uses `classification`, model has `division` in some places
- ❌ Inconsistent field naming across request models

## Impact Assessment

### High Impact Issues:
1. **Invalid API Calls**: Users can create requests that will fail at the API level
2. **Poor User Experience**: Errors caught late in the process instead of at validation time
3. **Inconsistent Behavior**: Different endpoints have different validation strategies
4. **Data Quality**: Invalid parameters can be passed through

### Medium Impact Issues:
1. **Maintenance Burden**: Hard-coded validation in API classes instead of reusable model validation
2. **Code Duplication**: Validation logic scattered across multiple files

## Recommended Solutions

### Phase 1: Core Conditional Validation
1. **Implement `model_validator` decorators** for complex conditional logic
2. **Fix [`GamesRequest`](cfb_data/cfb_data/game/models/pydantic/requests.py:10)** with year/id conditional validation
3. **Fix [`TeamGameStatsRequest`](cfb_data/cfb_data/game/models/pydantic/requests.py:169)** with complex conditional logic

### Phase 2: Enum Validation
1. **Create shared enums** for `SeasonType` and `Classification`
2. **Update all request models** to use proper enum validation
3. **Ensure consistent field naming** across all models

### Phase 3: API Layer Cleanup
1. **Remove hard-coded validation** from [`CFBDGamesAPI`](cfb_data/cfb_data/game/api/game_api.py:29)
2. **Rely on model validation** instead of API-layer checks
3. **Uncomment and fix** disabled validations

### Phase 4: Comprehensive Testing
1. **Create validation test suite** for all conditional logic
2. **Test edge cases** and complex parameter combinations
3. **Verify consistency** with actual API behavior

## Implementation Strategy

### 1. Shared Validation Components
```python
# Create shared enums and validators
class SeasonType(str, Enum): ...
class Classification(str, Enum): ...

# Create reusable validator functions
def validate_year_or_id(values): ...
def validate_one_of_required(values, fields): ...
```

### 2. Model-Level Validation
```python
# Use Pydantic v2 model_validator for complex logic
@model_validator(mode='after')
def validate_conditional_requirements(self) -> 'RequestModel':
    # Implement conditional validation logic
    return self
```

### 3. Backwards Compatibility
- Maintain existing public API
- Add deprecation warnings for incorrect usage
- Provide clear error messages for validation failures

## Next Steps
1. Create shared validation utilities
2. Implement conditional validation for critical endpoints
3. Update API layer to rely on model validation
4. Create comprehensive test suite
5. Document proper usage patterns

## Files Requiring Updates
- [`cfb_data/cfb_data/game/models/pydantic/requests.py`](cfb_data/cfb_data/game/models/pydantic/requests.py:1)
- [`cfb_data/cfb_data/game/api/game_api.py`](cfb_data/cfb_data/game/api/game_api.py:1)
- [`cfb_data/cfb_data/game/models/pydantic/responses.py`](cfb_data/cfb_data/game/models/pydantic/responses.py:1) (for shared enums)
- New: `cfb_data/cfb_data/base/validation/request_validators.py` (shared utilities)
