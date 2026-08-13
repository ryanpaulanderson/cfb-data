"""Test public request and response contracts without legacy client layers."""

from datetime import UTC

import pytest
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.games.models.pydantic.responses import CalendarWeek, Game
from pydantic import ValidationError

from cfb_data import (
    AdvancedBoxScoreRequest,
    BettingLinesRequest,
    CalendarRequest,
    Classification,
    CoachesRequest,
    CoachProfileRequest,
    CoachSeasonsRequest,
    CoachTenuresRequest,
    ConferenceSPRatingsRequest,
    CoreRatingsRequest,
    DrivesRequest,
    EloRatingsRequest,
    ExpandedSRSRatingsRequest,
    FPIRatingsRequest,
    GameMediaRequest,
    GamesRequest,
    GameWeatherRequest,
    LivePlaysRequest,
    MediaType,
    PlayerGamePPARequest,
    PlayerGameStatsRequest,
    PlayerSearchRequest,
    PlayerSeasonOverviewRequest,
    PlayerSeasonPPARequest,
    PlayerUsageRequest,
    PlayoffCompetition,
    PlayoffRound,
    PlaysRequest,
    PlayStatsRequest,
    PredictedPointsRequest,
    PregameWinProbabilityRequest,
    RankingsRequest,
    RecordsRequest,
    RecruitingGroupsRequest,
    RecruitingPlayersRequest,
    RecruitingTeamsRequest,
    RetryPolicy,
    ReturningProductionRequest,
    ScoreboardRequest,
    SeasonType,
    SPRatingsRequest,
    SRSRatingsRequest,
    TeamGamePPARequest,
    TeamGameStatsRequest,
    TeamSeasonPPARequest,
    TransferPortalRequest,
    WinProbabilityRequest,
)


def test_request_models_are_exported_and_serialize_upstream_aliases() -> None:
    requests = [
        (GamesRequest(game_id=10), {"id": 10}),
        (GameWeatherRequest(game_id=11), {"gameId": 11}),
        (PlayerGameStatsRequest(game_id=12), {"id": 12}),
        (TeamGameStatsRequest(game_id=13), {"id": 13}),
        (AdvancedBoxScoreRequest(game_id=14), {"id": 14}),
        (
            PlayStatsRequest(game_id=15, athlete_id=16, stat_type_id=17),
            {"gameId": 15, "athleteId": 16, "statTypeId": 17},
        ),
        (LivePlaysRequest(game_id=18), {"gameId": 18}),
        (WinProbabilityRequest(game_id=19), {"gameId": 19}),
        (PlayerSearchRequest(search_term="Smith"), {"searchTerm": "Smith"}),
        (
            PlayerUsageRequest(year=2024, player_id=20, exclude_garbage_time=True),
            {"year": 2024, "playerId": 20, "excludeGarbageTime": True},
        ),
        (BettingLinesRequest(game_id=21), {"gameId": 21}),
        (
            RecruitingGroupsRequest(
                recruit_type="HighSchool", start_year=2020, end_year=2024
            ),
            {
                "recruitType": "HighSchool",
                "startYear": 2020,
                "endYear": 2024,
            },
        ),
        (
            CoachesRequest(first_name="Sherrone", min_year=2024, max_year=2025),
            {"firstName": "Sherrone", "minYear": 2024, "maxYear": 2025},
        ),
        (CoachProfileRequest(coach_id=22), {"coachId": 22}),
    ]

    for request, expected in requests:
        assert (
            request.model_dump(mode="json", by_alias=True, exclude_none=True)
            == expected
        )


@pytest.mark.parametrize(
    ("request_type", "values"),
    [
        (PredictedPointsRequest, {"down": 1, "distance": 10}),
        (TeamSeasonPPARequest, {"year": 2024}),
        (TeamGamePPARequest, {"year": 2024}),
        (PlayerGamePPARequest, {"year": 2024, "team": "Michigan"}),
        (PlayerSeasonPPARequest, {"year": 2024}),
        (PregameWinProbabilityRequest, {}),
        (CoreRatingsRequest, {"year": 2024}),
        (SPRatingsRequest, {"year": 2024}),
        (ConferenceSPRatingsRequest, {}),
        (SRSRatingsRequest, {"year": 2024}),
        (ExpandedSRSRatingsRequest, {"year": 2024}),
        (EloRatingsRequest, {}),
        (FPIRatingsRequest, {"year": 2024}),
        (PlayerSeasonOverviewRequest, {"year": 2024, "player_id": 1}),
        (ReturningProductionRequest, {"year": 2024}),
        (TransferPortalRequest, {"year": 2024}),
        (RankingsRequest, {"year": 2024}),
        (BettingLinesRequest, {"year": 2024}),
        (RecruitingPlayersRequest, {"year": 2024}),
        (RecruitingTeamsRequest, {}),
        (RecruitingGroupsRequest, {}),
        (CoachesRequest, {}),
        (CoachProfileRequest, {"coach_id": 1}),
        (CoachSeasonsRequest, {}),
        (CoachTenuresRequest, {}),
    ],
)
def test_new_request_models_are_public_and_accept_documented_minimums(
    request_type: type[object], values: dict[str, object]
) -> None:
    request_type(**values)


