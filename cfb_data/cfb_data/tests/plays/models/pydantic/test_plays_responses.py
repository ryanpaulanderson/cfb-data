"""Contract tests for responses documented by the current Plays API."""

from datetime import UTC

import pytest
from cfb_data.plays.models.pydantic.responses import (
    DownType,
    LiveGame,
    Play,
    PlayStat,
    PlayStatType,
    PlayType,
    RushPass,
)
from pydantic import ValidationError


def test_play_response_matches_current_contract(
    play_response: dict[str, object],
) -> None:
    """Validate every field currently returned by ``GET /plays``."""
    play = Play.model_validate(play_response)

    assert play.game_id == 401628452
    assert play.clock.minutes == 15
    assert play.ppa == pytest.approx(-0.5874795431016855)
    assert play.wallclock is not None
    assert play.wallclock.tzinfo is UTC


@pytest.mark.parametrize(
    "required_nullable_field",
    [
        "driveNumber",
        "playNumber",
        "offenseConference",
        "defenseConference",
        "offenseTimeouts",
        "defenseTimeouts",
        "playText",
        "ppa",
        "wallclock",
    ],
)
def test_play_requires_nullable_keys(
    play_response: dict[str, object], required_nullable_field: str
) -> None:
    """Require nullable keys that remain mandatory upstream."""
    del play_response[required_nullable_field]

    with pytest.raises(ValidationError, match="Field required"):
        Play.model_validate(play_response)


def test_play_stat_and_type_responses_match_current_contracts(
    play_stat_response: dict[str, object],
) -> None:
    """Validate play-stat rows and both reference tables."""
    stat = PlayStat.model_validate(play_stat_response)
    play_type = PlayType.model_validate(
        {"id": 5, "text": "Rush", "abbreviation": "RUSH"}
    )
    stat_type = PlayStatType.model_validate({"id": 1, "name": "Incompletion"})

    assert stat.athlete_id == "4794102"
    assert stat.clock.seconds == 31
    assert play_type.abbreviation == "RUSH"
    assert stat_type.name == "Incompletion"


def test_play_accepts_upstream_unknown_timeout_sentinel(
    play_response: dict[str, object],
) -> None:
    """Preserve the upstream ``-1`` timeout sentinel without coercion."""
    play_response["offenseTimeouts"] = -1
    play_response["defenseTimeouts"] = -1

    play = Play.model_validate(play_response)

    assert play.offense_timeouts == -1
    assert play.defense_timeouts == -1


def test_live_game_matches_nested_current_contract(
    live_game_response: dict[str, object],
) -> None:
    """Validate live teams, drives, plays, enums, and optional metrics."""
    game = LiveGame.model_validate(live_game_response)
    team = game.teams[0]
    play = game.drives[0].plays[0]

    assert team.deserve_to_win is None
    assert play.rush_pass is RushPass.pass_
    assert play.down_type is DownType.standard
    assert play.wall_clock.tzinfo is UTC
    assert play.wall_clock.hour == 16


@pytest.mark.parametrize(
    ("field", "value"),
    [("rushPass", "option"), ("downType", "short")],
)
def test_live_play_rejects_unknown_closed_values(
    live_game_response: dict[str, object], field: str, value: str
) -> None:
    """Reject live-play classifications outside the upstream contract."""
    drives = live_game_response["drives"]
    assert isinstance(drives, list)
    drive = drives[0]
    assert isinstance(drive, dict)
    plays = drive["plays"]
    assert isinstance(plays, list)
    play = plays[0]
    assert isinstance(play, dict)
    play[field] = value

    with pytest.raises(ValidationError):
        LiveGame.model_validate(live_game_response)


@pytest.mark.parametrize("timestamp_field", ["wallclock", "wallClock"])
def test_play_timestamps_must_identify_an_instant(
    play_response: dict[str, object],
    live_game_response: dict[str, object],
    timestamp_field: str,
) -> None:
    """Reject naive timestamps at historical and live boundaries."""
    if timestamp_field == "wallclock":
        play_response[timestamp_field] = "2024-08-31T23:35:05"
        model: type[Play] | type[LiveGame] = Play
        payload = play_response
    else:
        drives = live_game_response["drives"]
        assert isinstance(drives, list)
        drive = drives[0]
        assert isinstance(drive, dict)
        plays = drive["plays"]
        assert isinstance(plays, list)
        play = plays[0]
        assert isinstance(play, dict)
        play[timestamp_field] = "2024-09-07T16:10:47"
        model = LiveGame
        payload = live_game_response

    with pytest.raises(ValidationError, match="timezone-aware"):
        model.model_validate(payload)


def test_plays_responses_reject_undocumented_fields(
    play_response: dict[str, object],
) -> None:
    """Keep the response model authoritative and closed."""
    play_response["privateUpstreamValue"] = "unexpected"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Play.model_validate(play_response)
