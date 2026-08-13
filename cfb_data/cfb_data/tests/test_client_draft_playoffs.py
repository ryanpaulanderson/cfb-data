"""Test Draft and Playoffs endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.draft import DraftPick, DraftPosition, DraftTeam
from cfb_data.playoffs import CfpPlayoff, PlayoffMatchup, PlayoffParticipant
from pydantic import ValidationError

from cfb_data import CFBDClient, CfpGamesRequest, DraftPicksRequest

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _team(team_id: int, school: str) -> dict[str, object]:
    return {"id": team_id, "school": school, "conference": "Big Ten"}


def _participant() -> dict[str, object]:
    return {
        "team": _team(130, "Michigan"),
        "committeeRank": 1,
        "seed": 1,
        "bidType": "automatic",
        "qualificationReason": "Big Ten champion",
        "conferenceChampion": True,
        "qualifyingConference": "Big Ten",
        "firstRoundBye": True,
        "outcome": "champion",
        "eliminatedRound": None,
    }


def _matchup() -> dict[str, object]:
    return {
        "id": 1001,
        "bracketSlot": "QF1",
        "round": "quarterfinal",
        "roundName": "Quarterfinal",
        "roundOrder": 2,
        "matchupOrder": 1,
        "startDate": "2025-01-01T17:00:00-05:00",
        "bowlName": "Rose Bowl",
        "slots": [
            {
                "position": 1,
                "seed": 1,
                "participant": _team(130, "Michigan"),
                "source": None,
            },
            {
                "position": 2,
                "seed": None,
                "participant": None,
                "source": {
                    "matchupId": 1000,
                    "bracketSlot": "R1",
                    "outcome": "winner",
                },
            },
        ],
        "game": {
            "id": 401677000,
            "startDate": "2025-01-01T17:00:00-05:00",
            "completed": True,
            "homeTeam": _team(130, "Michigan"),
            "homePoints": 27,
            "awayTeam": _team(333, "Opponent"),
            "awayPoints": 20,
            "venueId": 1056,
            "venue": "Rose Bowl",
        },
        "advancesTo": {
            "matchupId": 1002,
            "bracketSlot": "SF1",
            "position": 1,
        },
    }


def _payloads() -> dict[str, object]:
    participant = _participant()
    matchup = _matchup()
    return {
        "/draft/teams": [
            {
                "location": "Detroit",
                "nickname": "Lions",
                "displayName": "Detroit Lions",
                "logo": "https://example.test/lions.png",
            }
        ],
        "/draft/positions": [{"name": "Quarterback", "abbreviation": "QB"}],
        "/draft/picks": [
            {
                "collegeAthleteId": 44212186,
                "nflAthleteId": 12345,
                "collegeId": 130,
                "collegeTeam": "Michigan",
                "collegeConference": "Big Ten",
                "nflTeamId": 8,
                "nflTeam": "Detroit Lions",
                "year": 2024,
                "overall": 1,
                "round": 1,
                "pick": 1,
                "name": "Example Player",
                "position": "QB",
                "height": 74,
                "weight": 215,
                "preDraftRanking": 1,
                "preDraftPositionRanking": 1,
                "preDraftGrade": 95,
                "hometownInfo": {
                    "city": "Ann Arbor",
                    "state": "MI",
                    "country": "USA",
                    "latitude": "42.2808",
                    "longitude": "-83.7430",
                    "countyFips": "26161",
                },
            }
        ],
        "/playoffs/cfp": {
            "season": 2024,
            "competition": "cfp",
            "format": "12-team",
            "teamCount": 12,
            "status": "completed",
            "participants": [participant],
            "rounds": [
                {
                    "code": "quarterfinal",
                    "name": "Quarterfinal",
                    "order": 2,
                    "matchups": [matchup],
                }
            ],
            "champion": _team(130, "Michigan"),
        },
        "/playoffs/cfp/participants": [participant],
        "/playoffs/cfp/games": [matchup],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_all_draft_and_playoff_routes_preserve_public_contracts(
    api_server: ServerFactory, backend: str
) -> None:
    payloads = _payloads()
    observed: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            draft_teams = await client.draft.teams()
            draft_positions = await client.draft.positions()
            draft_picks = await client.draft.picks(
                year=2024, school="Michigan", position="QB"
            )
            bracket = await client.playoffs.cfp(year=2024)
            participants = await client.playoffs.participants(year=2024)
            games = await client.playoffs.games(year=2024, round="quarterfinal")

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in (
        (draft_teams, DraftTeam),
        (draft_positions, DraftPosition),
        (draft_picks, DraftPick),
        (participants, PlayoffParticipant),
        (games, PlayoffMatchup),
    ):
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    assert isinstance(bracket, CfpPlayoff)
    assert bracket.rounds[0].matchups[0].game is not None
    assert bracket.rounds[0].matchups[0].game.start_date.tzinfo is UTC

    if backend == "pandas":
        assert draft_picks.loc[0, "hometown_info"]["state"] == "MI"
        assert games.loc[0, "start_date"].tzinfo is UTC
        assert games.loc[0, "slots"][1]["source"]["outcome"] == "winner"
    else:
        assert draft_picks["hometown_info"].struct.field("state")[0] == "MI"
        assert games["start_date"][0].utcoffset().total_seconds() == 0
        assert games["slots"][0].to_list()[1]["source"]["outcome"] == "winner"

    assert observed["/draft/teams"] == {}
    assert observed["/draft/positions"] == {}
    assert observed["/draft/picks"] == {
        "year": "2024",
        "school": "Michigan",
        "position": "QB",
    }
    assert observed["/playoffs/cfp/games"] == {
        "year": "2024",
        "round": "quarterfinal",
    }


def test_draft_and_playoff_requests_reject_invalid_filters() -> None:
    with pytest.raises(ValidationError):
        DraftPicksRequest(year=1935)
    with pytest.raises(ValidationError):
        CfpGamesRequest(year=2024, round="regional")


def test_playoff_matchup_rejects_naive_timestamp() -> None:
    payload = _matchup()
    payload["startDate"] = "2025-01-01T17:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        PlayoffMatchup.model_validate(payload)
