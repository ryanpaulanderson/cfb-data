"""Project validated responses into typed durable identity facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from pydantic import BaseModel

from cfb_data.base.types import QueryParameters


class CoverageStatus(StrEnum):
    """Describe whether a validated partition proves complete coverage."""

    complete = "complete"
    partial = "partial"
    possibly_truncated = "possibly_truncated"


@dataclass(frozen=True, slots=True)
class TeamFact:
    """Store the durable core identity for one team."""

    id: int
    school: str
    abbreviation: str | None
    alternate_names: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class TeamSeasonFact:
    """Store one time-varying team relationship snapshot."""

    team_id: int
    season: int
    conference_name: str | None
    venue_id: int | None


@dataclass(frozen=True, slots=True)
class ConferenceFact:
    """Store the durable core identity for one conference."""

    id: int
    name: str
    abbreviation: str | None
    classification: str | None


@dataclass(frozen=True, slots=True)
class ConferenceAffiliationFact:
    """Store a historical team-to-conference validity interval."""

    team_id: int
    conference_id: int
    start_year: int
    end_year: int | None


@dataclass(frozen=True, slots=True)
class VenueFact:
    """Store the durable core identity for one venue."""

    id: int
    name: str
    city: str | None
    state: str | None


@dataclass(frozen=True, slots=True)
class GameFact:
    """Store one game partition and its stable relationships."""

    id: int
    season: int | None
    week: int | None
    season_type: str | None
    start_date: datetime | None
    status: str | None
    home_team_id: int | None
    away_team_id: int | None
    venue_id: int | None


@dataclass(frozen=True, slots=True)
class AthleteFact:
    """Store the durable core identity for one athlete."""

    id: str
    name: str
    position: str | None


@dataclass(frozen=True, slots=True)
class AthleteTeamSeasonFact:
    """Store one athlete membership at a team-season grain."""

    athlete_id: str
    team_name: str
    season: int


@dataclass(frozen=True, slots=True)
class RecruitFact:
    """Store one recruiting identity and optional athlete link."""

    id: str
    athlete_id: str | None
    name: str
    year: int


@dataclass(frozen=True, slots=True)
class CoachFact:
    """Store the durable core identity for one coach."""

    id: int
    name: str
    wikidata_id: str | None = None


@dataclass(frozen=True, slots=True)
class CoachTeamSeasonFact:
    """Store one coach-to-team time relationship."""

    coach_id: int
    team_id: int
    start_year: int
    end_year: int | None
    tenure_id: int | None = None


@dataclass(frozen=True, slots=True)
class DriveFact:
    """Store one drive and its game/team relationships."""

    id: str
    game_id: int
    offense_team_id: int | None
    offense_team: str | None
    defense_team_id: int | None
    defense_team: str | None


@dataclass(frozen=True, slots=True)
class PlayFact:
    """Store one play and its game, drive, and type relationships."""

    id: str
    game_id: int
    drive_id: str | None
    play_type_id: int | None
    play_type: str | None


@dataclass(frozen=True, slots=True)
class VocabularyFact:
    """Store one enumerated provider vocabulary item."""

    namespace: str
    id: str
    name: str
    abbreviation: str | None


@dataclass(frozen=True, slots=True)
class PlayoffMatchupFact:
    """Store one playoff matchup and its linked game."""

    id: int
    season: int | None
    linked_game_id: int | None


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    """Record the capabilities proven by one canonical validated partition."""

    partition_key: str
    namespace: str
    canonical_filters: str
    capabilities: tuple[str, ...]
    status: CoverageStatus
    response_key: str
    endpoint: str
    fetched_at: datetime
    validated_at: datetime
    fresh_until: datetime
    retained_until: datetime
    row_count: int
    known_cap: int | None


@dataclass(frozen=True, slots=True)
class CatalogProjection:
    """Carry typed facts and coverage for one atomic backend commit."""

    teams: tuple[TeamFact, ...] = ()
    team_seasons: tuple[TeamSeasonFact, ...] = ()
    conferences: tuple[ConferenceFact, ...] = ()
    affiliations: tuple[ConferenceAffiliationFact, ...] = ()
    venues: tuple[VenueFact, ...] = ()
    games: tuple[GameFact, ...] = ()
    athletes: tuple[AthleteFact, ...] = ()
    athlete_team_seasons: tuple[AthleteTeamSeasonFact, ...] = ()
    recruits: tuple[RecruitFact, ...] = ()
    coaches: tuple[CoachFact, ...] = ()
    coach_team_seasons: tuple[CoachTeamSeasonFact, ...] = ()
    drives: tuple[DriveFact, ...] = ()
    plays: tuple[PlayFact, ...] = ()
    vocabularies: tuple[VocabularyFact, ...] = ()
    playoff_matchups: tuple[PlayoffMatchupFact, ...] = ()
    coverage: CoverageRecord | None = None


_TEAM_CLASSES = frozenset(
    {
        "Team",
        "TeamRecords",
        "TeamATS",
        "ScoreboardTeam",
        "TeamGameStatsTeam",
        "LiveGameTeam",
        "PlayoffTeam",
        "CoachTeamReference",
        "CoachSeasonTeamReference",
        "CoachAlmaMater",
        "CoachSeason",
        "AdjustedTeamMetrics",
        "PollRank",
        "LiveGamePlay",
    }
)
_ATHLETE_CLASSES = frozenset(
    {
        "RosterPlayer",
        "PlayerSearchResult",
        "PlayerUsage",
        "PlayerSeasonOverview",
        "PlayerGameStatPlayer",
        "PlayerStat",
        "PlayerSeasonSuccessRate",
        "PlayerGameSuccessRate",
        "PlayerGamePredictedPointsAdded",
        "PlayerSeasonPredictedPointsAdded",
        "PlayerWeightedEPA",
        "KickerPAAR",
    }
)
_GAME_CLASSES = frozenset(
    {
        "Game",
        "ScoreboardGame",
        "LiveGame",
        "GameMedia",
        "GameWeather",
        "TeamGameStats",
        "PlayerGameStats",
        "BettingGame",
        "PlayWinProbability",
        "PregameWinProbability",
        "TeamGamePredictedPointsAdded",
        "AdvancedGameStat",
        "GameHavocStats",
        "PlayerGameSuccessRate",
        "PlayStat",
        "PlayoffLinkedGame",
    }
)


class _ProjectionBuilder:
    """Accumulate deduplicated typed identity facts from model instances."""

    def __init__(self, parameters: QueryParameters) -> None:
        self._parameters = parameters
        self.teams: dict[int, TeamFact] = {}
        self.team_seasons: dict[tuple[int, int], TeamSeasonFact] = {}
        self.conferences: dict[int, ConferenceFact] = {}
        self.affiliations: dict[tuple[int, int, int], ConferenceAffiliationFact] = {}
        self.venues: dict[int, VenueFact] = {}
        self.games: dict[int, GameFact] = {}
        self.athletes: dict[str, AthleteFact] = {}
        self.athlete_team_seasons: dict[
            tuple[str, str, int], AthleteTeamSeasonFact
        ] = {}
        self.recruits: dict[str, RecruitFact] = {}
        self.coaches: dict[int, CoachFact] = {}
        self.coach_team_seasons: dict[tuple[int, int, int], CoachTeamSeasonFact] = {}
        self.drives: dict[str, DriveFact] = {}
        self.plays: dict[str, PlayFact] = {}
        self.vocabularies: dict[tuple[str, str], VocabularyFact] = {}
        self.playoff_matchups: dict[int, PlayoffMatchupFact] = {}
        self._playoff_season: int | None = None

    def visit(self, value: object) -> None:
        """Visit validated models recursively without interpreting raw payloads."""
        if isinstance(value, list | tuple):
            for item in value:
                self.visit(item)
            return
        if not isinstance(value, BaseModel):
            return

        class_name = type(value).__name__
        data = value.model_dump(mode="python")
        self._project(class_name, data)
        for item in data.values():
            self.visit(item)
        for field_name in type(value).model_fields:
            nested = getattr(value, field_name)
            if isinstance(nested, BaseModel | list | tuple):
                self.visit(nested)

    def _project(self, class_name: str, data: dict[str, object]) -> None:
        """Project one known response-model shape into its typed fact schema."""
        if class_name == "CfpPlayoff":
            self._playoff_season = _optional_int(data.get("season"))
        if class_name in _TEAM_CLASSES:
            self._project_team(class_name, data)
        if class_name == "Conference":
            self._project_conference(data)
        if class_name == "TeamConferenceAffiliation":
            self._project_affiliation(data)
        if class_name == "TeamConferenceChange":
            self._project_conference_change(data)
        if class_name == "Venue":
            self._project_venue(data)
        if class_name in _GAME_CLASSES:
            self._project_game(class_name, data)
        if class_name in _ATHLETE_CLASSES:
            self._project_athlete(class_name, data)
        if class_name == "PlayerSearchResult":
            self._project_player_search_stints(data)
        if class_name == "PlayStat":
            self._project_play_stat_athlete(data)
            self._project_play_stat(data)
        if class_name == "Recruit":
            self._project_recruit(data)
        if class_name in {"Coach", "CoachReference", "CoachProfile"}:
            self._project_coach(data)
        if class_name == "CoachTenure":
            self._project_coach_tenure(data)
        if class_name == "DetailedCoachSeason":
            self._project_detailed_coach_season(data)
        if class_name == "Coach":
            self._project_coach_seasons(data)
        if class_name in {"Drive", "LiveGameDrive"}:
            self._project_drive(data)
        if class_name in {"Play", "LiveGamePlay"}:
            self._project_play(data)
        if class_name == "PlayType":
            self._project_vocabulary("play_type", data, "text")
        if class_name == "PlayStatType":
            self._project_vocabulary("play_stat_type", data, "name")
        if class_name == "DraftTeam":
            self._project_draft_team(data)
        if class_name == "DraftPosition":
            self._project_draft_position(data)
        if class_name == "DraftPick":
            self._project_draft_pick(data)
        if class_name == "PlayoffMatchup":
            self._project_playoff_matchup(data)
        if class_name in {"PlayoffMatchupSlotSource", "PlayoffAdvancement"}:
            self._project_playoff_matchup_reference(data)
        if class_name == "LiveGame":
            self._project_live_game(data)
        if class_name == "PlayWinProbability":
            self._project_win_probability_play(data)
        if class_name == "PlayerGameStats":
            self._project_player_game_stats(data)

    def _project_team(self, class_name: str, data: dict[str, object]) -> None:
        team_id = _optional_int(data.get("team_id"))
        if team_id is None and class_name in {
            "Team",
            "ScoreboardTeam",
            "PlayoffTeam",
            "CoachTeamReference",
            "CoachSeasonTeamReference",
            "CoachAlmaMater",
        }:
            team_id = _optional_int(data.get("id"))
        school = _first_string(data, "school", "team", "name")
        if team_id is None or school is None:
            return
        aliases = data.get("alternate_names")
        alternate_names: tuple[str, ...] | None = (
            tuple(item for item in aliases if isinstance(item, str))
            if isinstance(aliases, list)
            else None
        )
        abbreviation = _optional_string(data.get("abbreviation"))
        existing = self.teams.get(team_id)
        if existing is None or class_name == "Team":
            self.teams[team_id] = TeamFact(
                id=team_id,
                school=school,
                abbreviation=abbreviation
                or (existing.abbreviation if existing else None),
                alternate_names=(
                    alternate_names
                    if alternate_names is not None
                    else (existing.alternate_names if existing else None)
                ),
            )
        season = _optional_int(data.get("year")) or _optional_int(
            self._parameters.get("year")
        )
        if season is not None:
            conference = _optional_string(data.get("conference"))
            location = data.get("location")
            venue_id = None
            if isinstance(location, dict):
                venue_id = _optional_int(location.get("id"))
            self.team_seasons[(team_id, season)] = TeamSeasonFact(
                team_id=team_id,
                season=season,
                conference_name=conference,
                venue_id=venue_id,
            )

    def _project_conference(self, data: dict[str, object]) -> None:
        conference_id = _optional_int(data.get("id"))
        name = _optional_string(data.get("name"))
        if conference_id is None or name is None:
            return
        self.conferences[conference_id] = ConferenceFact(
            id=conference_id,
            name=name,
            abbreviation=_optional_string(data.get("abbreviation")),
            classification=_optional_string(data.get("classification")),
        )

    def _project_affiliation(self, data: dict[str, object]) -> None:
        team_id = _optional_int(data.get("team_id"))
        conference_id = _optional_int(data.get("conference_id"))
        start_year = _optional_int(data.get("start_year"))
        if team_id is None or conference_id is None or start_year is None:
            return
        fact = ConferenceAffiliationFact(
            team_id=team_id,
            conference_id=conference_id,
            start_year=start_year,
            end_year=_optional_int(data.get("end_year")),
        )
        self.affiliations[(team_id, conference_id, start_year)] = fact
        school = _optional_string(data.get("team"))
        if school is not None:
            self.teams.setdefault(team_id, TeamFact(team_id, school, None, None))
        name = _optional_string(data.get("conference"))
        if name is not None:
            self.conferences.setdefault(
                conference_id,
                ConferenceFact(
                    conference_id,
                    name,
                    _optional_string(data.get("conference_abbreviation")),
                    _optional_string(data.get("classification")),
                ),
            )

    def _project_conference_change(self, data: dict[str, object]) -> None:
        """Project both sides of a validated conference transition."""
        team_id = _optional_int(data.get("team_id"))
        effective_year = _optional_int(data.get("effective_year"))
        from_id = _optional_int(data.get("from_conference_id"))
        to_id = _optional_int(data.get("to_conference_id"))
        team_name = _optional_string(data.get("team"))
        if team_id is None or effective_year is None:
            return
        if team_name is not None:
            self.teams.setdefault(team_id, TeamFact(team_id, team_name, None, None))
        if from_id is not None:
            from_name = _optional_string(data.get("from_conference"))
            if from_name is not None:
                self.conferences.setdefault(
                    from_id,
                    ConferenceFact(
                        from_id,
                        from_name,
                        _optional_string(data.get("from_conference_abbreviation")),
                        _optional_string(data.get("from_classification")),
                    ),
                )
        if to_id is not None:
            to_name = _optional_string(data.get("to_conference"))
            if to_name is not None:
                self.conferences.setdefault(
                    to_id,
                    ConferenceFact(
                        to_id,
                        to_name,
                        _optional_string(data.get("to_conference_abbreviation")),
                        _optional_string(data.get("to_classification")),
                    ),
                )
            self.affiliations[(team_id, to_id, effective_year)] = (
                ConferenceAffiliationFact(team_id, to_id, effective_year, None)
            )

    def _project_venue(self, data: dict[str, object]) -> None:
        venue_id = _optional_int(data.get("id"))
        name = _optional_string(data.get("name"))
        if venue_id is None or venue_id <= 0 or name is None:
            return
        self.venues[venue_id] = VenueFact(
            venue_id,
            name,
            _optional_string(data.get("city")),
            _optional_string(data.get("state")),
        )

    def _project_game(self, class_name: str, data: dict[str, object]) -> None:
        game_id = _optional_int(data.get("game_id"))
        if game_id is None and class_name in {
            "Game",
            "ScoreboardGame",
            "LiveGame",
            "GameMedia",
            "GameWeather",
            "TeamGameStats",
            "PlayerGameStats",
            "BettingGame",
            "PlayoffLinkedGame",
        }:
            game_id = _optional_int(data.get("id"))
        if game_id is None or game_id <= 0:
            return
        home_team_id = _optional_int(data.get("home_id")) or _optional_int(
            data.get("home_team_id")
        )
        away_team_id = _optional_int(data.get("away_id")) or _optional_int(
            data.get("away_team_id")
        )
        if class_name in {"LiveGame", "TeamGameStats"}:
            nested_home_team_id, nested_away_team_id = _nested_game_team_ids(data)
            home_team_id = home_team_id or nested_home_team_id
            away_team_id = away_team_id or nested_away_team_id
        venue_id = _optional_int(data.get("venue_id"))
        if class_name == "ScoreboardGame":
            home_team_id = _nested_int(data.get("home_team"), "id")
            away_team_id = _nested_int(data.get("away_team"), "id")
        if class_name == "PlayoffLinkedGame":
            home_team_id = _nested_int(data.get("home_team"), "id")
            away_team_id = _nested_int(data.get("away_team"), "id")
        status = _optional_string(data.get("status"))
        if class_name == "Game" and status is None:
            completed = data.get("completed")
            status = "completed" if completed is True else None
        raw_start_date = data.get("start_date") or data.get("start_time")
        start_date = raw_start_date if isinstance(raw_start_date, datetime) else None
        self.games[game_id] = GameFact(
            id=game_id,
            season=_optional_int(data.get("season"))
            or _optional_int(self._parameters.get("year")),
            week=_optional_int(data.get("week")),
            season_type=_optional_string(data.get("season_type")),
            start_date=start_date,
            status=status,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            venue_id=venue_id,
        )
        self._project_game_teams(data, home_team_id, away_team_id)
        venue_name = _optional_string(data.get("venue"))
        if venue_id is not None and venue_id > 0 and venue_name is not None:
            self.venues.setdefault(
                venue_id, VenueFact(venue_id, venue_name, None, None)
            )

    def _project_athlete(self, class_name: str, data: dict[str, object]) -> None:
        athlete_id = _first_string(data, "id", "athlete_id", "player_id")
        name = _first_string(data, "name", "athlete_name", "player")
        if name is None:
            name = (
                " ".join(
                    part
                    for part in (
                        _optional_string(data.get("first_name")),
                        _optional_string(data.get("last_name")),
                    )
                    if part
                )
                or None
            )
        if athlete_id is None or name is None:
            return
        self.athletes[athlete_id] = AthleteFact(
            athlete_id, name, _optional_string(data.get("position"))
        )
        team = _optional_string(data.get("team"))
        season = _optional_int(data.get("season"))
        if class_name in {"PlayerWeightedEPA", "KickerPAAR"}:
            season = _optional_int(data.get("year"))
        season = season or _optional_int(self._parameters.get("year"))
        if team is not None and season is not None:
            key = (athlete_id, team, season)
            self.athlete_team_seasons[key] = AthleteTeamSeasonFact(*key)
        recruit_ids = data.get("recruit_ids")
        if isinstance(recruit_ids, list) and season is not None:
            for recruit_id in recruit_ids:
                if isinstance(recruit_id, str):
                    self.recruits.setdefault(
                        recruit_id,
                        RecruitFact(recruit_id, athlete_id, name, season),
                    )

    def _project_play_stat_athlete(self, data: dict[str, object]) -> None:
        athlete_id = _optional_string(data.get("athlete_id"))
        name = _optional_string(data.get("athlete_name"))
        if athlete_id is None or name is None:
            return
        self.athletes.setdefault(athlete_id, AthleteFact(athlete_id, name, None))
        team = _optional_string(data.get("team"))
        season = _optional_int(data.get("season"))
        if team is not None and season is not None:
            key = (athlete_id, team, season)
            self.athlete_team_seasons[key] = AthleteTeamSeasonFact(*key)

    def _project_player_search_stints(self, data: dict[str, object]) -> None:
        """Project explicit team-season memberships from player search history."""
        athlete_id = _optional_string(data.get("id"))
        stints = data.get("team_stints")
        if athlete_id is None or not isinstance(stints, list):
            return
        active_end_year = _optional_int(data.get("active_end_year"))
        for stint in stints:
            if not isinstance(stint, dict):
                continue
            team = _optional_string(stint.get("team"))
            start_year = _optional_int(stint.get("start_year"))
            end_year = _optional_int(stint.get("end_year")) or active_end_year
            if team is None or start_year is None or end_year is None:
                continue
            if end_year < start_year or end_year - start_year > 100:
                continue
            for season in range(start_year, end_year + 1):
                key = (athlete_id, team, season)
                self.athlete_team_seasons[key] = AthleteTeamSeasonFact(*key)

    def _project_recruit(self, data: dict[str, object]) -> None:
        recruit_id = _optional_string(data.get("id"))
        name = _optional_string(data.get("name"))
        year = _optional_int(data.get("year"))
        if recruit_id is None or name is None or year is None:
            return
        athlete_id = _optional_string(data.get("athlete_id"))
        self.recruits[recruit_id] = RecruitFact(
            recruit_id,
            athlete_id,
            name,
            year,
        )
        if athlete_id is not None:
            self.athletes.setdefault(
                athlete_id,
                AthleteFact(
                    athlete_id,
                    name,
                    _optional_string(data.get("position")),
                ),
            )

    def _project_coach(self, data: dict[str, object]) -> None:
        coach_id = _optional_int(data.get("id"))
        if coach_id is None:
            return
        name = _optional_string(data.get("display_name")) or " ".join(
            part
            for part in (
                _optional_string(data.get("first_name")),
                _optional_string(data.get("last_name")),
            )
            if part
        )
        if name:
            self.coaches[coach_id] = CoachFact(
                coach_id,
                name,
                _optional_string(data.get("wikidata_id")),
            )

    def _project_coach_tenure(self, data: dict[str, object]) -> None:
        tenure_id = _optional_int(data.get("id"))
        coach = data.get("coach")
        team = data.get("team")
        start_year = _optional_int(data.get("start_year"))
        if (
            not isinstance(coach, dict)
            or not isinstance(team, dict)
            or start_year is None
        ):
            return
        coach_id = _optional_int(coach.get("id"))
        team_id = _optional_int(team.get("id"))
        if coach_id is None or team_id is None:
            return
        fact = CoachTeamSeasonFact(
            coach_id,
            team_id,
            start_year,
            _optional_int(data.get("end_year")),
            tenure_id,
        )
        self.coach_team_seasons[(coach_id, team_id, start_year)] = fact

    def _project_detailed_coach_season(self, data: dict[str, object]) -> None:
        """Project one coach-team relationship at its explicit season grain."""
        coach_id = _nested_int(data.get("coach"), "id")
        team_id = _nested_int(data.get("team"), "id")
        year = _optional_int(data.get("year"))
        if coach_id is None or team_id is None or year is None:
            return
        self.coach_team_seasons[(coach_id, team_id, year)] = CoachTeamSeasonFact(
            coach_id, team_id, year, year
        )

    def _project_coach_seasons(self, data: dict[str, object]) -> None:
        """Project nested summary seasons with their owning coach ID."""
        coach_id = _optional_int(data.get("id"))
        seasons = data.get("seasons")
        if coach_id is None or not isinstance(seasons, list):
            return
        for season in seasons:
            if not isinstance(season, dict):
                continue
            team_id = _optional_int(season.get("team_id"))
            year = _optional_int(season.get("year"))
            if team_id is not None and year is not None:
                self.coach_team_seasons[(coach_id, team_id, year)] = (
                    CoachTeamSeasonFact(coach_id, team_id, year, year)
                )

    def _project_drive(self, data: dict[str, object]) -> None:
        drive_id = _optional_string(data.get("id"))
        game_id = _optional_int(data.get("game_id")) or _optional_int(
            self._parameters.get("id")
        )
        if drive_id is None or game_id is None:
            return
        self.drives[drive_id] = DriveFact(
            drive_id,
            game_id,
            _optional_int(data.get("offense_id")),
            _first_string(data, "offense", "offense_team"),
            _optional_int(data.get("defense_id")),
            _first_string(data, "defense", "defense_team"),
        )
        self._project_drive_teams(data)

    def _project_play(self, data: dict[str, object]) -> None:
        play_id = _optional_string(data.get("id"))
        game_id = _optional_int(data.get("game_id")) or _optional_int(
            self._parameters.get("id")
        )
        if play_id is None or game_id is None:
            return
        self.plays[play_id] = PlayFact(
            play_id,
            game_id,
            _optional_string(data.get("drive_id")),
            _optional_int(data.get("play_type_id")),
            _optional_string(data.get("play_type")),
        )
        drive_id = _optional_string(data.get("drive_id"))
        if drive_id is not None:
            self.drives.setdefault(
                drive_id, DriveFact(drive_id, game_id, None, None, None, None)
            )
        play_type_id = _optional_int(data.get("play_type_id"))
        play_type = _optional_string(data.get("play_type"))
        if play_type_id is not None and play_type is not None:
            self.vocabularies.setdefault(
                ("play_type", str(play_type_id)),
                VocabularyFact("play_type", str(play_type_id), play_type, None),
            )

    def _project_vocabulary(
        self, namespace: str, data: dict[str, object], name_field: str
    ) -> None:
        source_id = data.get("id")
        name = _optional_string(data.get(name_field))
        if not isinstance(source_id, int | str) or name is None:
            return
        fact = VocabularyFact(
            namespace,
            str(source_id),
            name,
            _optional_string(data.get("abbreviation")),
        )
        self.vocabularies[(namespace, str(source_id))] = fact

    def _project_playoff_matchup(self, data: dict[str, object]) -> None:
        matchup_id = _optional_int(data.get("id"))
        if matchup_id is None:
            return
        self.playoff_matchups[matchup_id] = PlayoffMatchupFact(
            matchup_id,
            self._playoff_season or _optional_int(self._parameters.get("year")),
            _nested_int(data.get("game"), "id"),
        )

    def _project_playoff_matchup_reference(self, data: dict[str, object]) -> None:
        """Retain a referenced matchup ID even when its full row is absent."""
        matchup_id = _optional_int(data.get("matchup_id"))
        if matchup_id is None:
            return
        self.playoff_matchups.setdefault(
            matchup_id,
            PlayoffMatchupFact(
                matchup_id,
                self._playoff_season or _optional_int(self._parameters.get("year")),
                None,
            ),
        )

    def _project_play_stat(self, data: dict[str, object]) -> None:
        """Project play and drive relationships exposed by a play-stat row."""
        play_id = _optional_string(data.get("play_id"))
        game_id = _optional_int(data.get("game_id"))
        if play_id is None or game_id is None:
            return
        self.plays.setdefault(
            play_id,
            PlayFact(
                play_id,
                game_id,
                _optional_string(data.get("drive_id")),
                None,
                None,
            ),
        )
        drive_id = _optional_string(data.get("drive_id"))
        if drive_id is not None:
            self.drives.setdefault(
                drive_id, DriveFact(drive_id, game_id, None, None, None, None)
            )

    def _project_live_game(self, data: dict[str, object]) -> None:
        """Project contextual live drive/play relationships from their parent game."""
        game_id = _optional_int(data.get("id"))
        drives = data.get("drives")
        if game_id is None or not isinstance(drives, list):
            return
        for drive in drives:
            if not isinstance(drive, dict):
                continue
            drive_id = _optional_string(drive.get("id"))
            if drive_id is None:
                continue
            self.drives[drive_id] = DriveFact(
                drive_id,
                game_id,
                _optional_int(drive.get("offense_id")),
                _optional_string(drive.get("offense")),
                _optional_int(drive.get("defense_id")),
                _optional_string(drive.get("defense")),
            )
            self._project_drive_teams(drive)
            plays = drive.get("plays")
            if not isinstance(plays, list):
                continue
            for play in plays:
                if not isinstance(play, dict):
                    continue
                play_id = _optional_string(play.get("id"))
                if play_id is not None:
                    self.plays[play_id] = PlayFact(
                        play_id,
                        game_id,
                        drive_id,
                        _optional_int(play.get("play_type_id")),
                        _optional_string(play.get("play_type")),
                    )
                    play_type_id = _optional_int(play.get("play_type_id"))
                    play_type = _optional_string(play.get("play_type"))
                    if play_type_id is not None and play_type is not None:
                        self.vocabularies.setdefault(
                            ("play_type", str(play_type_id)),
                            VocabularyFact(
                                "play_type", str(play_type_id), play_type, None
                            ),
                        )

    def _project_drive_teams(self, data: dict[str, object]) -> None:
        """Project offense and defense team identities carried by a drive."""
        for id_field, name_fields in (
            ("offense_id", ("offense", "offense_team")),
            ("defense_id", ("defense", "defense_team")),
        ):
            team_id = _optional_int(data.get(id_field))
            team_name = _first_string(data, *name_fields)
            if team_id is not None and team_name is not None:
                self.teams.setdefault(team_id, TeamFact(team_id, team_name, None, None))

    def _project_win_probability_play(self, data: dict[str, object]) -> None:
        """Project a play identity carried by a win-probability row."""
        play_id = _optional_string(data.get("play_id"))
        game_id = _optional_int(data.get("game_id"))
        if play_id is None or game_id is None:
            return
        self.plays.setdefault(play_id, PlayFact(play_id, game_id, None, None, None))

    def _project_player_game_stats(self, data: dict[str, object]) -> None:
        """Project athlete membership using the parent team's context."""
        teams = data.get("teams")
        season = _optional_int(self._parameters.get("year"))
        if not isinstance(teams, list):
            return
        for team in teams:
            if not isinstance(team, dict):
                continue
            team_name = _optional_string(team.get("team"))
            categories = team.get("categories")
            if not isinstance(categories, list):
                continue
            for category in categories:
                if not isinstance(category, dict):
                    continue
                stat_types = category.get("types")
                if not isinstance(stat_types, list):
                    continue
                for stat_type in stat_types:
                    if not isinstance(stat_type, dict):
                        continue
                    athletes = stat_type.get("athletes")
                    if not isinstance(athletes, list):
                        continue
                    for athlete in athletes:
                        if not isinstance(athlete, dict):
                            continue
                        athlete_id = _optional_string(athlete.get("id"))
                        name = _optional_string(athlete.get("name"))
                        if athlete_id is None or name is None:
                            continue
                        self.athletes.setdefault(
                            athlete_id, AthleteFact(athlete_id, name, None)
                        )
                        if team_name is not None and season is not None:
                            key = (athlete_id, team_name, season)
                            self.athlete_team_seasons[key] = AthleteTeamSeasonFact(*key)

    def _project_game_teams(
        self,
        data: dict[str, object],
        home_team_id: int | None,
        away_team_id: int | None,
    ) -> None:
        """Project team IDs and canonical names carried by a game-shaped row."""
        if home_team_id is not None:
            home_name = _first_string(data, "home_team", "home")
            if home_name is None and isinstance(data.get("home_team"), dict):
                home_name = _optional_string(
                    cast(dict[str, object], data["home_team"]).get("school")
                )
            if home_name is not None:
                self.teams.setdefault(
                    home_team_id, TeamFact(home_team_id, home_name, None, None)
                )
        if away_team_id is not None:
            away_name = _first_string(data, "away_team", "away")
            if away_name is None and isinstance(data.get("away_team"), dict):
                away_name = _optional_string(
                    cast(dict[str, object], data["away_team"]).get("school")
                )
            if away_name is not None:
                self.teams.setdefault(
                    away_team_id, TeamFact(away_team_id, away_name, None, None)
                )

    def _project_draft_team(self, data: dict[str, object]) -> None:
        """Project an NFL draft team using its stable display identity."""
        name = _first_string(data, "display_name", "location")
        if name is None:
            return
        self.vocabularies[("draft_team", name)] = VocabularyFact(
            "draft_team", name, name, None
        )

    def _project_draft_position(self, data: dict[str, object]) -> None:
        """Project an NFL draft position using its provider abbreviation."""
        abbreviation = _optional_string(data.get("abbreviation"))
        name = _optional_string(data.get("name"))
        if abbreviation is None or name is None:
            return
        self.vocabularies[("draft_position", abbreviation)] = VocabularyFact(
            "draft_position", abbreviation, name, abbreviation
        )

    def _project_draft_pick(self, data: dict[str, object]) -> None:
        """Project linked college-athlete and NFL-team identities from a pick."""
        athlete_id = _optional_int(data.get("college_athlete_id"))
        athlete_name = _optional_string(data.get("name"))
        if athlete_id is not None and athlete_name is not None:
            opaque_id = str(athlete_id)
            self.athletes.setdefault(
                opaque_id,
                AthleteFact(
                    opaque_id,
                    athlete_name,
                    _optional_string(data.get("position")),
                ),
            )
        college_id = _optional_int(data.get("college_id"))
        college_name = _optional_string(data.get("college_team"))
        if college_id is not None and college_name is not None:
            self.teams.setdefault(
                college_id, TeamFact(college_id, college_name, None, None)
            )
        nfl_athlete_id = _optional_int(data.get("nfl_athlete_id"))
        if nfl_athlete_id is not None and athlete_name is not None:
            identity = str(nfl_athlete_id)
            self.vocabularies[("nfl_athlete", identity)] = VocabularyFact(
                "nfl_athlete", identity, athlete_name, None
            )
        team_id = _optional_int(data.get("nfl_team_id"))
        team_name = _optional_string(data.get("nfl_team"))
        if team_id is not None and team_name is not None:
            identity = str(team_id)
            self.vocabularies[("draft_team", identity)] = VocabularyFact(
                "draft_team", identity, team_name, None
            )


