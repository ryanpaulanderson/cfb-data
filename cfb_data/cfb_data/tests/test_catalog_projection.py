"""Test identifier-bearing validated models project durable typed facts."""

from datetime import UTC, datetime, timedelta

from cfb_data.cache._catalog import CatalogProjection, project_catalog
from cfb_data.coaches.models.pydantic.responses import CoachTenure
from cfb_data.conferences.models.pydantic.responses import TeamConferenceChange
from cfb_data.draft.models.pydantic.responses import DraftPick
from cfb_data.metrics.models.pydantic.responses import PlayWinProbability
from cfb_data.players.models.pydantic.responses import PlayerSearchResult
from cfb_data.playoffs.models.pydantic.responses import PlayoffMatchupSlotSource
from cfb_data.plays.models.pydantic.responses import Play
from cfb_data.teams.models.pydantic.responses import Team
from pydantic import BaseModel


def _project(
    value: BaseModel, endpoint: str, parameters: dict[str, int]
) -> CatalogProjection:
    """Project one validated model with deterministic observation metadata."""
    now = datetime(2026, 8, 13, tzinfo=UTC)
    return project_catalog(
        endpoint=endpoint,
        parameters=parameters,
        value=value,
        response_key="a" * 64,
        fetched_at=now,
        fresh_until=now + timedelta(days=1),
        retained_until=now + timedelta(days=30),
    )


def test_conference_change_projects_team_conferences_and_affiliation() -> None:
    """Retain all stable IDs exposed by a conference transition."""
    change = TeamConferenceChange.model_validate(
        {
            "teamId": 130,
            "team": "Michigan",
            "fromConferenceId": 8,
            "fromConference": "Independent",
            "fromConferenceAbbreviation": None,
            "fromClassification": "fbs",
            "toConferenceId": 5,
            "toConference": "Big Ten",
            "toConferenceAbbreviation": "B1G",
            "toClassification": "fbs",
            "effectiveYear": 1896,
        }
    )

    projection = _project(change, "/conferences/changes", {})

    assert [(fact.id, fact.school) for fact in projection.teams] == [(130, "Michigan")]
    assert projection.teams[0].alternate_names is None
    assert {fact.id for fact in projection.conferences} == {5, 8}
    assert [fact.start_year for fact in projection.affiliations] == [1896]


def test_authoritative_team_projection_preserves_known_empty_aliases() -> None:
    """Distinguish an observed empty alias list from an unobserved field."""
    team = Team.model_validate(
        {
            "id": 130,
            "school": "Michigan",
            "mascot": "Wolverines",
            "abbreviation": "MICH",
            "alternateNames": [],
            "conference": "Big Ten",
            "division": "East",
            "classification": "fbs",
            "color": "#00274C",
            "alternateColor": "#FFCB05",
            "logos": [],
            "twitter": None,
            "location": None,
        }
    )

    projection = _project(team, "/teams", {})

    assert projection.teams[0].alternate_names == ()


def test_play_models_project_game_drive_play_type_and_team_relationships() -> None:
    """Retain play and contextual relationship IDs from validated play rows."""
    play = Play.model_validate(
        {
            "id": "play-1",
            "driveId": "drive-1",
            "gameId": 401628347,
            "driveNumber": 1,
            "playNumber": 1,
            "offense": "Michigan",
            "offenseConference": "Big Ten",
            "offenseScore": 0,
            "defense": "Alabama",
            "home": "Michigan",
            "away": "Alabama",
            "defenseConference": "SEC",
            "defenseScore": 0,
            "period": 1,
            "clock": {"minutes": 15, "seconds": 0},
            "offenseTimeouts": 3,
            "defenseTimeouts": 3,
            "yardline": 25,
            "yardsToGoal": 75,
            "down": 1,
            "distance": 10,
            "yardsGained": 5,
            "scoring": False,
            "playType": "Rush",
            "playText": "Five-yard rush",
            "ppa": 0.1,
            "wallclock": "2026-08-13T00:00:00Z",
        }
    )
    probability = PlayWinProbability.model_validate(
        {
            "gameId": 401628347,
            "playId": "play-2",
            "playText": "Pass complete",
            "homeId": 130,
            "home": "Michigan",
            "awayId": 333,
            "away": "Alabama",
            "spread": -3.5,
            "homeBall": True,
            "homeScore": 7,
            "awayScore": 0,
            "yardLine": 50,
            "down": 1,
            "distance": 10,
            "homeWinProbability": 0.7,
            "playNumber": 10,
        }
    )

    play_projection = _project(play, "/plays", {})
    probability_projection = _project(probability, "/metrics/wp", {})

    assert [(fact.id, fact.game_id) for fact in play_projection.drives] == [
        ("drive-1", 401628347)
    ]
    assert [(fact.id, fact.drive_id) for fact in play_projection.plays] == [
        ("play-1", "drive-1")
    ]
    assert [(fact.id, fact.game_id) for fact in probability_projection.plays] == [
        ("play-2", 401628347)
    ]
    assert {fact.id for fact in probability_projection.teams} == {130, 333}


