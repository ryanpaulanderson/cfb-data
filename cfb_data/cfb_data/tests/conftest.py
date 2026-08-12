"""Provide representative payloads and a local HTTP boundary for client tests."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from aiohttp import web

TestHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@asynccontextmanager
async def _run_test_server(handler: TestHandler) -> AsyncIterator[str]:
    """Serve one async handler on an ephemeral local port."""
    application = web.Application()
    application.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(application)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    assert site._server is not None
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


@pytest.fixture
def api_server() -> Callable[[TestHandler], object]:
    """Return a context-manager factory for local HTTP boundary tests."""
    return _run_test_server


@pytest.fixture
def calendar_response() -> dict[str, object]:
    """Return one complete calendar row with a non-UTC source offset."""
    return {
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startDate": "2024-08-22T00:00:00-04:00",
        "endDate": "2024-09-03T00:00:00-04:00",
        "firstGameStart": "2024-08-22T12:30:00-04:00",
        "lastGameStart": "2024-09-02T20:00:00-04:00",
    }


@pytest.fixture
def game_response() -> dict[str, object]:
    """Return one complete game row containing nulls, a list, and a struct."""
    return {
        "id": 401628347,
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startDate": "2024-08-31T19:30:00-04:00",
        "startTimeTBD": False,
        "completed": True,
        "neutralSite": False,
        "conferenceGame": False,
        "attendance": None,
        "venueId": 365,
        "venue": "Bryant-Denny Stadium",
        "homeId": 333,
        "homeTeam": "Alabama",
        "homeConference": "SEC",
        "homeClassification": "fbs",
        "homePoints": 63,
        "homeLineScores": [14.0, 28.0, 7.0, 14.0],
        "homePostgameWinProbability": 0.999,
        "homePregameElo": 1900,
        "homePostgameElo": 1912,
        "awayId": 2459,
        "awayTeam": "Western Kentucky",
        "awayConference": None,
        "awayClassification": "fbs",
        "awayPoints": 0,
        "awayLineScores": [0.0, 0.0, 0.0, 0.0],
        "awayPostgameWinProbability": 0.001,
        "awayPregameElo": 1400,
        "awayPostgameElo": 1388,
        "excitementIndex": 0.42,
        "highlights": None,
        "notes": None,
        "playoff": {
            "competition": "cfp",
            "format": "12-team",
            "round": "first_round",
            "roundName": "First Round",
            "bracketSlot": "R1-1",
            "homeSeed": 5,
            "awaySeed": 12,
            "bowlName": None,
        },
    }


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


@pytest.fixture
def play_response() -> dict[str, object]:
    """Return one complete current ``GET /plays`` response item."""
    return {
        "id": "401628452101849909",
        "driveId": "4016284521",
        "gameId": 401628452,
        "driveNumber": 1,
        "playNumber": 2,
        "offense": "Fresno State",
        "offenseConference": "Mountain West",
        "offenseScore": 0,
        "defense": "Michigan",
        "home": "Michigan",
        "away": "Fresno State",
        "defenseConference": "Big Ten",
        "defenseScore": 0,
        "period": 1,
        "clock": {"minutes": 15, "seconds": 0},
        "offenseTimeouts": 3,
        "defenseTimeouts": 3,
        "yardline": 75,
        "yardsToGoal": 75,
        "down": 1,
        "distance": 10,
        "yardsGained": 1,
        "scoring": False,
        "playType": "Rush",
        "playText": "Elijah Gilliam run for 1 yd to the FRES 26",
        "ppa": -0.5874795431016855,
        "wallclock": "2024-08-31T19:35:05-04:00",
    }


@pytest.fixture
def play_stat_response() -> dict[str, object]:
    """Return one complete current ``GET /plays/stats`` response item."""
    return {
        "gameId": 401628452,
        "season": 2024,
        "week": 1,
        "team": "Michigan",
        "conference": "Big Ten",
        "opponent": "Fresno State",
        "teamScore": 0,
        "opponentScore": 0,
        "driveId": "4016284521",
        "playId": "401628452101866801",
        "period": 1,
        "clock": {"minutes": 13, "seconds": 31},
        "yardsToGoal": 71,
        "down": 3,
        "distance": 6,
        "athleteId": "4794102",
        "athleteName": "Zeke Berry",
        "statType": "Interception",
        "stat": 1,
    }


@pytest.fixture
def live_game_response() -> dict[str, object]:
    """Return one representative nested ``GET /live/plays`` response."""
    play = {
        "id": "401628347101854701",
        "homeScore": 0,
        "awayScore": 0,
        "period": 1,
        "clock": "14:52",
        "wallClock": "2024-09-07T12:10:47-04:00",
        "teamId": 251,
        "team": "Texas",
        "down": 1,
        "distance": 10,
        "yardsToGoal": 76,
        "yardsGained": 2,
        "playTypeId": 24,
        "playType": "Pass Reception",
        "epa": -0.433,
        "garbageTime": False,
        "success": False,
        "rushPass": "pass",
        "downType": "standard",
        "playText": "Quinn Ewers pass complete for 2 yds",
    }
    drive = {
        "id": "4016283471",
        "offenseId": 251,
        "offense": "Texas",
        "defenseId": 130,
        "defense": "Michigan",
        "playCount": 1,
        "yards": 2,
        "startPeriod": 1,
        "startClock": "14:54",
        "startYardsToGoal": 76,
        "endPeriod": 1,
        "endClock": None,
        "endYardsToGoal": 74,
        "duration": "0:02",
        "scoringOpportunity": False,
        "result": "Punt",
        "pointsGained": 0,
        "plays": [play],
    }
    team = {
        "teamId": 251,
        "team": "Texas",
        "homeAway": "away",
        "lineScores": [7, 17, 7, 0],
        "points": 31,
        "drives": 10,
        "scoringOpportunities": 6,
        "pointsPerOpportunity": 5.2,
        "averageStartYardLine": 58.9,
        "plays": 89,
        "lineYards": 103.7,
        "lineYardsPerRush": 3.2,
        "secondLevelYards": 25.0,
        "secondLevelYardsPerRush": 0.8,
        "openFieldYards": 46.0,
        "openFieldYardsPerRush": 1.4,
        "epaPerPlay": 0.02,
        "totalEpa": 1.2,
        "passingEpa": 7.6,
        "epaPerPass": 0.212,
        "rushingEpa": -5.2,
        "epaPerRush": -0.162,
        "successRate": 0.326,
        "standardDownSuccessRate": 0.261,
        "passingDownSuccessRate": 0.395,
        "explosiveness": 0.762,
    }
    return {
        "id": 401628347,
        "status": "Final",
        "period": None,
        "clock": "",
        "possession": "",
        "down": None,
        "distance": None,
        "yardsToGoal": None,
        "teams": [team],
        "drives": [drive],
    }


@pytest.fixture
def advanced_box_response() -> dict[str, object]:
    """Return a valid nested advanced box score with empty metric groups."""
    return {
        "gameInfo": {
            "homeTeam": "Alabama",
            "homePoints": 63,
            "homeWinProb": 0.999,
            "awayTeam": "Western Kentucky",
            "awayPoints": 0,
            "awayWinProb": 0.001,
            "homeWinner": True,
            "excitement": 0.42,
        },
        "teams": {
            "ppa": [],
            "cumulativePpa": [],
            "successRates": [],
            "explosiveness": [],
            "rushing": [],
            "havoc": [],
            "scoringOpportunities": [],
            "fieldPosition": [],
        },
        "players": {"usage": [], "ppa": []},
    }
