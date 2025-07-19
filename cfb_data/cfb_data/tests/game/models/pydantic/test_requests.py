"""Test request models with validation logic."""

import pytest
from pydantic import ValidationError

from cfb_data.base.validation.request_validators import Classification, SeasonType
from cfb_data.game.models.pydantic.requests import (
    GamesRequest,
    TeamGameStatsRequest,
    PlayerGameStatsRequest,
    GameWeatherRequest,
)


class TestGamesRequest:
    """Test GamesRequest model validation."""

    def test_valid_request_with_year(self) -> None:
        """Test valid request with year parameter."""
        request = GamesRequest(year=2023)
        assert request.year == 2023
        assert request.id is None

    def test_valid_request_with_id(self) -> None:
        """Test valid request with id parameter."""
        request = GamesRequest(id=12345)
        assert request.id == 12345
        assert request.year is None

    def test_valid_request_with_both_year_and_id(self) -> None:
        """Test valid request with both year and id parameters."""
        request = GamesRequest(year=2023, id=12345)
        assert request.year == 2023
        assert request.id == 12345

    def test_valid_request_with_all_parameters(self) -> None:
        """Test valid request with all optional parameters."""
        request = GamesRequest(
            year=2023,
            week=1,
            season_type=SeasonType.regular,
            team="Alabama",
            home="Auburn",
            away="Georgia",
            conference="SEC",
            classification=Classification.fbs,
        )
        assert request.year == 2023
        assert request.week == 1
        assert request.season_type == SeasonType.regular
        assert request.team == "Alabama"
        assert request.home == "Auburn"
        assert request.away == "Georgia"
        assert request.conference == "SEC"
        assert request.classification == Classification.fbs

    def test_invalid_request_no_year_no_id(self) -> None:
        """Test that validation fails when neither year nor id is provided."""
        with pytest.raises(ValidationError) as exc_info:
            GamesRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when id is not specified" in errors[0]["msg"]

    def test_season_type_enum_validation(self) -> None:
        """Test season_type field accepts valid enum values."""
        valid_season_types = [
            SeasonType.regular,
            SeasonType.postseason,
            SeasonType.both,
            SeasonType.allstar,
            SeasonType.spring_regular,
            SeasonType.spring_postseason,
        ]

        for season_type in valid_season_types:
            request = GamesRequest(year=2023, season_type=season_type)
            assert request.season_type == season_type

    def test_season_type_string_conversion(self) -> None:
        """Test season_type field accepts string values and converts to enum."""
        request = GamesRequest(year=2023, season_type="regular")
        assert request.season_type == SeasonType.regular
        assert isinstance(request.season_type, SeasonType)

    def test_invalid_season_type(self) -> None:
        """Test that invalid season_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GamesRequest(year=2023, season_type="invalid_season")

        errors = exc_info.value.errors()
        # Check that the error is related to the season_type field and enum validation
        assert any(error["loc"] == ("season_type",) for error in errors)
        assert any("invalid_season" in str(error["input"]) for error in errors)

    def test_classification_enum_validation(self) -> None:
        """Test classification field accepts valid enum values."""
        valid_classifications = [
            Classification.fbs,
            Classification.fcs,
            Classification.ii,
            Classification.iii,
        ]

        for classification in valid_classifications:
            request = GamesRequest(year=2023, classification=classification)
            assert request.classification == classification

    def test_classification_string_conversion(self) -> None:
        """Test classification field accepts string values and converts to enum."""
        request = GamesRequest(year=2023, classification="fbs")
        assert request.classification == Classification.fbs
        assert isinstance(request.classification, Classification)

    def test_invalid_classification(self) -> None:
        """Test that invalid classification raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GamesRequest(year=2023, classification="invalid_division")

        errors = exc_info.value.errors()
        # Check that the error is related to the classification field and enum validation
        assert any(error["loc"] == ("classification",) for error in errors)
        assert any("invalid_division" in str(error["input"]) for error in errors)

    def test_field_aliases(self) -> None:
        """Test that camelCase field aliases work correctly."""
        # Test with camelCase input (simulating API request)
        data = {
            "year": 2023,
            "seasonType": "regular",  # camelCase alias
        }
        request = GamesRequest.model_validate(data)
        assert request.season_type == SeasonType.regular

    def test_model_dump_with_aliases(self) -> None:
        """Test that model dumps with field aliases."""
        request = GamesRequest(year=2023, season_type=SeasonType.regular)
        dumped = request.model_dump(by_alias=True)
        assert "seasonType" in dumped
        assert dumped["seasonType"] == "regular"


