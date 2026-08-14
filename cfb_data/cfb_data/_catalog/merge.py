"""Merge canonical observations independently of storage backends."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime
from typing import Protocol, cast

from cfb_data._catalog.models import (
    CatalogFact,
    CatalogObservation,
    FieldObservation,
    ObservationState,
)
from cfb_data._catalog.projection import catalog_fact_key


class _FactConstructor(Protocol):
    """Construct a canonical fact from merge-validated field values."""

    def __call__(self, **values: object) -> CatalogFact:
        """Return one canonical fact."""
        ...


def merge_catalog_observations(
    current: CatalogObservation | None,
    candidate: CatalogObservation,
) -> CatalogObservation:
    """Merge observations using authority, time, and stable source precedence.

    :param current: Previously selected field observations, if any.
    :param candidate: Newly encountered field observations for the same grain.
    :return: A deterministic merged observation.
    :raises ValueError: If the observations describe different fact grains.
    """
    if current is None:
        return (
            candidate
            if candidate.first_observed_at is not None
            else replace(candidate, first_observed_at=_earliest_evidence(candidate))
        )
    if type(current.fact) is not type(candidate.fact) or catalog_fact_key(
        current.fact
    ) != catalog_fact_key(candidate.fact):
        raise ValueError("Catalog observations must share a type and grain")

    current_fields = {field.field: field for field in current.fields}
    candidate_fields = {field.field: field for field in candidate.fields}
    merged_fields: list[FieldObservation] = []
    values: dict[str, object] = {}
    for fact_field in fields(current.fact):
        existing = current_fields[fact_field.name]
        incoming = candidate_fields[fact_field.name]
        selected = _select_field(existing, incoming)
        merged_fields.append(selected)
        if selected.value.state is ObservationState.value:
            values[fact_field.name] = selected.value.value
        elif selected.value.state is ObservationState.null:
            values[fact_field.name] = None
        else:
            values[fact_field.name] = getattr(current.fact, fact_field.name)
    constructor = cast(_FactConstructor, type(current.fact))
    return CatalogObservation(
        constructor(**values),
        tuple(merged_fields),
        min(_first_observed_at(current), _first_observed_at(candidate)),
    )


def _first_observed_at(observation: CatalogObservation) -> datetime:
    """Return explicit or field-derived first observation time."""
    return observation.first_observed_at or _earliest_evidence(observation)


def _earliest_evidence(observation: CatalogObservation) -> datetime:
    """Return the earliest timestamp carried by one observation's fields."""
    observed = [
        field.observed_at for field in observation.fields if field.authority > 0
    ]
    if not observed:
        observed = [field.observed_at for field in observation.fields]
    return min(observed)


def _select_field(
    current: FieldObservation, candidate: FieldObservation
) -> FieldObservation:
    """Return the field observation that wins deterministic precedence."""
    if candidate.value.state is ObservationState.unobserved:
        return current
    if current.value.state is ObservationState.unobserved:
        return candidate
    current_precedence = (
        current.authority,
        current.observed_at,
        current.source,
    )
    candidate_precedence = (
        candidate.authority,
        candidate.observed_at,
        candidate.source,
    )
    return candidate if candidate_precedence >= current_precedence else current