def project_catalog(
    *,
    endpoint: str,
    parameters: QueryParameters,
    value: BaseModel | list[BaseModel] | list[object],
    response_key: str,
    fetched_at: datetime,
    fresh_until: datetime,
    retained_until: datetime,
) -> CatalogProjection:
    """Return all typed identity facts and coverage from validated output."""
    builder = _ProjectionBuilder(parameters)
    builder.visit(value)
    if endpoint == "/stats/categories" and isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                builder.vocabularies[("stat_category", item)] = VocabularyFact(
                    "stat_category", item, item, None
                )
    row_count = len(value) if isinstance(value, list) else 1
    namespace, capabilities, known_cap = _coverage_capabilities(endpoint)
    status = (
        CoverageStatus.possibly_truncated
        if known_cap is not None and row_count >= known_cap
        else CoverageStatus.complete
    )
    canonical_filter_value = canonical_filters(parameters)
    coverage = CoverageRecord(
        partition_key=f"{endpoint}:{canonical_filter_value}",
        namespace=namespace,
        canonical_filters=canonical_filter_value,
        capabilities=capabilities,
        status=status,
        response_key=response_key,
        endpoint=endpoint,
        fetched_at=fetched_at,
        validated_at=fetched_at,
        fresh_until=fresh_until,
        retained_until=retained_until,
        row_count=row_count,
        known_cap=known_cap,
    )
    return CatalogProjection(
        teams=tuple(builder.teams.values()),
        team_seasons=tuple(builder.team_seasons.values()),
        conferences=tuple(builder.conferences.values()),
        affiliations=tuple(builder.affiliations.values()),
        venues=tuple(builder.venues.values()),
        games=tuple(builder.games.values()),
        athletes=tuple(builder.athletes.values()),
        athlete_team_seasons=tuple(builder.athlete_team_seasons.values()),
        recruits=tuple(builder.recruits.values()),
        coaches=tuple(builder.coaches.values()),
        coach_team_seasons=tuple(builder.coach_team_seasons.values()),
        drives=tuple(builder.drives.values()),
        plays=tuple(builder.plays.values()),
        vocabularies=tuple(builder.vocabularies.values()),
        playoff_matchups=tuple(builder.playoff_matchups.values()),
        coverage=coverage,
    )


