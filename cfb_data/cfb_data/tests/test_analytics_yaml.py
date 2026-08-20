"""Validate safe YAML compilation through the ordinary recipe runtime."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDYamlError,
    DatasetRecipe,
    RecipeRef,
    dataset,
    discover_recipes,
    load_recipe_yaml,
    step,
)
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.errors import CFBDOptionalDependencyError
from pydantic import BaseModel, ConfigDict

from cfb_data import CFBDClient


class _YamlRow(BaseModel):
    """Represent the Python contract mirrored by YAML fixtures."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    game_id: int
    year: int
    label: str | None


@step(id="tests.yaml_rows", revision=1, output=_YamlRow)
def _yaml_rows(year: int, label: str | None = None) -> list[_YamlRow]:
    """Build one deterministic row without external I/O."""
    return [_YamlRow(game_id=year * 10, year=year, label=label)]


@dataset(
    id="tests.yaml_equivalent_dataset",
    revision=1,
    row=_YamlRow,
    grain="one generated row",
    keys=("game_id",),
    order_by=("year", "game_id"),
)
def _python_equivalent(
    *,
    year: int,
    label: str | None = None,
) -> RecipeRef[list[_YamlRow]]:
    """Build the Python form of the declarative fixture."""
    return _yaml_rows(year=year, label=label)


def _document(*, recipe_id: str) -> str:
    """Return one finite dataset document with an explicit ordered schema."""
    return f"""
api_version: cfb_data.analytics/v1
kind: dataset
id: {recipe_id}
revision: 1
parameters:
  - name: year
    type:
      kind: integer
  - name: label
    type:
      kind: string
      nullable: true
    default: null
nodes:
  - name: rows
    recipe:
      kind: step
      id: tests.yaml_rows
      revision: 1
    arguments:
      year:
        kind: parameter
        name: year
      label:
        kind: parameter
        name: label
output:
  kind: node
  name: rows
schema:
  fields:
    - name: game_id
      type:
        kind: integer
      semantic_type: identifier
    - name: year
      type:
        kind: integer
      semantic_type: dimension
    - name: label
      type:
        kind: string
        nullable: true
      semantic_type: text
grain: one generated row
keys: [game_id]
order_by: [year, game_id]
"""


def test_python_and_yaml_compile_to_the_same_graph_fingerprint() -> None:
    """Use one IR and identity for equivalent Python and YAML authoring."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))
    declarative = load_recipe_yaml(
        _document(recipe_id="tests.yaml_equivalent_dataset"),
        recipes=snapshot,
    )

    python_graph = _compile_recipe(_python_equivalent, (), {"year": 2024})
    yaml_graph = _compile_recipe(declarative, (), {"year": 2024})

    assert python_graph.graph_fingerprint == yaml_graph.graph_fingerprint
    assert python_graph.parameter_fingerprint == yaml_graph.parameter_fingerprint


@pytest.mark.asyncio
async def test_loaded_yaml_is_callable_and_auto_registered(
    tmp_path: Path,
) -> None:
    """Execute and discover a generated recipe without a registration call."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))
    declarative = load_recipe_yaml(
        _document(recipe_id="tests.yaml_autoregistered"),
        recipes=snapshot,
    )

    assert isinstance(declarative, DatasetRecipe)
    discovered = discover_recipes(AnalyticsConfig(discover_installed=False))
    assert (
        discovered._resolve(
            kind="dataset",
            recipe_id="tests.yaml_autoregistered",
            revision=1,
        )
        is declarative
    )

    async with CFBDClient(
        "yaml-key",
        analytics=AnalyticsConfig(root=tmp_path / "analytics"),
    ) as client:
        frame: pd.DataFrame = await declarative(client, year=2024, label="safe")

    assert frame.to_dict(orient="records") == [
        {"game_id": 20240, "year": 2024, "label": "safe"}
    ]


@pytest.mark.asyncio
async def test_yaml_workflow_composes_the_registered_dataset(
    tmp_path: Path,
) -> None:
    """Use the same exact snapshot resolution for a named workflow output."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))
    document = """
api_version: cfb_data.analytics/v1
kind: workflow
id: tests.yaml_workflow
revision: 1
parameters:
  - name: year
    type:
      kind: integer
nodes:
  - name: generated
    recipe:
      kind: dataset
      id: tests.yaml_equivalent_dataset
      revision: 1
    arguments:
      year:
        kind: parameter
        name: year
outputs:
  generated:
    kind: node
    name: generated
"""
    declarative = load_recipe_yaml(document, recipes=snapshot)

    async with CFBDClient(
        "yaml-key",
        analytics=AnalyticsConfig(root=tmp_path / "analytics"),
    ) as client:
        outputs = await declarative(client, year=2024)

    frame = outputs["generated"]
    assert isinstance(frame, pd.DataFrame)
    assert frame["year"].tolist() == [2024]


@pytest.mark.parametrize(
    ("payload", "category"),
    [
        ("id: safe.value\nid: duplicate\n", "duplicate_key"),
        ("value: &shared safe\ncopy: *shared\n", "alias"),
        ("value: !!python/object:builtins.object {}\n", "tag"),
        ("base: &base {id: safe.value}\nmerged: {<<: *base}\n", "alias"),
        ("---\nid: safe.one\n---\nid: safe.two\n", "documents"),
        ("1: non-string-key\n", "mapping_key"),
        ("value: 2024-01-01\n", "value"),
        ("value: .nan\n", "number"),
        ("value: '${SECRET_SELECTOR}'\n", "interpolation"),
        ("expression: __import__('os')\n", "schema"),
    ],
)
def test_yaml_security_boundary_rejects_hostile_documents(
    payload: str,
    category: str,
) -> None:
    """Reject executable, ambiguous, or non-JSON documents safely."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))

    with pytest.raises(CFBDYamlError) as exc_info:
        load_recipe_yaml(payload, recipes=snapshot)

    assert exc_info.value.category == category
    assert "SECRET_SELECTOR" not in str(exc_info.value)
    assert exc_info.value.line >= 1
    assert exc_info.value.column >= 1


def test_yaml_rejects_excess_bytes_and_depth() -> None:
    """Enforce byte and nesting limits before recipe publication."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))
    oversized = "x" * (1024 * 1024 + 1)
    nested = "value: " + "[" * 33 + "null" + "]" * 33

    with pytest.raises(CFBDYamlError, match="size"):
        load_recipe_yaml(oversized, recipes=snapshot)
    with pytest.raises(CFBDYamlError, match="depth"):
        load_recipe_yaml(nested, recipes=snapshot)


def test_yaml_rejects_excess_static_nodes() -> None:
    """Bound parsed declarations before Pydantic or recipe resolution."""
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))
    node_heavy = "values:\n" + "".join("  - 1\n" for _ in range(1_001))

    with pytest.raises(CFBDYamlError, match="nodes"):
        load_recipe_yaml(node_heavy, recipes=snapshot)


def test_yaml_missing_extra_has_actionable_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the base install importable and explain the selected extra."""
    original_import: Callable[..., object] = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "yaml":
            raise ImportError("blocked optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    snapshot = discover_recipes(AnalyticsConfig(discover_installed=False))

    with pytest.raises(CFBDOptionalDependencyError, match=r"cfb-data\[yaml\]"):
        load_recipe_yaml(_document(recipe_id="tests.missing_yaml"), recipes=snapshot)
