"""Project validated responses through source-owned catalog declarations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from cfb_data._catalog.models import (
    CatalogProjection,
    CoverageRecord,
    CoverageStatus,
)
from cfb_data._catalog.projection import (
    CatalogSink,
    ObservationAuthority,
    project_models,
)
from cfb_data._catalog.sources import identity_source, projection_contract
from cfb_data.base.types import QueryParameters


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
    """Return typed facts and coverage from one validated API response."""
    source_projection, _ = project_models(
        value,
        endpoint=endpoint,
        parameters=parameters,
        observed_at=fetched_at,
    )
    sink = CatalogSink(fetched_at)
    sink.add_projection(
        source_projection,
        authority=ObservationAuthority.authoritative,
        source="source-model",
    )
    source = identity_source(endpoint)
    row_count = len(value) if isinstance(value, list) else 1
    status = (
        CoverageStatus.possibly_truncated
        if source.known_cap is not None and row_count >= source.known_cap
        else CoverageStatus.complete
    )
    filters = canonical_filters(parameters)
    coverage = CoverageRecord(
        partition_key=f"{endpoint}:{filters}",
        namespace=source.namespace,
        canonical_filters=filters,
        capabilities=source.capabilities,
        status=status,
        response_key=response_key,
        endpoint=endpoint,
        fetched_at=fetched_at,
        validated_at=fetched_at,
        fresh_until=fresh_until,
        retained_until=retained_until,
        row_count=row_count,
        known_cap=source.known_cap,
        projection_contract=projection_contract(endpoint),
    )
    facts = sink.projection()
    return CatalogProjection(
        teams=facts.teams,
        team_seasons=facts.team_seasons,
        conferences=facts.conferences,
        affiliations=facts.affiliations,
        venues=facts.venues,
        games=facts.games,
        athletes=facts.athletes,
        athlete_team_seasons=facts.athlete_team_seasons,
        recruits=facts.recruits,
        coaches=facts.coaches,
        coach_team_seasons=facts.coach_team_seasons,
        drives=facts.drives,
        plays=facts.plays,
        vocabularies=facts.vocabularies,
        playoff_matchups=facts.playoff_matchups,
        observations=facts.observations,
        coverage=coverage,
    )


def canonical_filters(parameters: QueryParameters) -> str:
    """Return bounded deterministic filters for the coverage ledger."""
    return "&".join(f"{key}={parameters[key]!r}" for key in sorted(parameters))
