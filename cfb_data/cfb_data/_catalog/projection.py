"""Compile source-owned projection metadata into canonical catalog facts."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import pkgutil
import re
from dataclasses import MISSING, dataclass, fields, replace
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel

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
    ObservedValue,
    PlayFact,
    PlayoffMatchupFact,
    RecruitFact,
    TeamFact,
    TeamSeasonFact,
    VenueFact,
    VocabularyFact,
)
from cfb_data.base.types import QueryParameters


class ObservationAuthority(StrEnum):
    """Rank how completely one source establishes a canonical value."""

    sparse = "sparse"
    canonical = "canonical"
    authoritative = "authoritative"


_AUTHORITY_RANK = {
    ObservationAuthority.sparse: 1,
    ObservationAuthority.canonical: 2,
    ObservationAuthority.authoritative: 3,
}


class PresencePolicy(StrEnum):
    """Describe how a null source value affects canonical state."""

    sparse = "sparse"
    authoritative = "authoritative"


class ValueTransform(StrEnum):
    """Name a deterministic conversion from one validated source value."""

    identity = "identity"
    positive_int = "positive_int"
    nonempty_text = "nonempty_text"
    enum_text = "enum_text"
    aliases = "aliases"
    integer_text = "integer_text"
    completed_status = "completed_status"


@dataclass(frozen=True, slots=True)
class _ProjectionField:
    """Map one validated source field to one canonical fact attribute."""

    fact_type: type[CatalogFact]
    target: str
    binding: str = "self"
    transform: ValueTransform = ValueTransform.identity
    authority: ObservationAuthority = ObservationAuthority.sparse
    presence: PresencePolicy = PresencePolicy.sparse


@dataclass(frozen=True, slots=True)
class IdentityKey(_ProjectionField):
    """Declare a source field as an entity key."""


@dataclass(frozen=True, slots=True)
class IdentityAttribute(_ProjectionField):
    """Declare a source field as a canonical entity attribute."""


@dataclass(frozen=True, slots=True)
class RelationshipKey(_ProjectionField):
    """Declare a source field as part of a canonical relationship."""


@dataclass(frozen=True, slots=True)
class NonCatalogId:
    """Explain why an identifier-shaped source field is not catalog identity."""

    reason: str


@dataclass(frozen=True, slots=True)
class ProjectionContext:
    """Carry validated request and ancestor context through recursive projection."""

    endpoint: str
    parameters: QueryParameters
    observed_at: datetime
    ancestors: tuple[BaseModel, ...] = ()

    def parent(self, model_type: type[BaseModel]) -> BaseModel | None:
        """Return the nearest ancestor of ``model_type`` if one exists."""
        return next(
            (
                ancestor
                for ancestor in reversed(self.ancestors)
                if isinstance(ancestor, model_type)
            ),
            None,
        )


@runtime_checkable
class CatalogProjectable(Protocol):
    """Allow a source model to emit contextual canonical observations."""

    def _project_catalog(self, context: ProjectionContext, sink: CatalogSink) -> None:
        """Add this model's contextual observations to ``sink``."""
        ...


class _FactConstructor(Protocol):
    """Construct a canonical fact from compiler-validated field values."""

    def __call__(self, **values: object) -> CatalogFact:
        """Return one canonical fact."""
        ...


@dataclass(slots=True)
class _FactState:
    """Track field-level authority while merging one projection batch."""

    fact: CatalogFact
    authority: dict[str, tuple[int, str]]


