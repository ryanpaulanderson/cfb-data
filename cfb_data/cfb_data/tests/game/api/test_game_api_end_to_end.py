"""End-to-end validation flow tests for Game API with mocked responses."""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from cfb_data.game.api.game_api import CFBDGamesAPI


class TestGameAPIEndToEndValidation:
    """Test complete validation flow from public API to mocked HTTP responses."""

    @pytest.fixture
    def game_api(self) -> CFBDGamesAPI:
        """Create CFBDGamesAPI instance for testing.

        :return: CFBDGamesAPI instance
        :rtype: CFBDGamesAPI
        """
        return CFBDGamesAPI(api_key="test_api_key")

    @pytest.fixture
    def mock_games_response(self) -> Dict[str, Any]:
        """Mock response data for games endpoint.

        :return: Mock games response data
        :rtype: Dict[str, Any]
        """
        return [
            {
                "id": 401310890,
                "season": 2021,
                "week": 1,
                "season_type": "regular",
                "home_team": "Alabama",
                "away_team": "Miami",
                "home_points": 44,
                "away_points": 13,
            }
        ]

    @pytest.fixture
    def mock_team_stats_response(self) -> Dict[str, Any]:
        """Mock response data for team game stats endpoint.

        :return: Mock team stats response data
        :rtype: Dict[str, Any]
        """
        return [
            {
                "game_id": 401310890,
                "team": "Alabama",
                "conference": "SEC",
                "total_yards": 450,
                "passing_yards": 280,
                "rushing_yards": 170,
            }
        ]

    @pytest.mark.asyncio
    async def test_get_games_end_to_end_with_year(
        self, game_api: CFBDGamesAPI, mock_games_response: Dict[str, Any]
    ) -> None:
        """Test end-to-end get_games with year parameter through complete pipeline.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_games_response: Mock response data
        :type mock_games_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_games_response

            # Test valid request
            result = await game_api._get_games({"year": 2021})

            # Verify request was made with correct parameters
            mock_request.assert_called_once_with("/games", {"year": 2021})

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["id"] == 401310890

    @pytest.mark.asyncio
    async def test_get_games_end_to_end_with_id(
        self, game_api: CFBDGamesAPI, mock_games_response: Dict[str, Any]
    ) -> None:
        """Test end-to-end get_games with id parameter through complete pipeline.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_games_response: Mock response data
        :type mock_games_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_games_response

            # Test valid request with ID
            result = await game_api._get_games({"id": 401310890})

            # Verify request was made with correct parameters
            mock_request.assert_called_once_with("/games", {"id": 401310890})

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_games_end_to_end_validation_failure(
        self, game_api: CFBDGamesAPI
    ) -> None:
        """Test that validation errors are raised before HTTP request.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            # Test invalid request (no year or id)
            with pytest.raises(ValidationError) as exc_info:
                await game_api._get_games({})

            # Verify HTTP request was never made due to validation failure
            mock_request.assert_not_called()

            # Verify error message contains expected validation info
            error_str = str(exc_info.value)
            assert "year is required when id is not specified" in error_str

    @pytest.mark.asyncio
    async def test_get_team_game_stats_end_to_end_with_year_and_team(
        self, game_api: CFBDGamesAPI, mock_team_stats_response: Dict[str, Any]
    ) -> None:
        """Test end-to-end get_team_game_stats with year and team parameters.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_team_stats_response: Mock response data
        :type mock_team_stats_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_team_stats_response

            # Test valid request
            result = await game_api._get_team_game_stats(
                {"year": 2021, "team": "Alabama"}
            )

            # Verify request was made with correct parameters
            mock_request.assert_called_once_with(
                "/games/teams", {"year": 2021, "team": "Alabama"}
            )

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["team"] == "Alabama"

    @pytest.mark.asyncio
    async def test_get_team_game_stats_end_to_end_with_game_id(
        self, game_api: CFBDGamesAPI, mock_team_stats_response: Dict[str, Any]
    ) -> None:
        """Test end-to-end get_team_game_stats with game_id parameter.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_team_stats_response: Mock response data
        :type mock_team_stats_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_team_stats_response

            # Test valid request with game_id (bypasses other validation)
            result = await game_api._get_team_game_stats({"game_id": 401310890})

            # Verify request was made with correct parameters
            mock_request.assert_called_once_with("/games/teams", {"gameId": 401310890})

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_team_game_stats_end_to_end_validation_failure(
        self, game_api: CFBDGamesAPI
    ) -> None:
        """Test that complex validation errors are raised before HTTP request.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            # Test invalid request (year without additional filters)
            with pytest.raises(ValidationError) as exc_info:
                await game_api._get_team_game_stats({"year": 2021})

            # Verify HTTP request was never made due to validation failure
            mock_request.assert_not_called()

            # Verify error message contains expected validation info
            error_str = str(exc_info.value)
            assert (
                "At least one of week, team, or conference is required when game_id is not specified"
                in error_str
            )

    @pytest.mark.asyncio
    async def test_field_alias_handling_end_to_end(
        self, game_api: CFBDGamesAPI, mock_team_stats_response: Dict[str, Any]
    ) -> None:
        """Test that field aliases are correctly handled in end-to-end flow.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_team_stats_response: Mock response data
        :type mock_team_stats_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_team_stats_response

            # Test with snake_case parameters that should be converted to camelCase
            result = await game_api._get_team_game_stats(
                {"game_id": 401310890, "season_type": "regular"}
            )

            # Verify request was made with camelCase field names
            expected_params = {"gameId": 401310890, "seasonType": "regular"}
            mock_request.assert_called_once_with("/games/teams", expected_params)

            # Verify result structure
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_enum_validation_end_to_end(
        self, game_api: CFBDGamesAPI, mock_team_stats_response: Dict[str, Any]
    ) -> None:
        """Test that enum validation works correctly in end-to-end flow.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_team_stats_response: Mock response data
        :type mock_team_stats_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_team_stats_response

            # Test with valid enum values
            result = await game_api._get_team_game_stats(
                {
                    "year": 2021,
                    "team": "Alabama",
                    "season_type": "postseason",
                    "classification": "fbs",
                }
            )

            # Verify request was made with proper enum string conversion
            expected_params = {
                "year": 2021,
                "team": "Alabama",
                "seasonType": "postseason",
                "classification": "fbs",
            }
            mock_request.assert_called_once_with("/games/teams", expected_params)

            # Verify result structure
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_invalid_enum_validation_end_to_end(
        self, game_api: CFBDGamesAPI
    ) -> None:
        """Test that invalid enum values are caught before HTTP request.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            # Test with invalid season_type enum
            with pytest.raises(ValidationError) as exc_info:
                await game_api._get_team_game_stats(
                    {"year": 2021, "team": "Alabama", "season_type": "invalid_season"}
                )

            # Verify HTTP request was never made due to validation failure
            mock_request.assert_not_called()

            # Verify error message contains enum validation info
            error_str = str(exc_info.value)
            assert "season_type" in error_str

    @pytest.mark.asyncio
    async def test_parameter_combination_validation_end_to_end(
        self, game_api: CFBDGamesAPI, mock_games_response: Dict[str, Any]
    ) -> None:
        """Test parameter combination validation in end-to-end flow.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        :param mock_games_response: Mock response data
        :type mock_games_response: Dict[str, Any]
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_games_response

            # Test with both year and id (should work - validation allows both)
            result = await game_api._get_games({"year": 2021, "id": 401310890})

            # Verify request was made with both parameters
            expected_params = {"year": 2021, "id": 401310890}
            mock_request.assert_called_once_with("/games", expected_params)

            # Verify result structure
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_validation_error_propagation_end_to_end(
        self, game_api: CFBDGamesAPI
    ) -> None:
        """Test that validation errors are properly propagated to the caller.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        """
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            # Test multiple validation scenarios and verify proper error propagation

            # Scenario 1: Games without year or id
            with pytest.raises(ValidationError) as exc_info:
                await game_api._get_games({"week": 1})  # Week without year or id

            mock_request.assert_not_called()
            assert "year is required when id is not specified" in str(exc_info.value)

            # Reset mock for next test
            mock_request.reset_mock()

            # Scenario 2: Team stats with invalid parameter combinations
            with pytest.raises(ValidationError) as exc_info:
                await game_api._get_team_game_stats({"week": 1})  # Week without year

            mock_request.assert_not_called()
            error_str = str(exc_info.value)
            assert "game_id" in error_str and "year" in error_str

    @pytest.mark.asyncio
    async def test_http_error_vs_validation_error_end_to_end(
        self, game_api: CFBDGamesAPI
    ) -> None:
        """Test distinction between validation errors and HTTP errors.

        :param game_api: CFBDGamesAPI instance
        :type game_api: CFBDGamesAPI
        """
        # Test 1: Validation error (should not reach HTTP layer)
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            with pytest.raises(ValidationError):
                await game_api._get_games({})  # Missing required parameters

            # Verify HTTP request was never attempted
            mock_request.assert_not_called()

        # Test 2: HTTP error (validation passes, but HTTP fails)
        with patch.object(
            game_api, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            # Configure mock to raise an HTTP-related exception
            mock_request.side_effect = Exception("HTTP Error")

            # This should pass validation but fail at HTTP level
            with pytest.raises(Exception, match="HTTP Error"):
                await game_api._get_games({"year": 2021})

            # Verify HTTP request was attempted (validation passed)
            mock_request.assert_called_once_with("/games", {"year": 2021})