def test_game_id_uses_the_public_name_when_validating_request_models() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GamesRequest.model_validate({"id": 10})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LivePlaysRequest.model_validate({"gameId": 10})


def test_shared_enums_accept_members_and_documented_strings() -> None:
    game = GamesRequest(
        year=2024,
        season_type="postseason",
        classification=Classification.fbs,
        competition="cfp",
        round=PlayoffRound.semifinal,
    )
    media = GameMediaRequest(year=2024, media_type="tv")
    drives = DrivesRequest(year=2024, season_type=SeasonType.regular)
    plays = PlaysRequest(
        year=2024,
        week=1,
        season_type="regular",
        classification="fbs",
    )

    assert game.season_type is SeasonType.postseason
    assert game.classification is Classification.fbs
    assert game.competition is PlayoffCompetition.cfp
    assert media.media_type is MediaType.tv
    assert drives.season_type is SeasonType.regular
    assert plays.season_type is SeasonType.regular
    assert plays.classification is Classification.fbs


def test_response_models_use_the_same_shared_enums(
    game_response: dict[str, object],
) -> None:
    game = Game.model_validate(game_response)

    assert game.season_type is SeasonType.regular
    assert game.home_classification is Classification.fbs


@pytest.mark.parametrize(
    ("request_type", "values"),
    [
        (CalendarRequest, {"year": 2024}),
        (RecordsRequest, {"team": "Alabama"}),
        (ScoreboardRequest, {}),
        (GameMediaRequest, {"year": 2024}),
        (GameWeatherRequest, {"year": 2024}),
        (PlayerGameStatsRequest, {"year": 2024, "week": 1}),
        (TeamGameStatsRequest, {"year": 2024, "team": "Alabama"}),
        (DrivesRequest, {"year": 2024}),
        (PlaysRequest, {"year": 2024, "week": 1}),
        (PlayStatsRequest, {}),
        (LivePlaysRequest, {"game_id": 401628347}),
    ],
)
def test_exported_request_models_accept_documented_minimums(
    request_type: type[object], values: dict[str, object]
) -> None:
    request_type(**values)


@pytest.mark.parametrize(
    ("request_type", "values"),
    [
        (PlaysRequest, {"year": 2024}),
        (PlaysRequest, {"week": 1}),
        (PlayStatsRequest, {"game_id": 0}),
        (PlayStatsRequest, {"athlete_id": -1}),
        (PlayStatsRequest, {"stat_type_id": 0}),
        (LivePlaysRequest, {"game_id": 0}),
    ],
)
def test_plays_requests_reject_missing_or_invalid_selectors(
    request_type: type[object], values: dict[str, object]
) -> None:
    """Reject incomplete historical selectors and non-positive IDs."""
    with pytest.raises(ValidationError):
        request_type(**values)


def test_response_timestamp_is_normalized_to_utc(
    calendar_response: dict[str, object],
) -> None:
    calendar = CalendarWeek.model_validate(calendar_response)

    assert calendar.start_date.tzinfo is UTC
    assert calendar.start_date.hour == 4


def test_naive_response_timestamp_is_rejected(
    calendar_response: dict[str, object],
) -> None:
    calendar_response["startDate"] = "2024-08-22T00:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        CalendarWeek.model_validate(calendar_response)


def test_migrated_response_invariants_reject_invalid_values(
    game_response: dict[str, object], drive_response: dict[str, object]
) -> None:
    game_response["homePostgameWinProbability"] = 1.1
    drive_response["plays"] = -1

    with pytest.raises(ValidationError):
        Game.model_validate(game_response)
    with pytest.raises(ValidationError):
        Drive.model_validate(drive_response)


@pytest.mark.parametrize(
    "policy",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"base_delay_seconds": -0.1},
        {"base_delay_seconds": float("nan")},
        {"base_delay_seconds": 2.0, "max_backoff_seconds": 1.0},
        {"max_backoff_seconds": float("inf")},
        {"max_retry_after_seconds": -1.0},
        {"max_retry_after_seconds": float("inf")},
    ],
)
def test_retry_policy_rejects_unbounded_or_negative_configuration(
    policy: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**policy)
