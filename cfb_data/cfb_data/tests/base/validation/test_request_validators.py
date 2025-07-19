"""Test request validation logic."""

import pytest
from pydantic import ValidationError

from cfb_data.base.validation.request_validators import (
    Classification,
    SeasonType,
    validate_at_least_one_of,
    validate_team_game_stats_logic,
    validate_year_or_id_required,
)


class TestSeasonTypeEnum:
    """Test SeasonType enumeration."""

    def test_valid_season_types(self) -> None:
        """Test that all valid season types are accepted."""
        valid_types = [
            "regular",
            "postseason",
            "both",
            "allstar",
            "spring_regular",
            "spring_postseason",
        ]

        for season_type in valid_types:
            enum_value = SeasonType(season_type)
            assert enum_value.value == season_type

    def test_invalid_season_type(self) -> None:
        """Test that invalid season type raises ValueError."""
        with pytest.raises(
            ValueError, match="'invalid_season' is not a valid SeasonType"
        ):
            SeasonType("invalid_season")

    def test_enum_string_behavior(self) -> None:
        """Test that enum behaves like string."""
        season_type = SeasonType.regular
        assert str(season_type) == "regular"
        assert season_type == "regular"
        assert season_type.value == "regular"


class TestClassificationEnum:
    """Test Classification enumeration."""

    def test_valid_classifications(self) -> None:
        """Test that all valid classifications are accepted."""
        valid_classifications = ["fbs", "fcs", "ii", "iii"]

        for classification in valid_classifications:
            enum_value = Classification(classification)
            assert enum_value.value == classification

    def test_invalid_classification(self) -> None:
        """Test that invalid classification raises ValueError."""
        with pytest.raises(
            ValueError, match="'invalid_div' is not a valid Classification"
        ):
            Classification("invalid_div")

    def test_enum_string_behavior(self) -> None:
        """Test that enum behaves like string."""
        classification = Classification.fbs
        assert str(classification) == "fbs"
        assert classification == "fbs"
        assert classification.value == "fbs"


class TestValidateYearOrIdRequired:
    """Test validate_year_or_id_required function."""

    def test_year_provided(self) -> None:
        """Test validation passes when year is provided."""
        # Should not raise any exception
        validate_year_or_id_required(2023, None, "id")

    def test_id_provided(self) -> None:
        """Test validation passes when id is provided."""
        # Should not raise any exception
        validate_year_or_id_required(None, 12345, "id")

    def test_both_provided(self) -> None:
        """Test validation passes when both year and id are provided."""
        # Should not raise any exception
        validate_year_or_id_required(2023, 12345, "id")

    def test_neither_provided(self) -> None:
        """Test validation fails when neither year nor id is provided."""
        with pytest.raises(
            ValueError, match="year is required when id is not specified"
        ):
            validate_year_or_id_required(None, None, "id")

    def test_custom_id_field_name(self) -> None:
        """Test validation with custom id field name."""
        with pytest.raises(
            ValueError, match="year is required when game_id is not specified"
        ):
            validate_year_or_id_required(None, None, "game_id")


class TestValidateAtLeastOneOf:
    """Test validate_at_least_one_of function."""

    def test_one_field_provided(self) -> None:
        """Test validation passes when one field is provided."""
        values = {"field1": "value1", "field2": None, "field3": None}
        fields = ["field1", "field2", "field3"]

        # Should not raise any exception
        validate_at_least_one_of(values, fields)

    def test_multiple_fields_provided(self) -> None:
        """Test validation passes when multiple fields are provided."""
        values = {"field1": "value1", "field2": "value2", "field3": None}
        fields = ["field1", "field2", "field3"]

        # Should not raise any exception
        validate_at_least_one_of(values, fields)

    def test_no_fields_provided(self) -> None:
        """Test validation fails when no fields are provided."""
        values = {"field1": None, "field2": None, "field3": None}
        fields = ["field1", "field2", "field3"]

        with pytest.raises(
            ValueError,
            match="At least one of the following fields is required: field1, field2, field3",
        ):
            validate_at_least_one_of(values, fields)

    def test_empty_string_counts_as_provided(self) -> None:
        """Test that empty string counts as a provided value."""
        values = {"field1": "", "field2": None, "field3": None}
        fields = ["field1", "field2", "field3"]

        # Should not raise any exception (empty string is truthy)
        validate_at_least_one_of(values, fields)

    def test_zero_counts_as_provided(self) -> None:
        """Test that zero counts as a provided value."""
        values = {"field1": 0, "field2": None, "field3": None}
        fields = ["field1", "field2", "field3"]

        # Should not raise any exception (0 is truthy for this validation)
        validate_at_least_one_of(values, fields)

    def test_custom_context_message(self) -> None:
        """Test validation with custom context message."""
        values = {"field1": None, "field2": None}
        fields = ["field1", "field2"]
        custom_message = "Custom validation message"

        with pytest.raises(
            ValueError, match="Custom validation message: field1, field2"
        ):
            validate_at_least_one_of(values, fields, custom_message)