class CatalogSink:
    """Accumulate and deterministically merge canonical catalog facts."""

    def __init__(self, observed_at: datetime) -> None:
        """Initialize an empty canonical observation batch."""
        self._facts: dict[type[object], dict[tuple[object, ...], _FactState]] = {}
        self._contract_parts: set[str] = set()
        self._observed_at = observed_at

    def add(
        self,
        fact: CatalogFact,
        *,
        authority: ObservationAuthority = ObservationAuthority.sparse,
        source: str,
        observed_fields: frozenset[str] | None = None,
    ) -> None:
        """Merge one fact using field authority and a stable source tie-break."""
        fact_type = type(fact)
        key = catalog_fact_key(fact)
        observed = observed_fields or frozenset(
            field.name
            for field in fields(fact)
            if getattr(fact, field.name) is not None
        )
        rank = _AUTHORITY_RANK[authority]
        collection = self._facts.setdefault(fact_type, {})
        state = collection.get(key)
        if state is None:
            collection[key] = _FactState(
                fact=fact,
                authority={name: (rank, source) for name in observed},
            )
            return
        values = {field.name: getattr(state.fact, field.name) for field in fields(fact)}
        changed = False
        for name in observed:
            candidate = (rank, source)
            current = state.authority.get(name, (0, ""))
            if candidate >= current:
                values[name] = getattr(fact, name)
                state.authority[name] = candidate
                changed = True
        if changed:
            state.fact = replace(state.fact, **values)

    def note_contract(self, part: str) -> None:
        """Include one stable source-owned declaration in the contract digest."""
        self._contract_parts.add(part)

    def add_projection(
        self,
        projection: CatalogProjection,
        *,
        authority: ObservationAuthority,
        source: str,
    ) -> None:
        """Merge every fact from one already typed projection."""
        if projection.observations:
            authorities = {
                rank: authority for authority, rank in _AUTHORITY_RANK.items()
            }
            for observation in projection.observations:
                for field in observation.fields:
                    if field.authority == 0:
                        continue
                    self.add(
                        observation.fact,
                        authority=authorities[field.authority],
                        source=field.source,
                        observed_fields=frozenset((field.field,)),
                    )
            return
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
                self.add(fact, authority=authority, source=source)

    def projection(self) -> CatalogProjection:
        """Return the merged facts without endpoint coverage."""
        return CatalogProjection(
            teams=self._values(TeamFact),
            team_seasons=self._values(TeamSeasonFact),
            conferences=self._values(ConferenceFact),
            affiliations=self._values(ConferenceAffiliationFact),
            venues=self._values(VenueFact),
            games=self._values(GameFact),
            athletes=self._values(AthleteFact),
            athlete_team_seasons=self._values(AthleteTeamSeasonFact),
            recruits=self._values(RecruitFact),
            coaches=self._values(CoachFact),
            coach_team_seasons=self._values(CoachTeamSeasonFact),
            drives=self._values(DriveFact),
            plays=self._values(PlayFact),
            vocabularies=self._values(VocabularyFact),
            playoff_matchups=self._values(PlayoffMatchupFact),
            observations=self._observations(),
        )

    def contract_digest(self) -> str:
        """Return a deterministic digest of declarations exercised by the batch."""
        encoded = json.dumps(sorted(self._contract_parts), separators=(",", ":"))
        return (
            f"source-model-projection:v1:{hashlib.sha256(encoded.encode()).hexdigest()}"
        )

    def _values[FactT: CatalogFact](self, fact_type: type[FactT]) -> tuple[FactT, ...]:
        """Return facts of one canonical type in deterministic key order."""
        collection = self._facts.get(fact_type, {})
        return tuple(
            cast(FactT, state.fact)
            for _, state in sorted(collection.items(), key=lambda item: repr(item[0]))
        )

    def _observations(self) -> tuple[CatalogObservation, ...]:
        """Return explicit three-state observations for every canonical fact."""
        observations: list[CatalogObservation] = []
        for collection in self._facts.values():
            for state in collection.values():
                field_observations: list[FieldObservation] = []
                for field in fields(state.fact):
                    evidence = state.authority.get(field.name)
                    value = getattr(state.fact, field.name)
                    if evidence is None:
                        observed = ObservedValue[object].unobserved()
                        rank, source = 0, ""
                    elif value is None:
                        observed = ObservedValue[object].null()
                        rank, source = evidence
                    else:
                        observed = ObservedValue[object].of(value)
                        rank, source = evidence
                    field_observations.append(
                        FieldObservation(
                            field=field.name,
                            value=observed,
                            authority=rank,
                            source=source,
                            observed_at=self._observed_at,
                        )
                    )
                observations.append(
                    CatalogObservation(
                        state.fact,
                        tuple(field_observations),
                        self._observed_at,
                    )
                )
        return tuple(
            sorted(
                observations,
                key=lambda observation: (
                    type(observation.fact).__name__,
                    repr(catalog_fact_key(observation.fact)),
                ),
            )
        )


