"""Provide a transient catalog when response persistence is disabled."""

from __future__ import annotations

import unicodedata
from dataclasses import fields, replace
from datetime import datetime
from typing import TYPE_CHECKING, Self, cast

from cfb_data._catalog.merge import merge_catalog_observations
from cfb_data._catalog.models import (
    AthleteFact,
    AthleteTeamSeasonFact,
    CatalogCounts,
    CatalogFact,
    CatalogObservation,
    CatalogProjection,
    CoachFact,
    CoachTeamSeasonFact,
    ConferenceAffiliationFact,
    ConferenceFact,
    CoverageRecord,
    DriveFact,
    GameFact,
    PlayFact,
    PlayoffMatchupFact,
    RecruitFact,
    TeamFact,
    TeamSeasonFact,
    VenueFact,
    VocabularyFact,
)
from cfb_data._catalog.projection import catalog_fact_key
from cfb_data._catalog.sources import projection_contract
from cfb_data.cache._catalog_codecs import (
    projection_from_observations,
    projection_observations,
)
from cfb_data.cache._identity_codecs import (
    athlete_identity,
    conference_identity,
    game_identity,
    team_identity,
    venue_identity,
)
from cfb_data.cache._models import ResponsePeek, ResponsePeekStatus, ResponseRecord

if TYPE_CHECKING:
    from cfb_data.conferences.models.pydantic.identity import ConferenceIdentity
    from cfb_data.games.models.pydantic.identity import GameIdentity
    from cfb_data.players.models.pydantic.identity import AthleteIdentity
    from cfb_data.teams.models.pydantic.identity import TeamIdentity
    from cfb_data.venues.models.pydantic.identity import VenueIdentity


