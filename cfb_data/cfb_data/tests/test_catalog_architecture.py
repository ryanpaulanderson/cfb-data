"""Verify source ownership and backend-neutral catalog merge contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cfb_data._catalog.merge import merge_catalog_observations
from cfb_data._catalog.models import ObservationState, TeamFact
from cfb_data._catalog.projection import (
    compile_model_declarations,
    project_models,
    response_model_types,
    runtime_projection_contract_digest,
    validate_response_model_completeness,
)
from cfb_data._catalog.sources import IDENTITY_SOURCES
from cfb_data.teams.models.pydantic.identity import TeamIdentity
from cfb_data.teams.models.pydantic.responses import Team

_PACKAGE_ROOT = Path(__file__).parents[1]


def _team(*, abbreviation: str | None, aliases: list[str] | None) -> Team:
    """Return one validated authoritative team source row."""
    return Team.model_validate(
        {
            "id": 130,
            "school": "Michigan",
            "mascot": "Wolverines",
            "abbreviation": abbreviation,
            "alternateNames": aliases,
            "conference": "Big Ten",
            "division": "East",
            "classification": "fbs",
            "color": "#00274C",
            "alternateColor": "#FFCB05",
            "logos": [],
            "twitter": "@UMichFootball",
            "location": None,
        }
    )


def test_domain_model_owns_the_identity_read_view() -> None:
    """Keep compact read views with their source domains, not identities."""
    assert TeamIdentity.__module__ == "cfb_data.teams.models.pydantic.identity"
    assert not (_PACKAGE_ROOT / "identities" / "models.py").exists()


def test_central_projector_has_no_domain_dispatch_or_dumped_lookup() -> None:
    """Prevent class-name and dictionary mapping knowledge from returning."""
    source = (_PACKAGE_ROOT / "cache" / "_catalog.py").read_text()
    assert "model_dump" not in source
    assert "type(value).__name__" not in source
    assert "models.pydantic.responses" not in source
    assert "_TEAM_CLASSES" not in source


def test_actual_model_declarations_compile_deterministically() -> None:
    """Compile source declarations from actual classes, independent of names."""
    first = compile_model_declarations(Team)
    second = compile_model_declarations(Team)
    assert first == second
    assert first.startswith("source-model-projection:v1:")


def test_all_response_identifiers_have_source_owned_classification() -> None:
    """Reject reachable provider IDs not owned by metadata or a typed hook."""
    model_types = response_model_types()

    validate_response_model_completeness(*model_types)

    assert len(model_types) >= 150
    assert runtime_projection_contract_digest().startswith(
        "source-model-projection:v1:"
    )


def test_three_state_merge_is_order_independent_and_clears_authoritatively() -> None:
    """Clear authoritative aliases while sparse nulls preserve known values."""
    older = datetime(2024, 1, 1, tzinfo=UTC)
    newer = older + timedelta(days=1)
    old_rows: list[object] = [_team(abbreviation="MICH", aliases=["Wolverines"])]
    new_rows: list[object] = [_team(abbreviation=None, aliases=[])]
    old_projection, _ = project_models(
        old_rows,
        endpoint="/teams",
        parameters={},
        observed_at=older,
    )
    new_projection, _ = project_models(
        new_rows,
        endpoint="/teams",
        parameters={},
        observed_at=newer,
    )
    old = old_projection.observations[0]
    new = new_projection.observations[0]

    forward = merge_catalog_observations(old, new)
    reverse = merge_catalog_observations(new, old)

    assert forward == reverse
    assert forward.fact == TeamFact(130, "Michigan", "MICH", ())
    fields = {field.field: field for field in forward.fields}
    assert fields["abbreviation"].value.state is ObservationState.value
    assert fields["alternate_names"].value.state is ObservationState.value
    assert fields["alternate_names"].value.value == ()


def test_identity_source_registry_has_unique_typed_endpoints() -> None:
    """Keep one typed capability contract for each identity source route."""
    assert all(endpoint == spec.endpoint for endpoint, spec in IDENTITY_SOURCES.items())
    assert len(IDENTITY_SOURCES) == len(set(IDENTITY_SOURCES))
    assert all(
        spec.contract_digest.startswith("identity-source:v1:")
        for spec in IDENTITY_SOURCES.values()
    )


def test_hydration_capabilities_are_owned_by_identity_source_specs() -> None:
    """Keep the resumable hydration plan derived from endpoint contracts."""
    expected = {
        "/conferences",
        "/conferences/affiliations",
        "/games",
        "/plays/stats/types",
        "/plays/types",
        "/roster",
        "/stats/categories",
        "/teams",
        "/teams/fbs",
        "/venues",
    }
    actual = {
        endpoint
        for endpoint, spec in IDENTITY_SOURCES.items()
        if spec.hydration_capability is not None
    }

    assert actual == expected
    assert all(
        spec.hydration_capability in spec.capabilities
        for spec in IDENTITY_SOURCES.values()
        if spec.hydration_capability is not None
    )
