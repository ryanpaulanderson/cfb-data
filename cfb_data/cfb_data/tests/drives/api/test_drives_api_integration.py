"""Integration tests for drives API validation with DrivesRequest model."""

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
from cfb_data.drives.api.drives_api import CFBDDrivesAPI
from cfb_data.drives.models.pydantic.requests import DrivesRequest


class DrivesAPIForTesting(CFBDDrivesAPI):
    """Test API subclass to expose protected methods without real HTTP calls."""

    def __init__(self) -> None:
        """Initialize test API with fake credentials."""
        super().__init__(api_key="test_key")


def run(coro):
    """Execute ``coro`` synchronously.

    :param coro: Coroutine to execute.
    :type coro: Coroutine
    :return: Result of the coroutine.
    :rtype: Any
    """
    return asyncio.run(coro)


class TestDrivesRequestIntegration:
    """Test DrivesRequest model integration with API layer."""

    def test_valid_drives_request_with_year_only(self) -> None:
        """Test API accepts valid DrivesRequest with year only."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        request = DrivesRequest(year=2023)
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]
        assert params == {"year": 2023}

    def test_valid_drives_request_with_all_parameters(self) -> None:
        """Test API accepts valid DrivesRequest with all parameters."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])

        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            week=1,
            team="Alabama",
            offense="Auburn",
            defense="Georgia",
            conference="SEC",
            offense_conference="SEC",
            defense_conference="ACC",
            classification=Classification.fbs,
        )
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}, {"id": "2"}]

        # Verify all parameters are correctly formatted with aliases
        expected_params = {
            "year": 2023,
            "seasonType": "regular",
            "week": 1,
            "team": "Alabama",
            "offense": "Auburn",
            "defense": "Georgia",
            "conference": "SEC",
            "offenseConference": "SEC",
            "defenseConference": "ACC",
            "classification": "fbs",
        }
        assert params == expected_params

    def test_drives_request_with_team_filters(self) -> None:
        """Test API handles team filtering parameters correctly."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        request = DrivesRequest(
            year=2023,
            offense="Alabama",
            defense="Auburn",
        )
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]

        expected_params = {
            "year": 2023,
            "offense": "Alabama",
            "defense": "Auburn",
        }
        assert params == expected_params

    def test_drives_request_with_conference_filters(self) -> None:
        """Test API handles conference filtering parameters correctly."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        request = DrivesRequest(
            year=2023,
            offense_conference="SEC",
            defense_conference="ACC",
        )
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]

        expected_params = {
            "year": 2023,
            "offenseConference": "SEC",
            "defenseConference": "ACC",
        }
        assert params == expected_params

    def test_invalid_drives_request_missing_year(self) -> None:
        """Test that missing year raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("year",) for error in errors)
        assert any("Field required" in error["msg"] for error in errors)

    def test_invalid_drives_request_bad_year(self) -> None:
        """Test that invalid year raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=1868)  # Before 1869

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("year",) for error in errors)
        assert any("1869" in error["msg"] for error in errors)

    def test_invalid_drives_request_bad_week(self) -> None:
        """Test that invalid week raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, week=0)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("week",) for error in errors)
        assert any("greater than 0" in error["msg"] for error in errors)

    def test_invalid_drives_request_bad_season_type(self) -> None:
        """Test that invalid season_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, season_type="invalid_season")

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("season_type",) for error in errors)
        assert any("invalid_season" in str(error["input"]) for error in errors)

    def test_invalid_drives_request_bad_classification(self) -> None:
        """Test that invalid classification raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, classification="invalid_division")

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("classification",) for error in errors)
        assert any("invalid_division" in str(error["input"]) for error in errors)

    def test_drives_request_enum_string_conversion(self) -> None:
        """Test that enum fields accept string values and convert properly."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        request = DrivesRequest(
            year=2023,
            season_type="regular",  # String should convert to enum
            classification="fbs",  # String should convert to enum
        )
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]

        # Verify enum conversion worked and output is string
        expected_params = {
            "year": 2023,
            "seasonType": "regular",
            "classification": "fbs",
        }
        assert params == expected_params

    def test_drives_request_camelcase_input_validation(self) -> None:
        """Test that camelCase input (from API requests) validates correctly."""
        # Test with camelCase input data (simulating API request)
        data = {
            "year": 2023,
            "seasonType": "regular",
            "offenseConference": "SEC",
            "defenseConference": "ACC",
        }
        request = DrivesRequest.model_validate(data)

        assert request.year == 2023
        assert request.season_type == SeasonType.regular
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "ACC"

    def test_drives_request_excludes_none_values(self) -> None:
        """Test that API parameters exclude None values correctly."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        request = DrivesRequest(year=2023)  # Only year, all others should be None
        params = request.model_dump(by_alias=True, exclude_none=True)

        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]

        # Should only contain year, all None values excluded
        assert params == {"year": 2023}
        assert "seasonType" not in params
        assert "week" not in params
        assert "team" not in params
        assert "offense" not in params
        assert "defense" not in params
        assert "conference" not in params
        assert "offenseConference" not in params
        assert "defenseConference" not in params
        assert "classification" not in params


class TestDrivesAPIBackwardCompatibility:
    """Test that existing API behavior still works with new validation."""

    def test_backward_compatibility_with_dict_params(self) -> None:
        """Test that API still works with raw dict parameters for backward compatibility."""
        api = DrivesAPIForTesting()
        api._make_request = AsyncMock(return_value=[{"id": "1"}])

        # Old-style dict parameters should still work
        params = {"year": 2023}
        result = run(api._get_drives(params))

        api._make_request.assert_awaited_once_with("/drives", params)
        assert result == [{"id": "1"}]

    def test_year_validation_still_enforced(self) -> None:
        """Test that year validation is still enforced at API level."""
        api = DrivesAPIForTesting()

        # Missing year should still raise ValueError
        with pytest.raises(ValueError):
            run(api._get_drives({}))

        # Invalid year parameters should still raise ValueError
        with pytest.raises(ValueError):
            run(api._get_drives({"week": 1}))