class TestTeamGameStatsRequest:
    """Test TeamGameStatsRequest model validation."""

    def test_valid_request_with_id(self) -> None:
        """Test valid request with id bypasses other validation."""
        request = TeamGameStatsRequest(id=12345)
        assert request.id == 12345
        assert request.year is None

    def test_valid_request_with_year_and_week(self) -> None:
        """Test valid request with year and week parameters."""
        request = TeamGameStatsRequest(year=2023, week=1)
        assert request.year == 2023
        assert request.week == 1

    def test_valid_request_with_year_and_team(self) -> None:
        """Test valid request with year and team parameters."""
        request = TeamGameStatsRequest(year=2023, team="Alabama")
        assert request.year == 2023
        assert request.team == "Alabama"

    def test_valid_request_with_year_and_conference(self) -> None:
        """Test valid request with year and conference parameters."""
        request = TeamGameStatsRequest(year=2023, conference="SEC")
        assert request.year == 2023
        assert request.conference == "SEC"

    def test_valid_request_with_all_filters(self) -> None:
        """Test valid request with year and all filter parameters."""
        request = TeamGameStatsRequest(
            year=2023,
            week=1,
            team="Alabama",
            conference="SEC",
            season_type=SeasonType.regular,
            classification=Classification.fbs,
        )
        assert request.year == 2023
        assert request.week == 1
        assert request.team == "Alabama"
        assert request.conference == "SEC"
        assert request.season_type == SeasonType.regular
        assert request.classification == Classification.fbs

    def test_invalid_request_no_game_id_no_year(self) -> None:
        """Test that validation fails when no game_id and no year."""
        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when id is not specified" in errors[0]["msg"]

    def test_invalid_request_year_without_filters(self) -> None:
        """Test that validation fails when year provided but no filters."""
        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(year=2023)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert (
            "At least one of week, team, or conference is required" in errors[0]["msg"]
        )

    def test_id_overrides_other_validation(self) -> None:
        """Test that providing id bypasses year and filter validation."""
        # This should be valid even though year is missing and no filters
        request = TeamGameStatsRequest(id=12345)
        assert request.id == 12345

    def test_season_type_enum_validation(self) -> None:
        """Test season_type field accepts valid enum values."""
        request = TeamGameStatsRequest(
            year=2023, week=1, season_type=SeasonType.postseason
        )
        assert request.season_type == SeasonType.postseason

    def test_classification_enum_validation(self) -> None:
        """Test classification field accepts valid enum values."""
        request = TeamGameStatsRequest(
            year=2023, team="Alabama", classification=Classification.fcs
        )
        assert request.classification == Classification.fcs

    def test_field_aliases(self) -> None:
        """Test that camelCase field aliases work correctly."""
        # Test with camelCase input (simulating API request)
        data = {
            "year": 2023,
            "week": 1,  # Need at least one filter when year is provided
            "id": 12345,  # Use 'id' for TeamGameStatsRequest API compliance
            "seasonType": "postseason",  # camelCase alias
        }
        request = TeamGameStatsRequest.model_validate(data)
        assert request.id == 12345
        assert request.season_type == SeasonType.postseason

    def test_model_dump_with_aliases(self) -> None:
        """Test that model dumps with field aliases."""
        request = TeamGameStatsRequest(
            year=2023,
            week=1,
            season_type=SeasonType.regular,
            id=12345,
        )
        dumped = request.model_dump(by_alias=True)
        assert "id" in dumped
        assert "seasonType" in dumped
        assert dumped["id"] == 12345
        assert dumped["seasonType"] == "regular"


