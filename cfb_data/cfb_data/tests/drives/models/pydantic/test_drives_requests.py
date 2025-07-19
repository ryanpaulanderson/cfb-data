"""Test request models with validation logic for drives endpoints."""

import pytest
from pydantic import ValidationError

from cfb_data.base.validation.request_validators import Classification, SeasonType
from cfb_data.drives.models.pydantic.requests import DrivesRequest


class TestDrivesRequest:
    """Test DrivesRequest model validation."""

    def test_valid_request_with_year_only(self) -> None:
        """Test valid request with only year parameter."""
        request = DrivesRequest(year=2023)
        assert request.year == 2023
        assert request.season_type is None
        assert request.week is None
        assert request.team is None
        assert request.offense is None
        assert request.defense is None
        assert request.conference is None
        assert request.offense_conference is None
        assert request.defense_conference is None
        assert request.classification is None

    def test_valid_request_with_all_parameters(self) -> None:
        """Test valid request with all optional parameters."""
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
        assert request.year == 2023
        assert request.season_type == SeasonType.regular
        assert request.week == 1
        assert request.team == "Alabama"
        assert request.offense == "Auburn"
        assert request.defense == "Georgia"
        assert request.conference == "SEC"
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "ACC"
        assert request.classification == Classification.fbs

    def test_valid_request_with_team_filters(self) -> None:
        """Test valid request with team filtering parameters."""
        request = DrivesRequest(
            year=2023,
            offense="Alabama",
            defense="Auburn",
        )
        assert request.year == 2023
        assert request.offense == "Alabama"
        assert request.defense == "Auburn"
        assert request.team is None

    def test_valid_request_with_conference_filters(self) -> None:
        """Test valid request with conference filtering parameters."""
        request = DrivesRequest(
            year=2023,
            offense_conference="SEC",
            defense_conference="ACC",
        )
        assert request.year == 2023
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "ACC"
        assert request.conference is None

    def test_invalid_request_no_year(self) -> None:
        """Test that validation fails when year is not provided."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(week=1, team="Alabama")

        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert any(error["loc"] == ("year",) for error in errors)
        assert any("Field required" in error["msg"] for error in errors)

    def test_invalid_year_too_early(self) -> None:
        """Test that validation fails for year before 1869."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=1868)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("year",) for error in errors)
        assert any("1869" in error["msg"] for error in errors)

    def test_invalid_year_future(self) -> None:
        """Test that validation fails for year too far in future."""
        future_year = 2030
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=future_year)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("year",) for error in errors)

    def test_invalid_week_zero(self) -> None:
        """Test that validation fails for week 0."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, week=0)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("week",) for error in errors)
        assert any("greater than 0" in error["msg"] for error in errors)

    def test_invalid_week_negative(self) -> None:
        """Test that validation fails for negative week."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, week=-1)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("week",) for error in errors)
        assert any("greater than 0" in error["msg"] for error in errors)

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
            request = DrivesRequest(year=2023, season_type=season_type)
            assert request.season_type == season_type

    def test_season_type_string_conversion(self) -> None:
        """Test season_type field accepts string values and converts to enum."""
        request = DrivesRequest(year=2023, season_type="regular")
        assert request.season_type == SeasonType.regular
        assert isinstance(request.season_type, SeasonType)

    def test_invalid_season_type(self) -> None:
        """Test that invalid season_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, season_type="invalid_season")

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
            request = DrivesRequest(year=2023, classification=classification)
            assert request.classification == classification

    def test_classification_string_conversion(self) -> None:
        """Test classification field accepts string values and converts to enum."""
        request = DrivesRequest(year=2023, classification="fbs")
        assert request.classification == Classification.fbs
        assert isinstance(request.classification, Classification)

    def test_invalid_classification(self) -> None:
        """Test that invalid classification raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DrivesRequest(year=2023, classification="invalid_division")

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
            "offenseConference": "SEC",  # camelCase alias
            "defenseConference": "ACC",  # camelCase alias
        }
        request = DrivesRequest.model_validate(data)
        assert request.season_type == SeasonType.regular
        assert request.offense_conference == "SEC"
        assert request.defense_conference == "ACC"

    def test_model_dump_with_aliases(self) -> None:
        """Test that model dumps with field aliases."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            offense_conference="SEC",
            defense_conference="ACC",
        )
        dumped = request.model_dump(by_alias=True)
        assert "seasonType" in dumped
        assert dumped["seasonType"] == "regular"
        assert "offenseConference" in dumped
        assert dumped["offenseConference"] == "SEC"
        assert "defenseConference" in dumped
        assert dumped["defenseConference"] == "ACC"

    def test_model_dump_excludes_none_values(self) -> None:
        """Test that model dumps exclude None values by default."""
        request = DrivesRequest(year=2023)
        dumped = request.model_dump(exclude_none=True)
        assert "year" in dumped
        assert dumped["year"] == 2023
        # All optional fields should be excluded since they are None
        assert "season_type" not in dumped
        assert "week" not in dumped
        assert "team" not in dumped
        assert "offense" not in dumped
        assert "defense" not in dumped
        assert "conference" not in dumped
        assert "offense_conference" not in dumped
        assert "defense_conference" not in dumped
        assert "classification" not in dumped

    def test_team_conflict_validation_passes_when_valid(self) -> None:
        """Test that team conflicts validation passes for valid combinations."""
        # Valid: team without offense/defense
        request1 = DrivesRequest(year=2023, team="Alabama")
        assert request1.team == "Alabama"
        assert request1.offense is None
        assert request1.defense is None

        # Valid: offense and defense without team
        request2 = DrivesRequest(year=2023, offense="Alabama", defense="Auburn")
        assert request2.offense == "Alabama"
        assert request2.defense == "Auburn"
        assert request2.team is None

        # Valid: only offense or only defense
        request3 = DrivesRequest(year=2023, offense="Alabama")
        assert request3.offense == "Alabama"
        assert request3.defense is None
        assert request3.team is None

    def test_conference_conflict_validation_passes_when_valid(self) -> None:
        """Test that conference conflicts validation passes for valid combinations."""
        # Valid: conference without offense_conference/defense_conference
        request1 = DrivesRequest(year=2023, conference="SEC")
        assert request1.conference == "SEC"
        assert request1.offense_conference is None
        assert request1.defense_conference is None

        # Valid: offense_conference and defense_conference without conference
        request2 = DrivesRequest(
            year=2023, offense_conference="SEC", defense_conference="ACC"
        )
        assert request2.offense_conference == "SEC"
        assert request2.defense_conference == "ACC"
        assert request2.conference is None

        # Valid: only offense_conference or only defense_conference
        request3 = DrivesRequest(year=2023, offense_conference="SEC")
        assert request3.offense_conference == "SEC"
        assert request3.defense_conference is None
        assert request3.conference is None

    def test_api_parameter_conversion(self) -> None:
        """Test that request converts to API parameters correctly."""
        request = DrivesRequest(
            year=2023,
            season_type=SeasonType.regular,
            week=1,
            team="Alabama",
            classification=Classification.fbs,
        )
        params = request.model_dump(by_alias=True, exclude_none=True)
        expected_params = {
            "year": 2023,
            "seasonType": "regular",
            "week": 1,
            "team": "Alabama",
            "classification": "fbs",
        }
        assert params == expected_params
