"""Encode canonical catalog merge evidence independently of storage backends."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime
from typing import Protocol, cast

from cfb_data._catalog.models import (
    AthleteFact,
    AthleteTeamSeasonFact,
    CatalogFact,
    CatalogObservation,
    CatalogProjection,
    CoachFact,
    CoachTeamSeasonFact,
    ConferenceAffiliationFact,
    ConferenceFact,
    DriveFact,
    FieldObservation,
    GameFact,
    ObservationState,
    ObservedValue,
    PlayFact,
    PlayoffMatchupFact,
    RecruitFact,
    TeamFact,
    TeamSeasonFact,
    VenueFact,
    VocabularyFact,
)
from cfb_data._catalog.projection import catalog_fact_key
from cfb_data.base.types import JSONValue, json_object
from cfb_data.errors import CFBDCacheBackendError

_FACT_TYPES: tuple[type[CatalogFact], ...] = (
    TeamFact,
    TeamSeasonFact,
    ConferenceFact,
    ConferenceAffiliationFact,
    VenueFact,
    GameFact,
    AthleteFact,
    AthleteTeamSeasonFact,
    RecruitFact,
    CoachFact,
    CoachTeamSeasonFact,
    DriveFact,
    PlayFact,
    VocabularyFact,
    PlayoffMatchupFact,
)
_FACT_NAMES = {fact_type.__name__: fact_type for fact_type in _FACT_TYPES}


class _FactConstructor(Protocol):
    """Construct a validated canonical fact from decoded field values."""

    def __call__(self, **values: object) -> CatalogFact:
        """Return one canonical fact."""
        ...


def projection_observations(
    projection: CatalogProjection,
    *,
    observed_at: datetime,
    source: str,
) -> tuple[CatalogObservation, ...]:
    """Return explicit observations, adapting direct test/backend fact batches."""
    if projection.observations:
        return projection.observations
    return tuple(
        _implicit_observation(fact, observed_at=observed_at, source=source)
        for fact in _projection_facts(projection)
    )


def projection_from_observations(
    observations: tuple[CatalogObservation, ...],
    *,
    original: CatalogProjection,
) -> CatalogProjection:
    """Build an explicit fact batch from already merged observations."""
    facts = tuple(observation.fact for observation in observations)
    return CatalogProjection(
        teams=tuple(fact for fact in facts if isinstance(fact, TeamFact)),
        team_seasons=tuple(fact for fact in facts if isinstance(fact, TeamSeasonFact)),
        conferences=tuple(fact for fact in facts if isinstance(fact, ConferenceFact)),
        affiliations=tuple(
            fact for fact in facts if isinstance(fact, ConferenceAffiliationFact)
        ),
        venues=tuple(fact for fact in facts if isinstance(fact, VenueFact)),
        games=tuple(fact for fact in facts if isinstance(fact, GameFact)),
        athletes=tuple(fact for fact in facts if isinstance(fact, AthleteFact)),
        athlete_team_seasons=tuple(
            fact for fact in facts if isinstance(fact, AthleteTeamSeasonFact)
        ),
        recruits=tuple(fact for fact in facts if isinstance(fact, RecruitFact)),
        coaches=tuple(fact for fact in facts if isinstance(fact, CoachFact)),
        coach_team_seasons=tuple(
            fact for fact in facts if isinstance(fact, CoachTeamSeasonFact)
        ),
        drives=tuple(fact for fact in facts if isinstance(fact, DriveFact)),
        plays=tuple(fact for fact in facts if isinstance(fact, PlayFact)),
        vocabularies=tuple(fact for fact in facts if isinstance(fact, VocabularyFact)),
        playoff_matchups=tuple(
            fact for fact in facts if isinstance(fact, PlayoffMatchupFact)
        ),
        observations=observations,
        coverage=original.coverage,
    )


def observation_storage_key(observation: CatalogObservation) -> tuple[str, str]:
    """Return the stable namespace and grain key for merge provenance."""
    namespace = type(observation.fact).__name__
    grain = json.dumps(
        [_json_value(value) for value in catalog_fact_key(observation.fact)],
        sort_keys=True,
        separators=(",", ":"),
    )
    return namespace, grain


def encode_catalog_observation(observation: CatalogObservation) -> str:
    """Serialize one typed canonical observation to bounded JSON text."""
    sources = sorted({field.source for field in observation.fields})
    source_indexes = {source: index for index, source in enumerate(sources)}
    timestamps = sorted({field.observed_at.isoformat() for field in observation.fields})
    timestamp_indexes = {timestamp: index for index, timestamp in enumerate(timestamps)}
    payload: dict[str, JSONValue] = {
        "v": 1,
        "t": type(observation.fact).__name__,
        "o": (
            observation.first_observed_at.isoformat()
            if observation.first_observed_at is not None
            else None
        ),
        "x": [
            _json_value(getattr(observation.fact, field.name))
            for field in fields(observation.fact)
        ],
        "s": cast(list[JSONValue], sources),
        "d": cast(list[JSONValue], timestamps),
        "e": [
            [
                str(field.value.state),
                _json_value(field.value.value),
                field.authority,
                source_indexes[field.source],
                timestamp_indexes[field.observed_at.isoformat()],
            ]
            for field in observation.fields
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def decode_catalog_observation(payload: str | bytes) -> CatalogObservation:
    """Validate and deserialize one stored canonical observation."""
    try:
        decoded = json_object(json.loads(payload))
        if _required_int(decoded, "v") != 1:
            raise ValueError("unsupported provenance version")
        fact_name = _required_text(decoded, "t")
        fact_type = _FACT_NAMES[fact_name]
        fact_fields = fields(fact_type)
        raw_fact = _required_array(decoded, "x")
        if len(raw_fact) != len(fact_fields):
            raise ValueError("fact values do not match the fact contract")
        fact_values = {
            field.name: _decode_fact_value(fact_type, field.name, raw_value)
            for field, raw_value in zip(fact_fields, raw_fact, strict=True)
        }
        constructor = cast(_FactConstructor, fact_type)
        fact = constructor(**fact_values)
        sources = _required_text_array(decoded, "s")
        raw_timestamps = _required_text_array(decoded, "d")
        timestamps = [datetime.fromisoformat(timestamp) for timestamp in raw_timestamps]
        raw_evidence = _required_array(decoded, "e")
        if len(raw_evidence) != len(fact_fields):
            raise ValueError("evidence does not match the fact contract")
        observations: list[FieldObservation] = []
        for fact_field, raw_item in zip(fact_fields, raw_evidence, strict=True):
            if not isinstance(raw_item, list) or len(raw_item) != 5:
                raise TypeError("field evidence must contain five values")
            raw_state, raw_value, authority, source_index, timestamp_index = raw_item
            if not isinstance(raw_state, str):
                raise TypeError("field state must be text")
            if isinstance(authority, bool) or not isinstance(authority, int):
                raise TypeError("field authority must be an integer")
            if isinstance(source_index, bool) or not isinstance(source_index, int):
                raise TypeError("field source index must be an integer")
            if isinstance(timestamp_index, bool) or not isinstance(
                timestamp_index, int
            ):
                raise TypeError("field timestamp index must be an integer")
            state = ObservationState(raw_state)
            value = _decode_fact_value(
                fact_type,
                fact_field.name,
                raw_value,
            )
            observations.append(
                FieldObservation(
                    field=fact_field.name,
                    value=ObservedValue(state, value),
                    authority=authority,
                    source=sources[source_index],
                    observed_at=timestamps[timestamp_index],
                )
            )
        first_observed_at = decoded.get("o")
        if first_observed_at is not None and not isinstance(first_observed_at, str):
            raise TypeError("first observation time must be text or null")
        return CatalogObservation(
            fact,
            tuple(observations),
            (
                datetime.fromisoformat(first_observed_at)
                if first_observed_at is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CFBDCacheBackendError("Catalog merge provenance is corrupt") from exc


def _implicit_observation(
    fact: CatalogFact, *, observed_at: datetime, source: str
) -> CatalogObservation:
    """Adapt direct fact batches to sparse source observations."""
    evidence: list[FieldObservation] = []
    for field in fields(fact):
        value = getattr(fact, field.name)
        observed = value is not None
        if (
            isinstance(fact, CoachTeamSeasonFact)
            and field.name == "end_year"
            and fact.tenure_id is None
        ):
            observed = False
        state = ObservationState.value if observed else ObservationState.unobserved
        evidence.append(
            FieldObservation(
                field=field.name,
                value=ObservedValue(state, value),
                authority=1 if observed else 0,
                source=source,
                observed_at=observed_at,
            )
        )
    return CatalogObservation(fact, tuple(evidence), observed_at)


def _projection_facts(projection: CatalogProjection) -> tuple[CatalogFact, ...]:
    """Flatten all explicit catalog collections without losing their types."""
    return cast(
        tuple[CatalogFact, ...],
        (
            *projection.teams,
            *projection.team_seasons,
            *projection.conferences,
            *projection.affiliations,
            *projection.venues,
            *projection.games,
            *projection.athletes,
            *projection.athlete_team_seasons,
            *projection.recruits,
            *projection.coaches,
            *projection.coach_team_seasons,
            *projection.drives,
            *projection.plays,
            *projection.vocabularies,
            *projection.playoff_matchups,
        ),
    )


def _json_value(value: object) -> JSONValue:
    """Convert one canonical scalar into its JSON representation."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")


def _decode_fact_value(
    fact_type: type[CatalogFact], field_name: str, value: object
) -> object:
    """Restore canonical tuple and datetime values from JSON scalars."""
    if fact_type is TeamFact and field_name == "alternate_names":
        if value is None:
            return None
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise TypeError("team aliases must be an array of strings")
        return tuple(value)
    if fact_type is GameFact and field_name == "start_date":
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("game start date must be text")
        return datetime.fromisoformat(value)
    return value


def _required_text(payload: dict[str, JSONValue], field: str) -> str:
    """Return one required text field from stored provenance."""
    value = payload.get(field)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    return value


def _required_array(payload: dict[str, JSONValue], field: str) -> list[JSONValue]:
    """Return one required array field from stored provenance."""
    value = payload.get(field)
    if not isinstance(value, list):
        raise TypeError(f"{field} must be an array")
    return value


def _required_text_array(payload: dict[str, JSONValue], field: str) -> list[str]:
    """Return one required text-only array from stored provenance."""
    value = _required_array(payload, field)
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field} must contain text")
    return cast(list[str], value)


def _required_int(payload: dict[str, JSONValue], field: str) -> int:
    """Return one required integer field from stored provenance."""
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value