class TestRequestModelsIntegration:
    """Integration tests for request models."""

    def test_games_request_edge_cases(self) -> None:
        """Test edge cases for GamesRequest."""
        # Test with zero values
        request = GamesRequest(year=2023, week=0)
        assert request.week == 0

        # Test with empty string values
        request = GamesRequest(year=2023, team="")
        assert request.team == ""

    def test_team_stats_request_edge_cases(self) -> None:
        """Test edge cases for TeamGameStatsRequest."""
        # Test with zero week (should count as valid filter)
        request = TeamGameStatsRequest(year=2023, week=0)
        assert request.week == 0

        # Test with empty string team (should count as valid filter)
        request = TeamGameStatsRequest(year=2023, team="")
        assert request.team == ""

    def test_model_validation_consistency(self) -> None:
        """Test that validation behavior is consistent between models."""
        # Both models should handle enum validation consistently
        games_request = GamesRequest(year=2023, season_type="regular")
        stats_request = TeamGameStatsRequest(year=2023, week=1, season_type="regular")

        assert games_request.season_type == stats_request.season_type
        assert isinstance(games_request.season_type, SeasonType)
        assert isinstance(stats_request.season_type, SeasonType)

    def test_error_message_quality(self) -> None:
        """Test that error messages are clear and helpful."""
        # Test GamesRequest error message
        with pytest.raises(ValidationError) as exc_info:
            GamesRequest(week=1)

        error_msg = str(exc_info.value)
        assert "year is required when id is not specified" in error_msg

        # Test TeamGameStatsRequest error messages
        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(week=1)

        error_msg = str(exc_info.value)
        assert "year is required when id is not specified" in error_msg

        with pytest.raises(ValidationError) as exc_info:
            TeamGameStatsRequest(year=2023)

        error_msg = str(exc_info.value)
        assert "At least one of week, team, or conference is required" in error_msg


class TestPlayerGameStatsRequest:
    """Test PlayerGameStatsRequest model validation."""

    def test_valid_request_with_id(self) -> None:
        """Test valid request with id bypasses other validation."""
        request = PlayerGameStatsRequest(id=12345)
        assert request.id == 12345
        assert request.year is None

    def test_valid_request_with_year_and_week(self) -> None:
        """Test valid request with year and week parameters."""
        request = PlayerGameStatsRequest(year=2023, week=1)
        assert request.year == 2023
        assert request.week == 1

    def test_valid_request_with_year_and_team(self) -> None:
        """Test valid request with year and team parameters."""
        request = PlayerGameStatsRequest(year=2023, team="Alabama")
        assert request.year == 2023
        assert request.team == "Alabama"

    def test_valid_request_with_year_and_conference(self) -> None:
        """Test valid request with year and conference parameters."""
        request = PlayerGameStatsRequest(year=2023, conference="SEC")
        assert request.year == 2023
        assert request.conference == "SEC"

    def test_valid_request_with_all_filters(self) -> None:
        """Test valid request with year and all filter parameters."""
        request = PlayerGameStatsRequest(
            year=2023,
            week=1,
            team="Alabama",
            conference="SEC",
            season_type=SeasonType.regular,
            category="passing",
            classification=Classification.fbs,
        )
        assert request.year == 2023
        assert request.week == 1
        assert request.team == "Alabama"
        assert request.conference == "SEC"
        assert request.season_type == SeasonType.regular
        assert request.category == "passing"
        assert request.classification == Classification.fbs

    def test_invalid_request_no_game_id_no_year(self) -> None:
        """Test that validation fails when no game_id and no year."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerGameStatsRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when id is not specified" in errors[0]["msg"]

    def test_invalid_request_year_without_filters(self) -> None:
        """Test that validation fails when year provided but no filters."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerGameStatsRequest(year=2023)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert (
            "At least one of week, team, or conference is required" in errors[0]["msg"]
        )

    def test_id_overrides_other_validation(self) -> None:
        """Test that providing id bypasses year and filter validation."""
        # This should be valid even though year is missing and no filters
        request = PlayerGameStatsRequest(id=12345)
        assert request.id == 12345

    def test_season_type_enum_validation(self) -> None:
        """Test season_type field accepts valid enum values."""
        request = PlayerGameStatsRequest(
            year=2023, week=1, season_type=SeasonType.postseason
        )
        assert request.season_type == SeasonType.postseason

    def test_field_aliases(self) -> None:
        """Test that camelCase field aliases work correctly."""
        # Test with camelCase input (simulating API request)
        data = {
            "year": 2023,
            "week": 1,  # Need at least one filter when year is provided
            "id": 12345,  # Use 'id' for TeamGameStatsRequest API compliance
            "seasonType": "postseason",  # camelCase alias
        }
        request = PlayerGameStatsRequest.model_validate(data)
        assert request.id == 12345
        assert request.season_type == SeasonType.postseason

    def test_model_dump_with_aliases(self) -> None:
        """Test that model dumps with field aliases."""
        request = PlayerGameStatsRequest(
            year=2023,
            week=1,
            season_type=SeasonType.regular,
            id=12345,
        )
        dumped = request.model_dump(by_alias=True)
        assert "id" in dumped
        assert "seasonType" in dumped
        assert dumped["id"] == 12345
        assert dumped["seasonType"] == "regular"

    def test_edge_cases(self) -> None:
        """Test edge cases for PlayerGameStatsRequest."""
        # Test with zero week (should count as valid filter)
        request = PlayerGameStatsRequest(year=2023, week=0)
        assert request.week == 0

        # Test with empty string team (should count as valid filter)
        request = PlayerGameStatsRequest(year=2023, team="")
        assert request.team == ""

        # Test with zero id
        request = PlayerGameStatsRequest(id=0)
        assert request.id == 0


