# College Football Data API Documentation

Comprehensive documentation for the College Football Data API endpoints, sourced directly from the official API documentation at https://apinext.collegefootballdata.com/.

## Overview

This directory contains detailed specifications for College Football Data API endpoints, designed to support robust implementation of request validation and response handling in the cfb-data Python package.

## Documentation Structure

### Primary Endpoints

| Endpoint Family | Documentation | Implementation Status | Complexity |
|----------------|---------------|----------------------|------------|
| **Games** | [`games_api.md`](games_api.md) | ✅ Partial (1/6 endpoints) | High |
| **Drives** | [`drives_api.md`](drives_api.md) | ❌ Not Implemented | Medium |
| **Teams** | *Not yet documented* | ❌ Not Implemented | TBD |
| **Players** | *Not yet documented* | ❌ Not Implemented | TBD |
| **Recruiting** | *Not yet documented* | ❌ Not Implemented | TBD |
| **Statistics** | *Not yet documented* | ❌ Not Implemented | TBD |

### Implementation Priority

Based on complexity analysis and current codebase architecture:

1. **High Priority**
   - [`/games/teams`](games_api.md#endpoint-gamesteams) - Complex conditional validation identified
   - [`/drives`](drives_api.md) - Foundation for drives API enhancement

2. **Medium Priority**
   - [`/games/players`](games_api.md#endpoint-gamesplayers) - Player statistics
   - [`/games/media`](games_api.md#endpoint-gamesmedia) - Media information
   - [`/games/weather`](games_api.md#endpoint-gamesweather) - Weather data

3. **Lower Priority**
   - [`/games/box/advanced`](games_api.md#endpoint-gamesboxadvanced) - Advanced statistics

## Key Findings

### Validation Complexity Analysis

#### Simple Validation Pattern (Implemented)
- **Example:** [`/games`](games_api.md#endpoint-games)
- **Logic:** `year` required OR `id` specified
- **Status:** ✅ Fully implemented with robust testing

#### Complex Conditional Validation (Not Implemented)
- **Example:** [`/games/teams`](games_api.md#endpoint-gamesteams)
- **Logic:** `year` required AND (at least one of `week`, `team`, or `conference`) OR `id` specified
- **Challenge:** Requires sophisticated multi-parameter validation logic
- **Status:** ❌ Identified but not implemented

#### Standard Validation Pattern
- **Example:** [`/drives`](drives_api.md)
- **Logic:** `year` required with optional filters
- **Status:** ❌ Not implemented, but straightforward

### Common Validation Patterns

All endpoints share these standardized patterns:

#### Required Enums
```python
SeasonType = Literal["regular", "postseason", "both", "allstar", "spring_regular", "spring_postseason"]
Classification = Literal["fbs", "fcs", "ii", "iii"]
```

#### Field Aliases
- API uses **camelCase**: `seasonType`, `gameId`
- Python uses **snake_case**: `season_type`, `game_id`
- Handled by Pydantic `alias` definitions

#### Standard Ranges
- **Year**: 1869-2030 (college football history to reasonable future)
- **Week**: 0-20 (regular season + postseason weeks)

## API Architecture Insights

### Current Implementation Strengths
1. **Robust Base Validation**: [`request_validators.py`](../../cfb_data/cfb_data/base/validation/request_validators.py)
2. **Comprehensive Testing**: 303 lines of test coverage for games endpoint
3. **Pydantic Integration**: Full type safety and validation
4. **Field Alias Support**: Seamless API parameter conversion

### Implementation Gaps Identified
1. **Complex Conditional Logic**: `/games/teams` validation not implemented
2. **Missing Endpoints**: Most endpoint families lack implementation
3. **Response Model Coverage**: Limited response validation patterns

## Implementation Recommendations

### Immediate Next Steps

#### 1. Implement `/games/teams` Validation
```python
@model_validator(mode='after')
def validate_games_teams_requirements(self) -> 'GamesTeamsRequest':
    """Validate complex conditional requirements for games/teams endpoint."""
    if self.id is not None:
        # ID bypasses all other requirements
        return self

    if self.year is None:
        raise ValueError("year is required when id is not specified")

    # Year provided, check for at least one additional filter
    if not any([self.week, self.team, self.conference]):
        raise ValueError(
            "year must be provided along with at least one of: week, team, or conference"
        )

    return self
```

#### 2. Implement `/drives` API
- Standard validation pattern (straightforward)
- Foundation for drives enhancement project
- Good next implementation target

#### 3. Expand Documentation
- Research remaining endpoint families via browser automation
- Document validation requirements for each endpoint
- Identify additional complex validation patterns

### Long-term Architecture Goals

#### Validation Framework Enhancement
1. **Conditional Validation DSL**: Create reusable patterns for complex logic
2. **Validation Testing Framework**: Automated test generation for parameter combinations
3. **Response Validation**: Expand beyond request validation to response validation

#### Documentation Automation
1. **API Specification Sync**: Automated documentation updates from API changes
2. **Example Generation**: Automated request/response examples
3. **Implementation Tracking**: Automated status updates

## Quick Navigation

### By Endpoint Type
- **Game Data**: [`games_api.md`](games_api.md) - Historical game information and statistics
- **Drive Data**: [`drives_api.md`](drives_api.md) - Offensive drive details and outcomes

### By Implementation Status
- **Implemented**: [`/games`](games_api.md#endpoint-games) ✅
- **Complex Validation Needed**: [`/games/teams`](games_api.md#endpoint-gamesteams) ⚠️
- **Ready to Implement**: [`/drives`](drives_api.md) 🔄
- **Needs Research**: All other endpoints 📋

### By Validation Complexity
- **Simple**: Single conditional requirement
- **Complex**: Multi-parameter conditional logic
- **Standard**: Required year with optional filters

## Contributing

When adding new endpoint documentation:

1. **Use Browser Research**: Get authoritative specifications from https://apinext.collegefootballdata.com/
2. **Document Validation Logic**: Include complex conditional requirements
3. **Provide Examples**: Show valid and invalid request patterns
4. **Update Implementation Status**: Mark current implementation state
5. **Link to Code**: Reference existing implementations where applicable

## Related Documentation

- **Project Overview**: [`../../README.md`](../../README.md) - Main project documentation
- **Implementation Analysis**: [`../../cfb_data/request_validation_analysis.md`](../../cfb_data/request_validation_analysis.md) - Technical validation analysis
- **Implementation Plan**: [`../../cfb_data/request_validation_implementation_plan.md`](../../cfb_data/request_validation_implementation_plan.md) - Development roadmap

---

*Last Updated: 2025-01-19 - Based on comprehensive API research and codebase analysis*
