"""Test endpoint-owned Drives operations and public recipe sources."""

from __future__ import annotations

from cfb_data.analytics import RecipeRef, dataset
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.drives.sources import drives


@dataset(
    id="tests.source_faithful_drives",
    revision=1,
    row=Drive,
    grain="one drive",
    keys=("game_id", "id"),
)
def _source_faithful_drives(year: int) -> RecipeRef[list[Drive]]:
    """Build the Drives source through its public callable."""
    return drives(year=year)


def test_drives_source_uses_its_domain_operation() -> None:
    """Derive route identity from the same operation as the client resource."""
    graph = _compile_recipe(_source_faithful_drives, (), {"year": 2024})

    assert drives.id == "cfbd.drives.list"
    assert drives.revision == 1
    source_node = graph.nodes[0]
    assert source_node.declaration.operation is not None
    assert source_node.declaration.source_cost == 1