class TestGameWeatherRequest:
    """Test GameWeatherRequest model validation."""

    def test_valid_request_with_game_id(self) -> None:
        """Test valid request with game_id bypasses other validation."""
        request = GameWeatherRequest(game_id=12345)
        assert request.game_id == 12345
        assert request.year is None

    def test_valid_request_with_year(self) -> None:
        """Test valid request with year parameter."""
        request = GameWeatherRequest(year=2023)
        assert request.year == 2023
        assert request.game_id is None

    def test_valid_request_with_all_parameters(self) -> None:
        """Test valid request with all optional parameters."""
        request = GameWeatherRequest(
            year=2023,
            week=1,
            season_type=SeasonType.regular,
            team="Alabama",
            conference="SEC",
            classification=Classification.fbs,
        )
        assert request.year == 2023
        assert request.week == 1
        assert request.season_type == SeasonType.regular
        assert request.team == "Alabama"
        assert request.conference == "SEC"
        assert request.classification == Classification.fbs

    def test_valid_request_with_both_game_id_and_year(self) -> None:
        """Test valid request with both game_id and year parameters."""
        request = GameWeatherRequest(game_id=12345, year=2023)
        assert request.game_id == 12345
        assert request.year == 2023

    def test_invalid_request_no_game_id_no_year(self) -> None:
        """Test that validation fails when neither game_id nor year is provided."""
        with pytest.raises(ValidationError) as exc_info:
            GameWeatherRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "year is required when game_id is not specified" in errors[0]["msg"]

    def test_game_id_overrides_year_requirement(self) -> None:
        """Test that providing game_id bypasses year requirement."""
        # This should be valid even though year is missing
        request = GameWeatherRequest(game_id=12345, week=1, team="Alabama")
        assert request.game_id == 12345
        assert request.week == 1
        assert request.team == "Alabama"

    def test_season_type_enum_validation(self) -> None:
        """Test season_type field accepts valid enum values."""
        request = GameWeatherRequest(year=2023, season_type=SeasonType.postseason)
        assert request.season_type == SeasonType.postseason

    def test_classification_enum_validation(self) -> None:
        """Test classification field accepts valid enum values."""
        request = GameWeatherRequest(year=2023, classification=Classification.fcs)
        assert request.classification == Classification.fcs

    def test_field_aliases(self) -> None:
        """Test that camelCase field aliases work correctly."""
        # Test with camelCase input (simulating API request)
        data = {
            "year": 2023,
            "week": 1,  # Need at least one filter when year is provided
            "gameId": 12345,  # Use 'gameId' for GameWeatherRequest API compliance
            "seasonType": "postseason",  # camelCase alias
        }
        request = GameWeatherRequest.model_validate(data)
        assert request.game_id == 12345
        assert request.season_type == SeasonType.postseason

    def test_model_dump_with_aliases(self) -> None:
        """Test that model dumps with field aliases."""
        request = GameWeatherRequest(
            year=2023,
            week=1,
            season_type=SeasonType.regular,
            game_id=12345,
        )
        dumped = request.model_dump(by_alias=True)
        assert "gameId" in dumped
        assert "seasonType" in dumped
        assert dumped["gameId"] == 12345
        assert dumped["seasonType"] == "regular"

    def test_edge_cases(self) -> None:
        """Test edge cases for GameWeatherRequest."""
        # Test with zero week
        request = GameWeatherRequest(year=2023, week=0)
        assert request.week == 0

        # Test with empty string team
        request = GameWeatherRequest(year=2023, team="")
        assert request.team == ""

        # Test year-only request (should be valid since no specific filters required)
        request = GameWeatherRequest(year=2023)
        assert request.year == 2023