def test_player_search_projects_each_explicit_team_season() -> None:
    """Preserve player stint history rather than only the latest team."""
    player = PlayerSearchResult.model_validate(
        {
            "id": "4426385",
            "team": "Michigan",
            "name": "Donovan Edwards",
            "firstName": "Donovan",
            "lastName": "Edwards",
            "weight": 210,
            "height": 72,
            "jersey": 7,
            "position": "RB",
            "hometown": "West Bloomfield",
            "teamColor": "#00274C",
            "teamColorSecondary": "#FFCB05",
            "activeStartYear": 2021,
            "activeEndYear": 2024,
            "teamStints": [{"team": "Michigan", "startYear": 2021, "endYear": 2024}],
        }
    )

    projection = _project(player, "/player/search", {})

    assert {fact.season for fact in projection.athlete_team_seasons} == {
        2021,
        2022,
        2023,
        2024,
    }


def test_draft_coach_and_playoff_reference_ids_are_not_discarded() -> None:
    """Retain reusable secondary identifiers from less common response shapes."""
    pick = DraftPick.model_validate(
        {
            "collegeAthleteId": 4426385,
            "nflAthleteId": 999,
            "collegeId": 130,
            "collegeTeam": "Michigan",
            "collegeConference": "Big Ten",
            "nflTeamId": 12,
            "nflTeam": "Detroit Lions",
            "year": 2025,
            "overall": 1,
            "round": 1,
            "pick": 1,
            "name": "Example Player",
            "position": "RB",
            "height": 72,
            "weight": 210,
            "preDraftRanking": 1,
            "preDraftPositionRanking": 1,
            "preDraftGrade": 99,
            "hometownInfo": {
                "city": "Ann Arbor",
                "state": "MI",
                "country": "US",
                "latitude": None,
                "longitude": None,
                "countyFips": None,
            },
        }
    )
    tenure = CoachTenure.model_validate(
        {
            "id": 44,
            "coach": {"id": 1, "firstName": "Jim", "lastName": "Coach"},
            "team": {"id": 130, "school": "Michigan"},
            "hireDate": "2020-01-01",
            "startYear": 2020,
            "endYear": 2024,
            "effectiveStart": "2020-01-01T00:00:00Z",
            "effectiveEnd": "2024-12-31T00:00:00Z",
            "isInterim": False,
            "active": False,
            "seasons": 5,
            "record": {
                "games": 60,
                "wins": 50,
                "losses": 10,
                "ties": 0,
                "winPercentage": 0.833,
            },
            "attributionComplete": True,
        }
    )
    source = PlayoffMatchupSlotSource.model_validate(
        {"matchupId": 10, "bracketSlot": "R1-1", "outcome": "winner"}
    )

    draft_projection = _project(pick, "/draft/picks", {})
    coach_projection = _project(tenure, "/coaches/tenures", {})
    playoff_projection = _project(source, "/playoffs/cfp", {"year": 2025})

    assert [fact.id for fact in draft_projection.teams] == [130]
    assert {fact.namespace for fact in draft_projection.vocabularies} == {
        "draft_team",
        "nfl_athlete",
    }
    assert [fact.tenure_id for fact in coach_projection.coach_team_seasons] == [44]
    assert [fact.id for fact in playoff_projection.playoff_matchups] == [10]
