"""Test the hardened YAML extension boundary."""

import pytest

from cfb_data import (
    CFBDDefinitionError,
    DatasetDefinition,
    WorkflowDefinition,
    loads_yaml_definition,
)

_DATASET = """
api_version: cfb-data/v1
kind: dataset
id: example.games
revision: 1
description: Validated example games.
parameters:
  year:
    type: integer
nodes:
  - kind: source
    id: games
    operation: cfbd.games.list
    revision: 1
    bindings:
      year:
        parameter: year
output_node: games
"""


def test_yaml_compiles_deterministically_to_the_python_contract() -> None:
    """Compile repeated documents to identical schema and definition identity."""
    first = loads_yaml_definition(_DATASET)
    second = loads_yaml_definition(_DATASET)

    assert isinstance(first, DatasetDefinition)
    assert isinstance(second, DatasetDefinition)
    assert first.id == second.id == "example.games"
    assert first.parameter_model.__name__ == second.parameter_model.__name__
    assert first.output.schema_digest == second.output.schema_digest


def test_yaml_supports_finite_named_output_workflows() -> None:
    """Compile workflow outputs without introducing executable YAML behavior."""
    document = _DATASET.replace("kind: dataset", "kind: workflow").replace(
        "output_node: games", "outputs:\n  games: games"
    )
    result = loads_yaml_definition(document)

    assert isinstance(result, WorkflowDefinition)
    assert tuple(result.outputs) == ("games",)


@pytest.mark.parametrize(
    "document",
    [
        _DATASET.replace("revision: 1", "revision: 1\nrevision: 2", 1),
        _DATASET.replace(
            "description: Validated example games.", "description: &x bad"
        ),
        _DATASET.replace(
            "description: Validated example games.", "description: !x bad"
        ),
        _DATASET + "---\n{}\n",
        _DATASET.replace("type: integer", "type: integer\n    default: .nan"),
        _DATASET.replace(
            "description: Validated example games.", "description: 2024-01-01"
        ),
    ],
)
def test_yaml_rejects_ambiguous_or_non_json_constructs(document: str) -> None:
    """Fail safely on duplicate, graph, tag, document, and scalar hazards."""
    with pytest.raises(CFBDDefinitionError):
        loads_yaml_definition(document)


def test_yaml_rejects_oversized_input_before_parsing() -> None:
    """Enforce the byte ceiling before constructing YAML nodes."""
    with pytest.raises(CFBDDefinitionError, match="1 MiB"):
        loads_yaml_definition("x" * (1024 * 1024 + 1))
