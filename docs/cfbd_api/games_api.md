# College Football Data API - Games Endpoints

This document provides comprehensive specification for all College Football Data API games-related endpoints, sourced directly from the official API documentation at https://apinext.collegefootballdata.com/.

## Overview

The games API family provides access to historical college football game data through multiple specialized endpoints, each with specific validation requirements and response formats.

## Table of Contents

- [Common Parameters](#common-parameters)
- [Endpoint: /games](#endpoint-games)
- [Endpoint: /games/teams](#endpoint-gamesteams)
- [Endpoint: /games/players](#endpoint-gamesplayers)
- [Endpoint: /games/media](#endpoint-gamesmedia)
- [Endpoint: /games/weather](#endpoint-gamesweather)
- [Endpoint: /games/box/advanced](#endpoint-gamesboxadvanced)
- [Related Endpoints](#related-endpoints)
- [Implementation Guidelines](#implementation-guidelines)

## Common Parameters

The following parameters are shared across multiple games endpoints:

### Standard Parameters

| Parameter | Type | Description | Valid Values |
|-----------|------|-------------|--------------|
| `year` | integer($int32) | Year filter | 1869-2030 (start of college football to reasonable future) |
| `week` | integer($int32) | Week filter | 0-20 (includes postseason weeks) |
| `seasonType` | string | Season type filter | `regular`, `postseason`, `both`, `allstar`, `spring_regular`, `spring_postseason` |
| `team` | string | Team filter | Any valid team name |
| `home` | string | Home team filter | Any valid team name |
| `away` | string | Away team filter | Any valid team name |
| `conference` | string | Conference filter | Any valid conference name |
| `classification` | string | Division classification filter | `fbs`, `fcs`, `ii`, `iii` |
| `id` | integer($int32) | Game ID filter | Any positive integer |

### Field Aliases

- **API uses camelCase:** `seasonType`, `gameId`
- **Python uses snake_case:** `season_type`, `game_id`
- **Pydantic handles conversion** with `alias` field definitions

---

## Endpoint: /games

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/games`
- **Description:** Retrieves historical game data with comprehensive filtering options
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Required Parameters (Conditional)
- **`year`** (`integer`) - **Required year filter (except when id is specified)**
  - **Validation:** `ge=1869, le=2030`
  - **Type:** `integer($int32)`
  - **Conditional Logic:** Required unless `id` parameter is specified

#### Optional Parameters

| Parameter | Type | Description | Validation |
|-----------|------|-------------|------------|
| `week` | integer($int32) | Optional week filter | `ge=0, le=20` |
| `seasonType` | string | Optional season type filter | Enum values listed above |
| `team` | string | Filter by any team (home or away) | - |
| `home` | string | Filter by home team specifically | - |
| `away` | string | Filter by away team specifically | - |
| `conference` | string | Optional conference filter | - |
| `classification` | string | Optional division classification filter | Enum values listed above |
| `id` | integer($int32) | Game id filter for single game | `ge=0` |

### Validation Rules

#### Conditional Logic
1. **Year/ID Requirement:** `year` is required UNLESS `id` is specified
   - Error message: "year is required when id is not specified"

### Example Requests

```bash
# Basic request (year required)
GET /games?year=2023

# Filtered request (multiple parameters)
GET /games?year=2023&week=1&seasonType=regular&team=Alabama&conference=SEC&classification=fbs

# Single game request (ID bypasses year requirement)
GET /games?id=401520340

# Conference championship games
GET /games?year=2023&seasonType=postseason&classification=fbs

# Team's home games
GET /games?year=2023&home=Alabama&seasonType=regular
```

### Response Format
- **Content-Type:** `application/json`
- **HTTP Status:** `200 OK`
- **Structure:** Array of game objects

---

## Endpoint: /games/teams

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/games/teams`
- **Description:** Retrieves team box score statistics
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Required Parameters (Complex Conditional Logic)
- **`year`** (`integer`) - **Required year filter (along with one of week, team, or conference), unless id is specified**
  - **Type:** `integer($int32)`
  - **Complex Validation:** Must be provided along with at least one of `week`, `team`, or `conference` unless `id` is specified

#### Conditional Parameters (At Least One Required with Year)
- **`week`** (`integer`) - **Optional week filter, required if team and conference not specified**
  - **Type:** `integer($int32)`
  - **Conditional Logic:** Required if neither `team` nor `conference` is provided

- **`team`** (`string`) - **Optional team filter, required if week and conference not specified**
  - **Type:** `string`
  - **Conditional Logic:** Required if neither `week` nor `conference` is provided

- **`conference`** (`string`) - **Optional conference filter, required if week and team not specified**
  - **Type:** `string`
  - **Conditional Logic:** Required if neither `week` nor `team` is provided

#### Optional Parameters

| Parameter | Type | Description | Valid Values |
|-----------|------|-------------|--------------|
| `classification` | string | Optional division classification filter | `fbs`, `fcs`, `ii`, `iii` |
| `seasonType` | string | Optional season type filter | `regular`, `postseason`, `both`, `allstar`, `spring_regular`, `spring_postseason` |
| `id` | integer($int32) | Optional id filter to retrieve a single game | Any positive integer |

### Complex Validation Logic

This endpoint requires sophisticated validation:

1. **Base Requirement:** `year` is required unless `id` is specified
2. **Additional Requirement:** When `year` is provided, at least one of the following must also be provided:
   - `week`
   - `team`
   - `conference`
3. **ID Bypass:** When `id` is specified, all other requirements are bypassed

### Example Requests

```bash
# Valid: Year + week
GET /games/teams?year=2023&week=1

# Valid: Year + team
GET /games/teams?year=2023&team=Alabama

# Valid: Year + conference
GET /games/teams?year=2023&conference=SEC

# Valid: Year + multiple filters
GET /games/teams?year=2023&week=1&conference=SEC&classification=fbs

# Valid: ID only (bypasses all other requirements)
GET /games/teams?id=401520340

# Invalid: Year alone without week, team, or conference
GET /games/teams?year=2023  # ❌ Validation Error

# Invalid: Week without year (unless id provided)
GET /games/teams?week=1  # ❌ Validation Error
```

### Response Format
- **Content-Type:** `application/json`
- **HTTP Status:** `200 OK`
- **Structure:** Object containing game ID and teams array with detailed statistics

### Example Response Structure
```json
{
  "id": 0,
  "teams": [
    {
      "homeAway": "string",
      "points": 0,
      "stats": [
        {
          "category": "string",
          "stat": "string"
        }
      ]
    }
  ]
}
```

---

## Endpoint: /games/players

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/games/players`
- **Description:** Retrieves player box score statistics
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Conditional Parameters
- **`year`** (`integer`) - **Required year filter (unless `id` is specified)**. Must be provided with `week`, `team`, or `conference`.
- **`week`** (`integer`) - Optional week filter.
- **`team`** (`string`) - Optional team filter.
- **`conference`** (`string`) - Optional conference filter.
- **`id`** (`integer`) - Game ID filter. Bypasses other requirements.

#### Optional Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `seasonType`| string | Optional season type filter (`regular`, `postseason`) |
| `category`| string | Optional player statistical category filter (e.g., `passing`, `rushing`) |
| `classification`| string | Optional division classification filter (`fbs`, `fcs`, `ii`, `iii`) |

### Validation Logic
- `id` bypasses all other requirements.
- If `id` is not provided, `year` is required.
- If `year` is provided, at least one of `week`, `team`, or `conference` must also be provided.

### Example Request
```bash
# Get player stats for a specific game
GET /games/players?id=401520340

# Get player stats for a team in a specific week
GET /games/players?year=2023&week=1&team=Texas
```
### Response Format
- **Content-Type:**`application/json`
- **HTTP Status:**`200 OK`
- **Structure:** Array of game objects, each containing player stats grouped by team and category.

---

## Endpoint: /games/media

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/games/media`
- **Description:** Retrieves game media information (TV, radio, web, etc.).
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Required Parameters
- **`year`** (`integer`) - **Required year filter.**

#### Optional Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `week` | integer | Optional week filter |
| `seasonType`| string | Optional season type filter |
| `team`      | string | Optional team filter |
| `conference`| string | Optional conference filter |
| `mediaType` | string | Optional media type filter (e.g., `tv`, `radio`, `web`, `ppv`, `mobile`) |
| `classification`| string | Optional division classification filter (`fbs`, `fcs`, `ii`, `iii`) |

### Example Request
```bash
# Get all media for the 2023 season
GET /games/media?year=2023

# Get TV media for week 1 of the 2023 season
GET /games/media?year=2023&week=1&mediaType=tv
```
### Response Format
- **Content-Type:**`application/json`
- **HTTP Status:**`200 OK`
- **Structure:** Array of game media objects.

---

## Endpoint: /games/weather

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/games/weather`
- **Description:** Retrieves game weather data. **Patreon only.**
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Optional Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `gameId` | integer | Game ID filter |
| `year` | integer | Year filter |
| `week` | integer | Optional week filter |
| `seasonType`| string | Optional season type filter |
| `team`      | string | Optional team filter |
| `conference`| string | Optional conference filter |
| `classification`| string | Optional division classification filter (`fbs`, `fcs`, `ii`, `iii`) |

### Validation Logic
- If `gameId` is provided, other filters are ignored.
- If `gameId` is not provided, `year` is the minimum required field.

### Example Request
```bash
# Get weather for a specific game
GET /games/weather?gameId=401520340

# Get weather for all games in week 1 of 2023
GET /games/weather?year=2023&week=1
```
### Response Format
- **Content-Type:**`application/json`
- **HTTP Status:**`200 OK`
- **Structure:** Array of game weather objects.

---

## Endpoint: /games/box/advanced

### Basic Information
- **HTTP Method:** GET
- **Endpoint:** `/game/box/advanced`
- **Description:** Retrieves advanced box score data for a single game.
- **Implementation Status:** ✅ **Fully Documented**

### Request Parameters

#### Required Parameters
- **`id`** (`integer`) - **Required game ID filter.**

### Example Request
```bash
# Get advanced box score for a specific game
GET /game/box/advanced?id=401520340
```
### Response Format
- **Content-Type:**`application/json`
- **HTTP Status:**`200 OK`
- **Structure:** A single advanced box score object.

---

## Related Endpoints

Additional endpoints that follow similar validation patterns:

- **`/calendar`** - Calendar/weeks data
- **`/records`** - Team records by year

All follow the same validation patterns and enum definitions established by the `/games` endpoints.

---

## Implementation Guidelines

### Priority Implementation Order

1. **`/games/teams`** - High priority due to complex validation requirements
2. **`/games/players`** - Medium priority for player statistics
3. **`/games/media`** - Lower priority for media information
4. **`/games/weather`** - Lower priority for weather data
5. **`/games/box/advanced`** - Lower priority for advanced statistics

### Validation Architecture Requirements

#### For /games/teams (Complex Conditional Logic)
```python
# Pseudo-code for complex validation
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

#### Shared Validation Components
- **Enum Support:** `SeasonType` and `Classification` enums
- **Field Aliases:** API parameter name mapping with `by_alias=True`
- **Range Validation:** Year (1869-2030), Week (0-20)

### Testing Requirements

Each endpoint requires comprehensive test coverage:

1. **Required parameter tests**
2. **Complex conditional logic tests** (especially for `/games/teams`)
3. **Enum validation tests**
4. **Edge case tests** (boundary years, invalid combinations)
5. **Integration tests** with actual API responses

### Error Handling

#### Validation Errors
- **Missing Required Parameters:** Clear error messages about conditional requirements
- **Invalid Conditional Logic:** Specific feedback about parameter combinations
- **Invalid Enum Values:** Specific feedback about valid options
- **Range Violations:** Boundary validation with helpful constraints

#### HTTP Error Responses
- **400 Bad Request:** Parameter validation failures
- **401 Unauthorized:** Missing or invalid API authentication
- **429 Too Many Requests:** Rate limiting exceeded
- **500 Internal Server Error:** Server-side issues

---

## Current Implementation Status

### Implemented Endpoints
- ✅ **`/games`** - Fully implemented with robust validation
  - Location: [`cfb_data.game.models.pydantic.requests.GamesRequest`](../../cfb_data/cfb_data/game/models/pydantic/requests.py:18-67)
  - Tests: [`tests/game/models/pydantic/test_requests.py`](../../cfb_data/cfb_data/tests/game/models/pydantic/test_requests.py) (303 lines)

### Not Yet Implemented
- ❌ **`/games/teams`** - Complex validation requirements identified
- ❌ **`/games/players`** - Not yet implemented
- ❌ **`/games/media`** - Not yet implemented
- ❌ **`/games/weather`** - Not yet implemented
- ❌ **`/games/box/advanced`** - Not yet implemented

This specification provides the foundation for implementing robust validation and request handling for all games API endpoints, ensuring compatibility with the official College Football Data API.