class TestValidateTeamGameStatsLogic:
    """Test validate_team_game_stats_logic function."""

    def test_id_provided_no_other_validation(self) -> None:
        """Test that providing id bypasses all other validation."""
        # Should not raise any exception regardless of other parameters
        validate_team_game_stats_logic(None, None, None, None, 12345)

    def test_year_and_week_provided(self) -> None:
        """Test validation passes with year and week."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, 1, None, None, None)

    def test_year_and_team_provided(self) -> None:
        """Test validation passes with year and team."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, None, "Alabama", None, None)

    def test_year_and_conference_provided(self) -> None:
        """Test validation passes with year and conference."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, None, None, "SEC", None)

    def test_year_and_all_filters_provided(self) -> None:
        """Test validation passes with year and all filter types."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, 1, "Alabama", "SEC", None)

    def test_no_id_no_year(self) -> None:
        """Test validation fails when id not provided and year missing."""
        with pytest.raises(
            ValueError, match="year is required when id is not specified"
        ):
            validate_team_game_stats_logic(None, 1, None, None, None)

    def test_year_but_no_filters(self) -> None:
        """Test validation fails when year provided but no week/team/conference."""
        with pytest.raises(
            ValueError,
            match="At least one of week, team, or conference is required when id is not specified",
        ):
            validate_team_game_stats_logic(2023, None, None, None, None)

    def test_year_but_all_filters_none(self) -> None:
        """Test validation fails when year provided but all filters are explicitly None."""
        with pytest.raises(
            ValueError,
            match="At least one of week, team, or conference is required when id is not specified",
        ):
            validate_team_game_stats_logic(2023, None, None, None, None)

    def test_year_with_empty_string_team(self) -> None:
        """Test validation passes when team is empty string (counts as provided)."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, None, "", None, None)

    def test_year_with_zero_week(self) -> None:
        """Test validation passes when week is zero (counts as provided)."""
        # Should not raise any exception
        validate_team_game_stats_logic(2023, 0, None, None, None)


class TestValidationIntegration:
    """Integration tests for validation functions with edge cases."""

    def test_complex_team_stats_scenarios(self) -> None:
        """Test complex scenarios for team game stats validation."""
        # Scenario: Game ID with year and other filters (should pass)
        validate_team_game_stats_logic(2023, 1, "Alabama", "SEC", 12345)

        # Scenario: Year with multiple filter types (should pass)
        validate_team_game_stats_logic(2023, 1, "Alabama", None, None)
        validate_team_game_stats_logic(2023, None, "Alabama", "SEC", None)
        validate_team_game_stats_logic(2023, 1, None, "SEC", None)

    def test_boundary_values(self) -> None:
        """Test boundary values for validation functions."""
        # Test with year boundary values
        validate_year_or_id_required(1869, None, "id")  # Minimum valid year
        validate_year_or_id_required(2030, None, "id")  # Maximum valid year

        # Test with week boundary values
        validate_team_game_stats_logic(2023, 0, None, None, None)  # Minimum week
        validate_team_game_stats_logic(2023, 20, None, None, None)  # Maximum week

    def test_error_message_consistency(self) -> None:
        """Test that error messages are consistent and informative."""
        # Test year_or_id error message format
        with pytest.raises(ValueError) as exc_info:
            validate_year_or_id_required(None, None, "id")
        assert "year is required when id is not specified" in str(exc_info.value)

        # Test team_stats year error message format
        with pytest.raises(ValueError) as exc_info:
            validate_team_game_stats_logic(None, 1, None, None, None)
        assert "year is required when id is not specified" in str(exc_info.value)

        # Test team_stats filter error message format
        with pytest.raises(ValueError) as exc_info:
            validate_team_game_stats_logic(2023, None, None, None, None)
        assert "At least one of week, team, or conference is required" in str(
            exc_info.value
        )