def canonical_filters(parameters: QueryParameters) -> str:
    """Return bounded deterministic filters for the internal coverage ledger."""
    return "&".join(f"{key}={parameters[key]!r}" for key in sorted(parameters))


def _coverage_capabilities(endpoint: str) -> tuple[str, tuple[str, ...], int | None]:
    """Return namespace, proven facts, and known endpoint cap."""
    mapping: dict[str, tuple[str, tuple[str, ...], int | None]] = {
        "/teams": ("team", ("team.core_identity", "team.aliases"), None),
        "/teams/fbs": ("team", ("team.core_identity",), None),
        "/venues": ("venue", ("venue.identity",), None),
        "/conferences": ("conference", ("conference.identity",), None),
        "/conferences/affiliations": (
            "team",
            ("team.conference_history",),
            None,
        ),
        "/games": (
            "game",
            ("game.identity", "game.schedule", "game.team_relationships"),
            None,
        ),
        "/roster": (
            "athlete",
            ("athlete.identity", "athlete.team_season", "recruit.link"),
            None,
        ),
        "/player/search": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            100,
        ),
        "/plays/types": ("play_type", ("play_type.identity",), None),
        "/plays/stats/types": (
            "play_stat_type",
            ("play_stat_type.identity",),
            None,
        ),
        "/stats/categories": (
            "stat_category",
            ("stat_category.identity",),
            None,
        ),
        "/conferences/changes": (
            "team",
            ("team.core_identity", "team.conference_history"),
            None,
        ),
        "/teams/ats": ("team", ("team.core_identity",), None),
        "/records": ("team", ("team.core_identity",), None),
        "/rankings": ("team", ("team.core_identity",), None),
        "/wepa/team/season": ("team", ("team.core_identity",), None),
        "/games/media": ("game", ("game.identity",), None),
        "/games/weather": (
            "game",
            ("game.identity", "game.venue_relationship"),
            None,
        ),
        "/games/teams": (
            "game",
            ("game.identity", "game.team_relationships"),
            None,
        ),
        "/games/players": (
            "game",
            ("game.identity", "athlete.identity", "athlete.team_season"),
            None,
        ),
        "/scoreboard": (
            "game",
            ("game.identity", "game.team_relationships"),
            None,
        ),
        "/lines": (
            "game",
            ("game.identity", "game.team_relationships"),
            None,
        ),
        "/metrics/wp": (
            "play",
            ("game.identity", "play.identity", "game.team_relationships"),
            None,
        ),
        "/metrics/wp/pregame": ("game", ("game.identity",), None),
        "/ppa/games": ("game", ("game.identity",), None),
        "/stats/game/advanced": ("game", ("game.identity",), None),
        "/stats/game/havoc": ("game", ("game.identity",), None),
        "/stats/player/success/game": (
            "athlete",
            ("athlete.identity", "athlete.team_season", "game.identity"),
            None,
        ),
        "/plays": (
            "play",
            ("play.identity", "play.game_relationship", "drive.identity"),
            None,
        ),
        "/plays/stats": (
            "play",
            (
                "play.identity",
                "drive.identity",
                "athlete.identity",
                "athlete.team_season",
            ),
            None,
        ),
        "/drives": (
            "drive",
            ("drive.identity", "drive.game_relationship", "team.core_identity"),
            None,
        ),
        "/live/plays": (
            "game",
            (
                "game.identity",
                "game.team_relationships",
                "drive.identity",
                "play.identity",
                "team.core_identity",
                "play_type.identity",
            ),
            None,
        ),
        "/player/usage": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/player/season/overview": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/player/returning": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/stats/player/season": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/stats/player/success": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/ppa/players/games": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/ppa/players/season": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/wepa/players/passing": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/wepa/players/rushing": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/wepa/players/kicking": (
            "athlete",
            ("athlete.identity", "athlete.team_season"),
            None,
        ),
        "/recruiting/players": (
            "recruit",
            ("recruit.identity", "recruit.athlete_link"),
            None,
        ),
        "/coaches": (
            "coach",
            ("coach.identity", "coach.team_season"),
            None,
        ),
        "/coaches/profile": ("coach", ("coach.identity",), None),
        "/coaches/seasons": (
            "coach",
            ("coach.identity", "coach.team_season"),
            None,
        ),
        "/coaches/tenures": (
            "coach",
            ("coach.identity", "coach.tenure"),
            None,
        ),
        "/draft/picks": (
            "draft",
            ("athlete.identity", "team.core_identity", "draft.identity"),
            None,
        ),
        "/draft/teams": ("draft_team", ("draft_team.identity",), None),
        "/draft/positions": (
            "draft_position",
            ("draft_position.identity",),
            None,
        ),
        "/playoffs/cfp": (
            "playoff",
            ("playoff.matchup", "game.identity", "team.core_identity"),
            None,
        ),
        "/playoffs/cfp/games": (
            "playoff",
            ("playoff.matchup", "game.identity", "team.core_identity"),
            None,
        ),
        "/playoffs/cfp/participants": (
            "playoff",
            ("team.core_identity",),
            None,
        ),
    }
    return mapping.get(endpoint, (endpoint.strip("/").replace("/", "."), (), None))