def project_models(
    value: BaseModel | list[BaseModel] | list[object],
    *,
    endpoint: str,
    parameters: QueryParameters,
    observed_at: datetime,
) -> tuple[CatalogProjection, str]:
    """Project validated models through metadata and colocated typed hooks."""
    sink = CatalogSink(observed_at)
    _visit(
        value,
        ProjectionContext(
            endpoint=endpoint,
            parameters=parameters,
            observed_at=observed_at,
        ),
        sink,
    )
    return sink.projection(), sink.contract_digest()


def compile_model_declarations(*model_types: type[BaseModel]) -> str:
    """Validate source declarations and return their deterministic digest.

    :param model_types: Actual Pydantic model classes that own declarations.
    :return: A digest covering typed fields and contextual hooks.
    :raises TypeError: If a declaration targets an incompatible fact definition.
    :raises ValueError: If a target or authority declaration conflicts.
    """
    parts: set[str] = set()
    for model_type in model_types:
        declarations: dict[tuple[type[CatalogFact], str, str], _ProjectionField] = {}
        for field_name, field_info in model_type.model_fields.items():
            for metadata in field_info.metadata:
                if isinstance(metadata, NonCatalogId):
                    if not metadata.reason.strip():
                        raise ValueError("NonCatalogId requires a reason")
                    parts.add(
                        f"non-catalog:{model_type.__module__}."
                        f"{model_type.__qualname__}:{field_name}:{metadata.reason}"
                    )
                    continue
                if not isinstance(metadata, _ProjectionField):
                    continue
                fact_fields = {field.name for field in fields(metadata.fact_type)}
                if metadata.target not in fact_fields:
                    raise ValueError(
                        f"{model_type.__qualname__}.{field_name} targets missing "
                        f"{metadata.fact_type.__name__}.{metadata.target}"
                    )
                key = (metadata.fact_type, metadata.binding, metadata.target)
                previous = declarations.get(key)
                if previous is not None and previous != metadata:
                    raise ValueError(
                        f"Conflicting catalog declarations for "
                        f"{model_type.__qualname__}.{field_name}"
                    )
                declarations[key] = metadata
                parts.add(
                    ":".join(
                        (
                            "field",
                            model_type.__module__,
                            model_type.__qualname__,
                            field_name,
                            type(metadata).__name__,
                            metadata.fact_type.__module__,
                            metadata.fact_type.__qualname__,
                            metadata.target,
                            metadata.binding,
                            metadata.transform,
                            metadata.authority,
                            metadata.presence,
                        )
                    )
                )
        if issubclass(model_type, CatalogProjectable):
            hook = model_type.__dict__.get("_project_catalog")
            if hook is not None:
                hook_source = inspect.getsource(hook)
                hook_digest = hashlib.sha256(hook_source.encode()).hexdigest()
                parts.add(
                    f"hook:{model_type.__module__}.{model_type.__qualname__}:"
                    f"{hook_digest}"
                )
    encoded = json.dumps(sorted(parts), separators=(",", ":"))
    return f"source-model-projection:v1:{hashlib.sha256(encoded.encode()).hexdigest()}"


@lru_cache(maxsize=1)
def runtime_projection_contract_digest() -> str:
    """Return a digest of every source-response declaration and hook."""
    model_types = response_model_types()
    validate_response_model_completeness(*model_types)
    return compile_model_declarations(*model_types)


@lru_cache(maxsize=1)
def response_model_types() -> tuple[type[BaseModel], ...]:
    """Import and return every source response model in deterministic order."""
    import cfb_data

    for module in pkgutil.walk_packages(cfb_data.__path__, prefix="cfb_data."):
        if module.name.endswith(".models.pydantic.responses"):
            importlib.import_module(module.name)
    return tuple(
        sorted(
            (
                model_type
                for model_type in _model_subclasses(BaseModel)
                if model_type.__module__.startswith("cfb_data.")
                and ".models.pydantic.responses" in model_type.__module__
            ),
            key=lambda model_type: (
                model_type.__module__,
                model_type.__qualname__,
            ),
        )
    )


