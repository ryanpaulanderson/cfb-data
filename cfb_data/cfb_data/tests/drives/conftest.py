"""Shared source-backed fixtures for drives endpoint tests."""

import pytest


@pytest.fixture
def drive_response() -> dict[str, object]:
    """Return one complete current ``GET /drives`` response item."""
    return {
        "offense": "Alabama",
        "offenseConference": "SEC",
        "defense": "Western Kentucky",
        "defenseConference": "Conference USA",
        "gameId": 401628347,
        "id": "4016283471",
        "driveNumber": 1,
        "scoring": False,
        "startPeriod": 1,
        "startYardline": 25,
        "startYardsToGoal": 75,
        "startTime": {"seconds": 0, "minutes": 15},
        "endPeriod": 1,
        "endYardline": 30,
        "endYardsToGoal": 70,
        "endTime": {"seconds": 0, "minutes": 12},
        "elapsed": {"seconds": 0, "minutes": 3},
        "plays": 3,
        "yards": 5,
        "driveResult": "Punt",
        "isHomeOffense": True,
        "startOffenseScore": 0,
        "startDefenseScore": 0,
        "endOffenseScore": 0,
        "endDefenseScore": 0,
    }