def _optional_int(value: object) -> int | None:
    """Narrow an unknown validated field to a non-boolean integer."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_string(value: object) -> str | None:
    """Narrow an unknown validated field or string enum to text."""
    if isinstance(value, StrEnum):
        return str(value)
    return value if isinstance(value, str) and value else None


def _first_string(data: dict[str, object], *names: str) -> str | None:
    """Return the first non-empty string among known semantic field names."""
    for name in names:
        value = _optional_string(data.get(name))
        if value is not None:
            return value
    return None


def _nested_game_team_ids(data: dict[str, object]) -> tuple[int | None, int | None]:
    """Return home and away IDs from nested game-team rows."""
    home_team_id: int | None = None
    away_team_id: int | None = None
    teams = data.get("teams")
    if not isinstance(teams, list):
        return home_team_id, away_team_id
    for team in teams:
        if not isinstance(team, dict):
            continue
        side = _optional_string(team.get("home_away"))
        team_id = _optional_int(team.get("team_id"))
        if team_id is None or team_id <= 0:
            continue
        if side == "home":
            home_team_id = team_id
        elif side == "away":
            away_team_id = team_id
    return home_team_id, away_team_id


def _nested_int(value: object, name: str) -> int | None:
    """Return an integer from a validated nested model dump."""
    if isinstance(value, dict):
        return _optional_int(cast(dict[str, object], value).get(name))
    return None