def validate_response_model_completeness(
    *model_types: type[BaseModel],
) -> None:
    """Reject identifier fields lacking metadata or typed hook ownership.

    :param model_types: Reachable source response models to classify.
    :raises ValueError: If an identifier-shaped field has no source-owned meaning.
    """
    missing: list[str] = []
    for model_type in model_types:
        hook = getattr(model_type, "_project_catalog", None)
        hook_source = inspect.getsource(hook) if hook is not None else ""
        for field_name, field_info in model_type.model_fields.items():
            if not _identifier_shaped(field_name):
                continue
            if any(
                isinstance(
                    metadata,
                    IdentityKey | IdentityAttribute | RelationshipKey | NonCatalogId,
                )
                for metadata in field_info.metadata
            ):
                continue
            if re.search(rf"\bself\.{re.escape(field_name)}\b", hook_source):
                continue
            missing.append(
                f"{model_type.__module__}.{model_type.__qualname__}.{field_name}"
            )
    if missing:
        joined = ", ".join(sorted(missing))
        raise ValueError(f"Unclassified response identifier fields: {joined}")


def _identifier_shaped(field_name: str) -> bool:
    """Return whether a source field name represents a provider identifier."""
    return (
        field_name == "id" or field_name.endswith("_id") or field_name.endswith("_ids")
    )


def _model_subclasses(model_type: type[BaseModel]) -> set[type[BaseModel]]:
    """Return every currently loaded Pydantic subclass recursively."""
    discovered: set[type[BaseModel]] = set()
    pending = list(model_type.__subclasses__())
    while pending:
        candidate = pending.pop()
        if candidate in discovered:
            continue
        discovered.add(candidate)
        pending.extend(candidate.__subclasses__())
    return discovered


def observe_team(
    sink: CatalogSink,
    *,
    id: int,
    school: str,
    source: str,
    abbreviation: str | None = None,
    alternate_names: tuple[str, ...] | None = None,
    authority: ObservationAuthority = ObservationAuthority.sparse,
) -> None:
    """Add a valid provider team identity when its key and name are usable."""
    if id <= 0 or not school:
        return
    sink.add(
        TeamFact(id, school, abbreviation, alternate_names),
        authority=authority,
        source=source,
    )


def observe_game(
    sink: CatalogSink,
    *,
    id: int,
    source: str,
    season: int | None = None,
    week: int | None = None,
    season_type: StrEnum | str | None = None,
    start_date: object = None,
    status: StrEnum | str | None = None,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
    venue_id: int | None = None,
    authority: ObservationAuthority = ObservationAuthority.sparse,
    observed_fields: frozenset[str] | None = None,
) -> None:
    """Add a valid game and normalize placeholder relationships."""
    from datetime import datetime

    if id <= 0:
        return
    sink.add(
        GameFact(
            id=id,
            season=season,
            week=week,
            season_type=str(season_type) if season_type is not None else None,
            start_date=start_date if isinstance(start_date, datetime) else None,
            status=str(status) if status is not None else None,
            home_team_id=(home_team_id if home_team_id and home_team_id > 0 else None),
            away_team_id=(away_team_id if away_team_id and away_team_id > 0 else None),
            venue_id=venue_id if venue_id and venue_id > 0 else None,
        ),
        authority=authority,
        source=source,
        observed_fields=observed_fields,
    )


def observe_athlete(
    sink: CatalogSink,
    *,
    id: str,
    name: str,
    source: str,
    position: str | None = None,
    team: str | None = None,
    season: int | None = None,
    authority: ObservationAuthority = ObservationAuthority.sparse,
) -> None:
    """Add an athlete and an optional exact team-season membership."""
    if not id or not name:
        return
    sink.add(AthleteFact(id, name, position), authority=authority, source=source)
    if team and season is not None:
        sink.add(
            AthleteTeamSeasonFact(id, team, season),
            authority=authority,
            source=source,
        )


def _visit(value: object, context: ProjectionContext, sink: CatalogSink) -> None:
    """Visit typed model values recursively without dumping them to dictionaries."""
    if isinstance(value, list | tuple):
        for item in value:
            _visit(item, context, sink)
        return
    if not isinstance(value, BaseModel):
        return
    _project_metadata(value, sink)
    if isinstance(value, CatalogProjectable):
        sink.note_contract(
            f"hook:{type(value).__module__}.{type(value).__qualname__}:v1"
        )
        value._project_catalog(context, sink)
    nested_context = ProjectionContext(
        endpoint=context.endpoint,
        parameters=context.parameters,
        observed_at=context.observed_at,
        ancestors=(*context.ancestors, value),
    )
    for field_name in type(value).model_fields:
        nested = getattr(value, field_name)
        if isinstance(nested, BaseModel | list | tuple):
            _visit(nested, nested_context, sink)


