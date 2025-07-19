# College Football Data API - Drives Endpoint

This document provides comprehensive specification for the College Football Data API drives endpoint, sourced directly from the official API documentation at https://apinext.collegefootballdata.com/.

## Overview

The drives endpoint retrieves historical drive data from college football games, providing detailed information about offensive drives during gameplay.

## Endpoint Details

### Base Information
- **HTTP Method:** GET
- **Endpoint:** `/drives`
- **Description:** Retrieves historical drive data
- **Response Format:** JSON (application/json)

## Request Parameters

### Required Parameters

| Parameter | Type | Location | Description |
|-----------|------|----------|-------------|
| `year` | integer($int32) | query | Required year filter |

### Optional Parameters

| Parameter | Type | Location | Description | Valid Values |
|-----------|------|----------|-------------|--------------|
| `seasonType` | string | query | Optional season type filter | `regular`, `postseason`, `both`, `allstar`, `spring_regular`, `spring_postseason` |
| `week` | integer($int32) | query | Optional week filter | Any valid week number |
| `team` | string | query | Optional team filter | Any valid team name |
| `offense` | string | query | Optional offensive team filter | Any valid team name |
| `defense` | string | query | Optional defensive team filter | Any valid team name |
| `conference` | string | query | Optional conference filter | Any valid conference name |
| `offenseConference` | string | query | Optional offensive team conference filter | Any valid conference name |
| `defenseConference` | string | query | Optional defensive team conference filter | Any valid conference name |
| `classification` | string | query | Optional division classification filter | `fbs`, `fcs`, `ii`, `iii` |

## Parameter Details

### Year Parameter
- **Required:** Yes
- **Type:** Integer (32-bit)
- **Description:** Specifies the year for which to retrieve drive data
- **Example:** `2024`

### Season Type Parameter
- **Required:** No
- **Type:** String
- **Description:** Filters drives by season type
- **Available Values:**
  - `regular` - Regular season games
  - `postseason` - Postseason/playoff games
  - `both` - Both regular and postseason games
  - `allstar` - All-star games
  - `spring_regular` - Spring regular season games
  - `spring_postseason` - Spring postseason games
- **Default:** All season types if not specified

### Week Parameter
- **Required:** No
- **Type:** Integer (32-bit)
- **Description:** Filters drives by specific week number
- **Example:** `1` for Week 1

### Team Filters
- **team:** General team filter (either offense or defense)
- **offense:** Specific offensive team filter
- **defense:** Specific defensive team filter
- **Type:** String
- **Description:** Filters drives by team participation
- **Example:** `Alabama`, `Ohio State`

### Conference Filters
- **conference:** General conference filter
- **offenseConference:** Offensive team's conference filter
- **defenseConference:** Defensive team's conference filter
- **Type:** String
- **Description:** Filters drives by conference affiliation
- **Example:** `SEC`, `Big Ten`, `ACC`

### Classification Parameter
- **Required:** No
- **Type:** String
- **Description:** Filters drives by division classification
- **Available Values:**
  - `fbs` - Football Bowl Subdivision (Division I FBS)
  - `fcs` - Football Championship Subdivision (Division I FCS)
  - `ii` - Division II
  - `iii` - Division III

## Response Format

### Success Response
- **HTTP Status:** 200 OK
- **Content-Type:** application/json
- **Description:** Returns an array of drive objects containing historical drive data

### Response Structure
The API returns a JSON array containing drive objects. Each drive object includes detailed information about the drive such as:
- Drive identification information
- Team information (offense/defense)
- Drive statistics (plays, yards, time)
- Drive outcome information
- Game context information

## Example Requests

### Basic Request (Required Parameters Only)
```
GET /drives?year=2024
```

### Filtered Request (Multiple Parameters)
```
GET /drives?year=2024&seasonType=regular&week=1&team=Alabama&classification=fbs
```

### Conference-Specific Request
```
GET /drives?year=2024&seasonType=regular&conference=SEC
```

### Offense vs Defense Specific Request
```
GET /drives?year=2024&offense=Alabama&defenseConference=Big%20Ten
```

## Usage Notes

### Parameter Combination Guidelines
1. **Year is always required** - No drives data will be returned without specifying a year
2. **Multiple filters can be combined** - Use multiple parameters to narrow down results
3. **URL encoding required** - Ensure proper URL encoding for team/conference names with spaces
4. **Case sensitivity** - Parameter values may be case-sensitive; use exact names as provided by the API

### Common Use Cases
1. **Season Overview:** Get all drives for a specific year and season type
2. **Team Analysis:** Filter by specific teams (offense/defense) to analyze team performance
3. **Conference Analysis:** Use conference filters to compare conference-level drive statistics
4. **Weekly Analysis:** Combine year, season type, and week filters for specific game weeks
5. **Division Comparison:** Use classification filter to analyze drives within specific divisions

### Performance Considerations
- **Large datasets:** Requests without filters may return large amounts of data
- **Recommended filtering:** Use appropriate filters to limit result set size
- **Rate limiting:** Follow API rate limiting guidelines for multiple requests

## Validation Requirements

Based on the API specification, the following validation should be implemented:

### Required Validations
1. **Year parameter validation:**
   - Must be present in all requests
   - Must be a valid integer
   - Should be within reasonable range (e.g., 1869-current year)

### Optional Parameter Validations
1. **Season type validation:**
   - Must be one of the allowed values if provided
   - Enum validation: `[regular, postseason, both, allstar, spring_regular, spring_postseason]`

2. **Classification validation:**
   - Must be one of the allowed values if provided
   - Enum validation: `[fbs, fcs, ii, iii]`

3. **Numeric parameter validation:**
   - Week must be a positive integer if provided
   - Year must be a valid integer in acceptable range

4. **String parameter validation:**
   - Team, conference names should be non-empty strings if provided
   - Proper URL encoding for names containing spaces

## Implementation Recommendations

### Request Model Structure
The drives API request model should include:
- **Required year field** with integer validation
- **Optional season type field** with enum validation
- **Optional week field** with integer validation
- **Optional team/conference fields** with string validation
- **Optional classification field** with enum validation

### Validation Logic
Implement validation similar to the games API pattern:
1. **Field aliases** for parameter name conversion (camelCase ↔ snake_case)
2. **Enum validation** for seasonType and classification
3. **Custom validators** for year range and parameter combinations
4. **Comprehensive error handling** for invalid parameter combinations

### Testing Requirements
Comprehensive test coverage should include:
1. **Required parameter tests** (year validation)
2. **Optional parameter tests** (all combinations)
3. **Enum validation tests** (valid/invalid season types and classifications)
4. **Edge case tests** (boundary years, invalid combinations)
5. **Integration tests** with actual API responses

This specification provides the foundation for implementing robust validation and request handling for the drives API endpoint, ensuring compatibility with the official College Football Data API.