class NullCacheBackend:
    """Keep projected identities in memory while discarding response bodies."""

    def __init__(self) -> None:
        """Initialize an empty process-local catalog."""
        self._facts: dict[type[object], dict[tuple[object, ...], CatalogFact]] = {}
        self._observations: dict[
            type[object], dict[tuple[object, ...], CatalogObservation]
        ] = {}
        self._coverage: dict[tuple[str, str], CoverageRecord] = {}
        self._open = False

    async def open(self) -> Self:
        """Open the process-local catalog."""
        self._open = True
        return self

    async def close(self) -> None:
        """Close and clear the process-local catalog."""
        self._open = False
        self._facts.clear()
        self._observations.clear()
        self._coverage.clear()

    async def get_response(self, key: str, now: datetime) -> ResponseRecord | None:
        """Return no persisted response record."""
        return None

    async def peek_response(self, key: str, now: datetime) -> ResponsePeek:
        """Report that disabled response persistence has no record."""
        return ResponsePeek(ResponsePeekStatus.missing)

    async def commit_response(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> CatalogProjection:
        """Merge canonical facts and coverage while discarding response bytes."""
        self._require_open()
        merged_observations: tuple[CatalogObservation, ...] = ()
        if projection.observations:
            merged_observations = tuple(
                self._merge_observation(observation)
                for observation in projection.observations
            )
        else:
            for collection in (
                projection.teams,
                projection.team_seasons,
                projection.conferences,
                projection.affiliations,
                projection.venues,
                projection.games,
                projection.athletes,
                projection.athlete_team_seasons,
                projection.recruits,
                projection.coaches,
                projection.coach_team_seasons,
                projection.drives,
                projection.plays,
                projection.vocabularies,
                projection.playoff_matchups,
            ):
                for fact in collection:
                    self._merge(fact)
        if projection.coverage is not None:
            coverage = projection.coverage
            self._coverage[(coverage.endpoint, coverage.canonical_filters)] = coverage
        if not merged_observations:
            return projection
        return projection_from_observations(
            merged_observations,
            original=projection,
        )

    async def merge_catalog_projection(
        self, record: ResponseRecord, projection: CatalogProjection
    ) -> CatalogProjection:
        """Merge a projection with current observations without writing it."""
        candidates = projection_observations(
            projection,
            observed_at=record.fetched_at,
            source=record.endpoint,
        )
        merged = tuple(
            merge_catalog_observations(
                self._observations.get(type(candidate.fact), {}).get(
                    catalog_fact_key(candidate.fact)
                ),
                candidate,
            )
            for candidate in candidates
        )
        return projection_from_observations(merged, original=projection)

    async def has_current_projection(
        self, *, endpoint: str, canonical_filters: str
    ) -> bool:
        """Return whether transient coverage uses the current contract."""
        coverage = self._coverage.get((endpoint, canonical_filters))
        return bool(
            coverage is not None
            and coverage.projection_contract == projection_contract(endpoint)
        )

    async def delete_response(self, key: str) -> None:
        """Delete no response because response bytes are never retained."""

    async def cleanup_responses(self, now: datetime) -> int:
        """Report that no response records were removed."""
        return 0

    async def has_fresh_coverage(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        capability: str,
        now: datetime,
    ) -> bool:
        """Return whether transient complete coverage proves a capability."""
        coverage = self._coverage.get((endpoint, canonical_filters))
        return bool(
            coverage is not None
            and coverage.status == "complete"
            and coverage.fresh_until > now
            and capability in coverage.capabilities
            and coverage.projection_contract == projection_contract(endpoint)
        )

    async def record_coverage_failure(
        self,
        *,
        endpoint: str,
        canonical_filters: str,
        failure_category: str,
        failed_at: datetime,
    ) -> None:
        """Discard transient failure metadata."""

    async def acquire_lease(
        self, key: str, owner_token: str, expires_at: datetime, now: datetime
    ) -> bool:
        """Grant a process-local no-op lease."""
        return True

    async def renew_lease(
        self, key: str, owner_token: str, expires_at: datetime
    ) -> bool:
        """Renew a process-local no-op lease."""
        return True

    async def release_lease(self, key: str, owner_token: str) -> bool:
        """Release a process-local no-op lease."""
        return True

    async def find_teams(self, query: str | int) -> list[TeamIdentity]:
        """Return exact provider-ID, school, abbreviation, or alias matches."""
        facts = self._values(TeamFact)
        return [
            team_identity(
                id=fact.id,
                school=fact.school,
                abbreviation=fact.abbreviation,
                alternate_names=fact.alternate_names or (),
            )
            for fact in facts
            if _identity_match(
                query,
                fact.id,
                fact.school,
                fact.abbreviation,
                *(fact.alternate_names or ()),
            )
        ]

    async def find_conferences(self, query: str | int) -> list[ConferenceIdentity]:
        """Return exact provider-ID, name, or abbreviation matches."""
        return [
            conference_identity(
                id=fact.id,
                name=fact.name,
                abbreviation=fact.abbreviation,
                classification=fact.classification,
            )
            for fact in self._values(ConferenceFact)
            if _identity_match(query, fact.id, fact.name, fact.abbreviation)
        ]

    async def find_venues(self, query: str | int) -> list[VenueIdentity]:
        """Return exact provider-ID or canonical-name matches."""
        return [
            venue_identity(
                id=fact.id,
                name=fact.name,
                city=fact.city,
                state=fact.state,
            )
            for fact in self._values(VenueFact)
            if _identity_match(query, fact.id, fact.name)
        ]

    async def find_game(self, game_id: int) -> GameIdentity | None:
        """Return one game identity by provider ID."""
        fact = self._facts.get(GameFact, {}).get((game_id,))
        return _game_view(cast(GameFact, fact)) if fact is not None else None

    async def find_games(
        self, *, season: int, week: int | None, team: str | None
    ) -> list[GameIdentity]:
        """Return games matching an explicit season partition."""
        team_ids = (
            {match.id for match in await self.find_teams(team)}
            if team is not None
            else set()
        )
        if team is not None and not team_ids:
            return []
        facts = [
            fact
            for fact in self._values(GameFact)
            if fact.season == season
            and (week is None or fact.week == week)
            and (
                team is None
                or fact.home_team_id in team_ids
                or fact.away_team_id in team_ids
            )
        ]
        facts.sort(
            key=lambda fact: (
                fact.start_date.isoformat() if fact.start_date else "",
                fact.id,
            )
        )
        return [_game_view(fact) for fact in facts]

    async def find_athletes(
        self, *, name: str, team: str | None, season: int | None
    ) -> list[AthleteIdentity]:
        """Return exact athlete matches within optional team-season scope."""
        memberships = self._values(AthleteTeamSeasonFact)
        results: list[AthleteIdentity] = []
        for fact in self._values(AthleteFact):
            if _normalize(fact.name) != _normalize(name):
                continue
            matching = [
                membership
                for membership in memberships
                if membership.athlete_id == fact.id
                and (
                    team is None or _normalize(membership.team_name) == _normalize(team)
                )
                and (season is None or membership.season == season)
            ]
            if (team is not None or season is not None) and not matching:
                continue
            if not matching:
                results.append(
                    athlete_identity(
                        id=fact.id,
                        name=fact.name,
                        position=fact.position,
                    )
                )
            else:
                results.extend(
                    athlete_identity(
                        id=fact.id,
                        name=fact.name,
                        position=fact.position,
                        team=membership.team_name,
                        season=membership.season,
                    )
                    for membership in matching
                )
        return results

    async def catalog_counts(self) -> CatalogCounts:
        """Return row counts for every transient canonical grain."""
        return CatalogCounts(
            teams=len(self._values(TeamFact)),
            team_seasons=len(self._values(TeamSeasonFact)),
            conferences=len(self._values(ConferenceFact)),
            affiliations=len(self._values(ConferenceAffiliationFact)),
            venues=len(self._values(VenueFact)),
            games=len(self._values(GameFact)),
            athletes=len(self._values(AthleteFact)),
            athlete_team_seasons=len(self._values(AthleteTeamSeasonFact)),
            recruits=len(self._values(RecruitFact)),
            coaches=len(self._values(CoachFact)),
            coach_team_seasons=len(self._values(CoachTeamSeasonFact)),
            drives=len(self._values(DriveFact)),
            plays=len(self._values(PlayFact)),
            vocabularies=len(self._values(VocabularyFact)),
            playoff_matchups=len(self._values(PlayoffMatchupFact)),
        )

    def _merge(self, fact: CatalogFact) -> None:
        """Merge sparse facts without erasing previously observed values."""
        collection = self._facts.setdefault(type(fact), {})
        key = catalog_fact_key(fact)
        existing = collection.get(key)
        if existing is None:
            collection[key] = fact
            return
        values = {
            field.name: (
                getattr(fact, field.name)
                if getattr(fact, field.name) is not None
                else getattr(existing, field.name)
            )
            for field in fields(fact)
        }
        collection[key] = replace(existing, **values)

    def _merge_observation(self, candidate: CatalogObservation) -> CatalogObservation:
        """Merge one fact through the backend-neutral precedence contract."""
        fact_type = type(candidate.fact)
        key = catalog_fact_key(candidate.fact)
        collection = self._observations.setdefault(fact_type, {})
        merged = merge_catalog_observations(collection.get(key), candidate)
        collection[key] = merged
        self._facts.setdefault(fact_type, {})[key] = merged.fact
        return merged

    def _values[FactT: CatalogFact](self, fact_type: type[FactT]) -> list[FactT]:
        """Return transient facts of one type in stable key order."""
        collection = self._facts.get(fact_type, {})
        return [
            cast(FactT, fact)
            for _, fact in sorted(collection.items(), key=lambda item: repr(item[0]))
        ]

    def _require_open(self) -> None:
        """Reject operations outside the backend lifecycle."""
        if not self._open:
            raise RuntimeError("Transient identity catalog is not open")


def _normalize(value: str) -> str:
    """Return the catalog's exact Unicode-aware search representation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _identity_match(query: str | int, identifier: int, *names: str | None) -> bool:
    """Match a provider ID before normalized exact identity names."""
    if isinstance(query, int):
        return query == identifier
    normalized = _normalize(query)
    return any(name is not None and _normalize(name) == normalized for name in names)


def _game_view(fact: GameFact) -> GameIdentity:
    """Build one domain-owned game identity from canonical values."""
    return game_identity(
        id=fact.id,
        season=fact.season,
        week=fact.week,
        season_type=fact.season_type,
        start_date=fact.start_date,
        status=fact.status,
        home_team_id=fact.home_team_id,
        away_team_id=fact.away_team_id,
        venue_id=fact.venue_id,
    )