def _project_metadata(model: BaseModel, sink: CatalogSink) -> None:
    """Compile ``Annotated`` field declarations attached to one source model."""
    grouped: dict[
        tuple[type[CatalogFact], str],
        tuple[dict[str, object], set[str], ObservationAuthority],
    ] = {}
    for field_name, field_info in type(model).model_fields.items():
        value = getattr(model, field_name)
        for metadata in field_info.metadata:
            if not isinstance(metadata, _ProjectionField):
                continue
            sink.note_contract(
                ":".join(
                    (
                        "field",
                        type(model).__module__,
                        type(model).__qualname__,
                        field_name,
                        type(metadata).__name__,
                        metadata.fact_type.__name__,
                        metadata.target,
                        metadata.binding,
                        metadata.transform,
                        metadata.authority,
                        metadata.presence,
                    )
                )
            )
            key = (metadata.fact_type, metadata.binding)
            values, observed, authority = grouped.setdefault(
                key, ({}, set(), metadata.authority)
            )
            transformed, is_observed = _transform(value, metadata)
            if is_observed:
                values[metadata.target] = transformed
                observed.add(metadata.target)
            if _AUTHORITY_RANK[metadata.authority] > _AUTHORITY_RANK[authority]:
                grouped[key] = (values, observed, metadata.authority)
    for (fact_type, binding), (values, observed, authority) in grouped.items():
        if not _has_required_values(fact_type, values):
            continue
        constructor = cast(_FactConstructor, fact_type)
        fact = constructor(**values)
        sink.add(
            fact,
            authority=authority,
            source=f"{type(model).__module__}.{type(model).__qualname__}:{binding}",
            observed_fields=frozenset(observed),
        )


def _transform(value: object, metadata: _ProjectionField) -> tuple[object, bool]:
    """Apply one named, deterministic projection transform."""
    if value is None:
        return None, metadata.presence is PresencePolicy.authoritative
    if metadata.transform is ValueTransform.identity:
        return value, True
    if metadata.transform is ValueTransform.positive_int:
        valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
        return value, valid
    if metadata.transform is ValueTransform.nonempty_text:
        valid = isinstance(value, str) and bool(value)
        return value, valid
    if metadata.transform is ValueTransform.enum_text:
        if isinstance(value, StrEnum):
            return str(value), True
        return value, isinstance(value, str) and bool(value)
    if metadata.transform is ValueTransform.aliases:
        if not isinstance(value, list | tuple):
            return None, False
        return tuple(item for item in value if isinstance(item, str)), True
    if metadata.transform is ValueTransform.integer_text:
        valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
        return str(value), valid
    if metadata.transform is ValueTransform.completed_status:
        return ("completed", True) if value is True else (None, False)
    raise AssertionError(f"Unhandled catalog transform: {metadata.transform}")


def _has_required_values(
    fact_type: type[CatalogFact], values: dict[str, object]
) -> bool:
    """Return whether values can construct every required canonical field."""
    return all(
        field.name in values
        or field.default is not MISSING
        or field.default_factory is not MISSING
        for field in fields(fact_type)
    )


def catalog_fact_key(fact: CatalogFact) -> tuple[object, ...]:
    """Return the explicit canonical grain key for one fact."""
    if isinstance(fact, TeamFact | ConferenceFact | VenueFact | GameFact | CoachFact):
        return (fact.id,)
    if isinstance(fact, AthleteFact | RecruitFact | DriveFact | PlayFact):
        return (fact.id,)
    if isinstance(fact, TeamSeasonFact):
        return (fact.team_id, fact.season)
    if isinstance(fact, ConferenceAffiliationFact):
        return (fact.team_id, fact.conference_id, fact.start_year)
    if isinstance(fact, AthleteTeamSeasonFact):
        return (fact.athlete_id, fact.team_name, fact.season)
    if isinstance(fact, CoachTeamSeasonFact):
        return (fact.coach_id, fact.team_id, fact.start_year)
    if isinstance(fact, VocabularyFact):
        return (fact.namespace, fact.id)
    if isinstance(fact, PlayoffMatchupFact):
        return (fact.id,)
    raise AssertionError(f"Unhandled catalog fact type: {type(fact).__name__}")
