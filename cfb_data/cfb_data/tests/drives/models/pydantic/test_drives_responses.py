"""Contract tests for responses documented by the current Drives API."""

import pytest
from cfb_data.drives.models.pydantic.responses import Drive
from pydantic import ValidationError


def test_drive_response_matches_current_contract(
    drive_response: dict[str, object],
) -> None:
    """Validate every field currently returned by ``GET /drives``."""
    drive = Drive.model_validate(drive_response)

    assert drive.game_id == 401628347
    assert drive.start_time.minutes == 15
    assert drive.elapsed.seconds == 0
    assert drive.drive_result == "Punt"


@pytest.mark.parametrize(
    "required_nullable_field",
    ["offenseConference", "defenseConference", "driveNumber"],
)
def test_drive_requires_nullable_keys(
    drive_response: dict[str, object], required_nullable_field: str
) -> None:
    """Require nullable keys that remain mandatory in the upstream object."""
    incomplete_response = drive_response.copy()
    del incomplete_response[required_nullable_field]

    with pytest.raises(ValidationError, match="Field required"):
        Drive.model_validate(incomplete_response)
