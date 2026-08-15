"""Define canonical identity observations and durable catalog grains."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CoverageStatus(StrEnum):
    """Describe whether a validated partition proves complete coverage."""

    complete = "complete"
    partial = "partial"
    possibly_truncated = "possibly_truncated"


class ObservationState(StrEnum):
    """Distinguish absence, an explicit null, and a concrete value."""

    unobserved = "unobserved"
    null = "null"
    value = "value"


@dataclass(frozen=True, slots=True)
class ObservedValue[ValueT]:
    """Carry one canonical value with explicit presence semantics."""

    state: ObservationState
    value: ValueT | None = None

    @classmethod
    def unobserved(cls) -> ObservedValue[ValueT]:
        """Return a value that the source did not establish."""
        return cls(ObservationState.unobserved)

    @classmethod
    def null(cls) -> ObservedValue[ValueT]:
        """Return a value that the source authoritatively observed as null."""
        return cls(ObservationState.null)

    @classmethod
    def of(cls, value: ValueT) -> ObservedValue[ValueT]:
        """Return a concrete observed value."""
        return cls(ObservationState.value, value)


@dataclass(frozen=True, slots=True)
class TeamFact:
    """Store the durable core identity for one team."""

    id: int
    school: str
    abbreviation: str | None = None
    alternate_names: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TeamSeasonFact:
    """Store one time-varying team relationship snapshot."""

    team_id: int
    season: int
    conference_name: str | None = None
    venue_id: int | None = None


@dataclass(frozen=True, slots=True)
class ConferenceFact:
    """Store the durable core identity for one conference."""

    id: int
    name: str
    abbreviation: str | None = None
    classification: str | None = None


@dataclass(frozen=True, slots=True)
class ConferenceAffiliationFact:
    """Store a historical team-to-conference validity interval."""

    team_id: int
    conference_id: int
    start_year: int
    end_year: int | None = None


@dataclass(frozen=True, slots=True)
class VenueFact:
    """Store the durable core identity for one venue."""

    id: int
    name: str
    city: str | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class GameFact:
    """Store one game partition and its stable relationships."""

    id: int
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    start_date: datetime | None = None
    status: str | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    venue_id: int | None = None


@dataclass(frozen=True, slots=True)
class AthleteFact:
    """Store the durable core identity for one athlete."""

    id: str
    name: str
    position: str | None = None


@dataclass(frozen=True, slots=True)
class AthleteTeamSeasonFact:
    """Store one athlete membership at a team-season grain."""

    athlete_id: str
    team_name: str
    season: int


@dataclass(frozen=True, slots=True)
class RecruitFact:
    """Store one recruiting identity with optional athlete and class links."""

    id: str
    athlete_id: str | None
    name: str
    year: int | None


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
    offense_team_id: int | None = None
    offense_team: str | None = None
    defense_team_id: int | None = None
    defense_team: str | None = None


@dataclass(frozen=True, slots=True)
class PlayFact:
    """Store one play and its game, drive, and type relationships."""

    id: str
    game_id: int
    drive_id: str | None = None
    play_type_id: int | None = None
    play_type: str | None = None


@dataclass(frozen=True, slots=True)
class VocabularyFact:
    """Store one enumerated provider vocabulary item."""

    namespace: str
    id: str
    name: str
    abbreviation: str | None = None


@dataclass(frozen=True, slots=True)
class PlayoffMatchupFact:
    """Store one playoff matchup and its linked game."""

    id: int
    season: int | None = None
    linked_game_id: int | None = None


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
    projection_contract: str = "source-model-projection:v1"


@dataclass(frozen=True, slots=True)
class FieldObservation:
    """Describe one source-owned observation of a canonical field."""

    field: str
    value: ObservedValue[object]
    authority: int
    source: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogObservation:
    """Carry typed fact values and their field-level merge evidence."""

    fact: CatalogFact
    fields: tuple[FieldObservation, ...]
    first_observed_at: datetime | None = None


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
    observations: tuple[CatalogObservation, ...] = ()
    coverage: CoverageRecord | None = None


@dataclass(frozen=True, slots=True)
class CatalogCounts:
    """Report stored rows for every canonical entity and relationship grain."""

    teams: int = 0
    team_seasons: int = 0
    conferences: int = 0
    affiliations: int = 0
    venues: int = 0
    games: int = 0
    athletes: int = 0
    athlete_team_seasons: int = 0
    recruits: int = 0
    coaches: int = 0
    coach_team_seasons: int = 0
    drives: int = 0
    plays: int = 0
    vocabularies: int = 0
    playoff_matchups: int = 0


type CatalogFact = (
    TeamFact
    | TeamSeasonFact
    | ConferenceFact
    | ConferenceAffiliationFact
    | VenueFact
    | GameFact
    | AthleteFact
    | AthleteTeamSeasonFact
    | RecruitFact
    | CoachFact
    | CoachTeamSeasonFact
    | DriveFact
    | PlayFact
    | VocabularyFact
    | PlayoffMatchupFact
)
