"""Integration tests for game API validation."""

import asyncio
import importlib
import types
from pathlib import Path
from unittest.mock import AsyncMock

# Provide a minimal aiohttp stub for import resolution
importlib.import_module("sys").path.insert(0, str(Path(__file__).resolve().parents[4]))

if importlib.util.find_spec("aiohttp") is None:
    aiohttp_stub = types.ModuleType("aiohttp")
    importlib.import_module("sys").modules["aiohttp"] = aiohttp_stub

import pytest
from pydantic import ValidationError

from cfb_data.base.validation.request_validators import Classification, SeasonType
from cfb_data.game.api.game_api import CFBDGamesAPI


class GameAPIForTesting(CFBDGamesAPI):
    """Test API subclass to expose protected methods without real HTTP calls."""

    def __init__(self) -> None:
        """Initialize test API with fake credentials."""
        super().__init__(api_key="test_key")


def run(coro):
    """Execute coroutine synchronously for testing.

    :param coro: Coroutine to execute
    :type coro: Coroutine
    :return: Result of the coroutine
    :rtype: Any
    """
    return asyncio.run(coro)


class TestGetGamesIntegration:
    """Integration tests for _get_games method with Pydantic validation."""

    def test_valid_request_with_year_only(self) -> None:
        """Test that valid request with only year parameter works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1, "season": 2023}])

        params = {"year": 2023}
        result = run(api._get_games(params))

        # Verify _make_request was called with validated parameters
        api._make_request.assert_awaited_once_with("/games", {"year": 2023})
        assert result == [{"id": 1, "season": 2023}]

    def test_valid_request_with_id_only(self) -> None:
        """Test that valid request with only id parameter works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 12345, "season": 2023}])

        params = {"id": 12345}
        result = run(api._get_games(params))

        # Verify _make_request was called with validated parameters
        api._make_request.assert_awaited_once_with("/games", {"id": 12345})
        assert result == [{"id": 12345, "season": 2023}]

    def test_valid_request_with_all_parameters(self) -> None:
        """Test that valid request with all parameters works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {
            "year": 2023,
            "week": 1,
            "season_type": "regular",
            "team": "Alabama",
            "home": "Auburn",
            "away": "Georgia",
            "conference": "SEC",
            "classification": "fbs",
        }
        result = run(api._get_games(params))

        # Verify all parameters were passed through
        expected_params = {
            "year": 2023,
            "week": 1,
            "seasonType": "regular",  # Note: field alias conversion
            "team": "Alabama",
            "home": "Auburn",
            "away": "Georgia",
            "conference": "SEC",
            "classification": "fbs",
        }
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_invalid_request_no_year_no_id(self) -> None:
        """Test that missing year and id raises ValidationError."""
        api = GameAPIForTesting()

        params = {"week": 1, "team": "Alabama"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_games(params))

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when id is not specified" in errors[0]["msg"]

    def test_invalid_season_type_raises_validation_error(self) -> None:
        """Test that invalid season_type raises ValidationError."""
        api = GameAPIForTesting()

        params = {"year": 2023, "season_type": "invalid_season"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_games(params))

        errors = exc_info.value.errors()
        # Check that validation error occurred on season_type field
        assert any(error["loc"] == ("season_type",) for error in errors)

    def test_invalid_classification_raises_validation_error(self) -> None:
        """Test that invalid classification raises ValidationError."""
        api = GameAPIForTesting()

        params = {"year": 2023, "classification": "invalid_division"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_games(params))

        errors = exc_info.value.errors()
        # Check that validation error occurred on classification field
        assert any(error["loc"] == ("classification",) for error in errors)

    def test_enum_string_conversion(self) -> None:
        """Test that string season_type and classification are converted to enums."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {
            "year": 2023,
            "season_type": "postseason",  # String should convert to enum
            "classification": "fcs",  # String should convert to enum
        }
        result = run(api._get_games(params))

        # Verify conversion happened and field aliases were applied
        expected_params = {
            "year": 2023,
            "seasonType": "postseason",  # Field alias
            "classification": "fcs",
        }
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_field_alias_conversion(self) -> None:
        """Test that snake_case fields are converted to camelCase for API."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {"year": 2023, "season_type": "regular"}  # snake_case input
        result = run(api._get_games(params))

        # Verify field alias conversion to camelCase
        expected_params = {"year": 2023, "seasonType": "regular"}  # camelCase output
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_camelcase_input_handling(self) -> None:
        """Test that camelCase input parameters are handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        # Input using camelCase (simulating API request format)
        params = {"year": 2023, "seasonType": "regular"}  # camelCase input
        result = run(api._get_games(params))

        # Should still output camelCase for API
        expected_params = {"year": 2023, "seasonType": "regular"}
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_none_values_excluded_from_output(self) -> None:
        """Test that None values are excluded from the API call."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {
            "year": 2023,
            "week": None,  # Should be excluded
            "team": "Alabama",  # Should be included
            "conference": None,  # Should be excluded
        }
        result = run(api._get_games(params))

        # Only non-None values should be passed to API
        expected_params = {"year": 2023, "team": "Alabama"}
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_both_year_and_id_provided(self) -> None:
        """Test that providing both year and id is valid."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 12345}])

        params = {"year": 2023, "id": 12345}
        result = run(api._get_games(params))

        # Both parameters should be passed through
        expected_params = {"year": 2023, "id": 12345}
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_validation_happens_before_api_call(self) -> None:
        """Test that validation errors prevent API calls."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        # Invalid parameters that should fail validation
        params = {"week": 1}  # Missing year and id

        with pytest.raises(ValidationError):
            run(api._get_games(params))

        # _make_request should never be called due to validation failure
        api._make_request.assert_not_awaited()

    def test_edge_case_zero_values(self) -> None:
        """Test that zero values are handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {"year": 2023, "week": 0}  # Zero should be valid and included
        result = run(api._get_games(params))

        expected_params = {"year": 2023, "week": 0}
        api._make_request.assert_awaited_once_with("/games", expected_params)

    def test_empty_string_values(self) -> None:
        """Test that empty string values are handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        params = {"year": 2023, "team": ""}  # Empty string should be valid and included
        result = run(api._get_games(params))

        expected_params = {"year": 2023, "team": ""}
        api._make_request.assert_awaited_once_with("/games", expected_params)


class TestGetGamesValidationErrorMessages:
    """Test validation error messages are clear and helpful."""

    def test_missing_year_error_message_quality(self) -> None:
        """Test that error message for missing year is clear."""
        api = GameAPIForTesting()

        params = {"week": 1}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_games(params))

        error_message = str(exc_info.value)
        assert "year is required when id is not specified" in error_message

    def test_invalid_enum_error_message_quality(self) -> None:
        """Test that error message for invalid enum is clear."""
        api = GameAPIForTesting()

        params = {"year": 2023, "season_type": "invalid_type"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_games(params))

        errors = exc_info.value.errors()
        # Should indicate which field had the problem
        assert any(error["loc"] == ("season_type",) for error in errors)
        # Should mention the invalid input
        assert any("invalid_type" in str(error["input"]) for error in errors)


class TestGetGamesEnumValidation:
    """Test enum validation and conversion in API context."""

    def test_all_valid_season_types(self) -> None:
        """Test that all valid season types work in API context."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        valid_season_types = [
            "regular",
            "postseason",
            "both",
            "allstar",
            "spring_regular",
            "spring_postseason",
        ]

        for season_type in valid_season_types:
            params = {"year": 2023, "season_type": season_type}
            result = run(api._get_games(params))

            expected_params = {"year": 2023, "seasonType": season_type}
            api._make_request.assert_awaited_with("/games", expected_params)

    def test_all_valid_classifications(self) -> None:
        """Test that all valid classifications work in API context."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": 1}])

        valid_classifications = ["fbs", "fcs", "ii", "iii"]

        for classification in valid_classifications:
            params = {"year": 2023, "classification": classification}
            result = run(api._get_games(params))

            expected_params = {"year": 2023, "classification": classification}
            api._make_request.assert_awaited_with("/games", expected_params)


class TestGetTeamGameStatsIntegration:
    """Integration tests for _get_team_game_stats method with complex conditional validation."""

    def test_valid_request_with_game_id_only(self) -> None:
        """Test that valid request with only game_id works (bypasses other validation)."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"gameId": 12345}])

        params = {"game_id": 12345}
        result = run(api._get_team_game_stats(params))

        # Verify _make_request was called with validated parameters and field alias
        expected_params = {"gameId": 12345}  # Note camelCase alias
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)
        assert result == [{"gameId": 12345}]

    def test_valid_request_with_year_and_week(self) -> None:
        """Test that valid request with year and week works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"team": "Alabama", "week": 1}])

        params = {"year": 2023, "week": 1}
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "week": 1}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_valid_request_with_year_and_team(self) -> None:
        """Test that valid request with year and team works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"team": "Alabama"}])

        params = {"year": 2023, "team": "Alabama"}
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "team": "Alabama"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_valid_request_with_year_and_conference(self) -> None:
        """Test that valid request with year and conference works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"conference": "SEC"}])

        params = {"year": 2023, "conference": "SEC"}
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "conference": "SEC"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_valid_request_with_year_and_all_filters(self) -> None:
        """Test that valid request with year and all filter types works."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {
            "year": 2023,
            "week": 1,
            "team": "Alabama",
            "conference": "SEC",
            "season_type": "regular",
            "classification": "fbs",
        }
        result = run(api._get_team_game_stats(params))

        # Field alias conversion should happen
        expected_params = {
            "year": 2023,
            "week": 1,
            "team": "Alabama",
            "conference": "SEC",
            "seasonType": "regular",  # camelCase alias
            "classification": "fbs",
        }
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_invalid_request_no_game_id_no_year(self) -> None:
        """Test that missing both game_id and year raises ValidationError."""
        api = GameAPIForTesting()

        params = {"week": 1, "team": "Alabama"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when game_id is not specified" in errors[0]["msg"]

    def test_invalid_request_year_without_filters(self) -> None:
        """Test that year without any filters raises ValidationError."""
        api = GameAPIForTesting()

        params = {"year": 2023}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert (
            "At least one of week, team, or conference is required" in errors[0]["msg"]
        )

    def test_game_id_overrides_all_other_validation(self) -> None:
        """Test that providing game_id bypasses year and filter requirements."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"gameId": 12345}])

        # This should be valid even though year is missing and no filters
        params = {"game_id": 12345}
        result = run(api._get_team_game_stats(params))

        expected_params = {"gameId": 12345}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_game_id_with_other_parameters(self) -> None:
        """Test that game_id can be combined with other parameters."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"gameId": 12345}])

        params = {
            "game_id": 12345,
            "year": 2023,  # Should be included even though not required
            "team": "Alabama",
        }
        result = run(api._get_team_game_stats(params))

        expected_params = {"gameId": 12345, "year": 2023, "team": "Alabama"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_validation_happens_before_api_call(self) -> None:
        """Test that validation errors prevent API calls."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        # Invalid parameters that should fail validation
        params = {"year": 2023}  # Missing filters

        with pytest.raises(ValidationError):
            run(api._get_team_game_stats(params))

        # _make_request should never be called due to validation failure
        api._make_request.assert_not_awaited()

    def test_field_alias_conversion_game_id(self) -> None:
        """Test that game_id is converted to gameId for API."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"gameId": 12345}])

        params = {"game_id": 12345}
        result = run(api._get_team_game_stats(params))

        # Verify field alias conversion
        expected_params = {"gameId": 12345}  # camelCase output
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_field_alias_conversion_season_type(self) -> None:
        """Test that season_type is converted to seasonType for API."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {
            "year": 2023,
            "week": 1,
            "season_type": "postseason",  # snake_case input
        }
        result = run(api._get_team_game_stats(params))

        # Verify field alias conversion
        expected_params = {
            "year": 2023,
            "week": 1,
            "seasonType": "postseason",  # camelCase output
        }
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_camelcase_input_handling(self) -> None:
        """Test that camelCase input parameters are handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        # Input using camelCase (simulating API request format)
        params = {
            "year": 2023,
            "gameId": 12345,  # camelCase input
            "seasonType": "regular",  # camelCase input
        }
        result = run(api._get_team_game_stats(params))

        # Should still output camelCase for API
        expected_params = {"year": 2023, "gameId": 12345, "seasonType": "regular"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_edge_case_zero_week(self) -> None:
        """Test that zero week value is handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {"year": 2023, "week": 0}  # Zero should be valid and count as a filter
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "week": 0}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_edge_case_empty_string_team(self) -> None:
        """Test that empty string team value is handled correctly."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {
            "year": 2023,
            "team": "",  # Empty string should be valid and count as a filter
        }
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "team": ""}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_enum_validation_season_type(self) -> None:
        """Test that season_type enum validation works in API context."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {
            "year": 2023,
            "week": 1,
            "season_type": "postseason",  # Valid enum value
        }
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "week": 1, "seasonType": "postseason"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_enum_validation_classification(self) -> None:
        """Test that classification enum validation works in API context."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        params = {
            "year": 2023,
            "team": "Alabama",
            "classification": "fcs",  # Valid enum value
        }
        result = run(api._get_team_game_stats(params))

        expected_params = {"year": 2023, "team": "Alabama", "classification": "fcs"}
        api._make_request.assert_awaited_once_with("/games/teams", expected_params)

    def test_invalid_season_type_raises_validation_error(self) -> None:
        """Test that invalid season_type raises ValidationError."""
        api = GameAPIForTesting()

        params = {"year": 2023, "week": 1, "season_type": "invalid_season"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        errors = exc_info.value.errors()
        # Check that validation error occurred on season_type field
        assert any(error["loc"] == ("season_type",) for error in errors)

    def test_invalid_classification_raises_validation_error(self) -> None:
        """Test that invalid classification raises ValidationError."""
        api = GameAPIForTesting()

        params = {"year": 2023, "team": "Alabama", "classification": "invalid_division"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        errors = exc_info.value.errors()
        # Check that validation error occurred on classification field
        assert any(error["loc"] == ("classification",) for error in errors)


class TestTeamGameStatsValidationErrorMessages:
    """Test validation error messages for team game stats are clear and helpful."""

    def test_missing_year_error_message_quality(self) -> None:
        """Test that error message for missing year is clear."""
        api = GameAPIForTesting()

        params = {"week": 1, "team": "Alabama"}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        error_message = str(exc_info.value)
        assert "year is required when game_id is not specified" in error_message

    def test_missing_filters_error_message_quality(self) -> None:
        """Test that error message for missing filters is clear."""
        api = GameAPIForTesting()

        params = {"year": 2023}

        with pytest.raises(ValidationError) as exc_info:
            run(api._get_team_game_stats(params))

        error_message = str(exc_info.value)
        assert "At least one of week, team, or conference is required" in error_message

    def test_complex_validation_logic_integration(self) -> None:
        """Test that complex validation logic works as expected."""
        api = GameAPIForTesting()

        # Test multiple invalid scenarios
        invalid_scenarios = [
            ({}, "Missing both game_id and year"),
            ({"week": 1}, "Missing year when no game_id"),
            ({"year": 2023}, "Missing filters when no game_id"),
            ({"team": "Alabama"}, "Missing year when no game_id"),
        ]

        for params, description in invalid_scenarios:
            with pytest.raises(
                ValidationError,
                match="year is required when game_id is not specified|At least one of week, team, or conference is required",
            ):
                run(api._get_team_game_stats(params))


class TestTeamGameStatsComplexScenarios:
    """Test complex real-world scenarios for team game stats validation."""

    def test_multiple_filter_combinations(self) -> None:
        """Test various valid combinations of filters."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        valid_combinations = [
            # Year + single filter
            {"year": 2023, "week": 1},
            {"year": 2023, "team": "Alabama"},
            {"year": 2023, "conference": "SEC"},
            # Year + multiple filters
            {"year": 2023, "week": 1, "team": "Alabama"},
            {"year": 2023, "week": 1, "conference": "SEC"},
            {"year": 2023, "team": "Alabama", "conference": "SEC"},
            {"year": 2023, "week": 1, "team": "Alabama", "conference": "SEC"},
            # Game ID scenarios (bypasses other requirements)
            {"game_id": 12345},
            {"game_id": 12345, "year": 2023},
            {"game_id": 12345, "week": 1},
        ]

        for params in valid_combinations:
            result = run(api._get_team_game_stats(params))
            # Should not raise any validation errors
            assert result == [{"stats": "data"}]

    def test_boundary_values_and_edge_cases(self) -> None:
        """Test boundary values for team game stats parameters."""
        api = GameAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"stats": "data"}])

        # Test edge cases that should be valid
        edge_cases = [
            {"year": 1869, "week": 0},  # Minimum year, zero week
            {"year": 2030, "week": 20},  # Maximum year, high week
            {"year": 2023, "team": ""},  # Empty string team
            {"year": 2023, "conference": ""},  # Empty string conference
        ]

        for params in edge_cases:
            result = run(api._get_team_game_stats(params))
            # Should not raise any validation errors
            assert result == [{"stats": "data"}]
