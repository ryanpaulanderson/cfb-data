"""Shared source-backed fixtures for games endpoint tests."""

import pytest


@pytest.fixture
def scoreboard_response() -> dict[str, object]:
    """Return one complete current ``GET /scoreboard`` response item."""
    return {
        "id": 401628347,
        "startDate": "2024-08-31T23:30:00Z",
        "startTimeTBD": False,
        "tv": "ESPN",
        "neutralSite": False,
        "conferenceGame": False,
        "status": "in_progress",
        "period": 3,
        "clock": "12:34",
        "situation": "2nd & 5",
        "possession": "Alabama",
        "lastPlay": "Five-yard rush",
        "venue": {
            "name": "Bryant-Denny Stadium",
            "city": "Tuscaloosa",
            "state": "AL",
        },
        "homeTeam": {
            "id": 333,
            "name": "Alabama",
            "conference": "SEC",
            "classification": "fbs",
            "points": 35,
            "lineScores": [14, 14, 7],
            "winProbability": 0.98,
        },
        "awayTeam": {
            "id": 2459,
            "name": "Western Kentucky",
            "conference": "Conference USA",
            "classification": "fbs",
            "points": 7,
            "lineScores": [0, 7, 0],
            "winProbability": 0.02,
        },
        "weather": {
            "temperature": 84.0,
            "description": "Partly cloudy",
            "windSpeed": 8.0,
            "windDirection": 180.0,
        },
        "betting": {
            "spread": -31.5,
            "overUnder": 58.5,
            "homeMoneyline": -10000.0,
            "awayMoneyline": 2500.0,
        },
    }
