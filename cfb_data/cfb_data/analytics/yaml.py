"""Load a hardened declarative YAML subset into analytics definitions."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    model_validator,
)
from pydantic_core import PydanticUndefined

from cfb_data.analytics._sources import endpoint_operation
from cfb_data.analytics.contracts import (
    AnalyticsDefinition,
    ColumnMetadata,
    DatasetDefinition,
    LiteralBinding,
    ParameterBinding,
    SourceNode,
    TableContract,
    TransformNode,
    WorkflowDefinition,
)
from cfb_data.base.types import JSONValue, json_value
from cfb_data.errors import (
    CFBDDefinitionError,
    CFBDOptionalDependencyError,
)

_MAX_BYTES = 1024 * 1024
_MAX_DEPTH = 32
_MAX_NODES = 10_000
_MAX_GRAPH_NODES = 1_000


class _YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _YamlParameter(_YamlModel):
    type: Literal["string", "integer", "number", "boolean"]
    required: bool = True
    default: JSONValue = None


class _YamlField(_YamlModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal[
        "string",
        "integer",
        "number",
        "boolean",
        "datetime",
        "string_list",
        "integer_list",
        "number_list",
    ]
    nullable: bool = False
    description: str | None = None
    units: str | None = None
    semantic_type: str | None = None


class _YamlTable(_YamlModel):
    id: str
    revision: int = Field(ge=1)
    grain: str = Field(min_length=1)
    keys: list[str] = Field(min_length=1)
    order_by: list[str]
    partition_by: list[str] = Field(default_factory=list)
    event_time: str | None = None
    fields: list[_YamlField] = Field(min_length=1)


class _YamlReference(_YamlModel):
    parameter: str | None = None
    literal: JSONValue = None

    @model_validator(mode="after")
    def validate_reference(self) -> _YamlReference:
        """Require exactly one structured reference variant."""
        has_parameter = "parameter" in self.model_fields_set
        has_literal = "literal" in self.model_fields_set
        if has_parameter == has_literal:
            raise ValueError("Reference must contain exactly parameter or literal")
        if has_parameter and not self.parameter:
            raise ValueError("Parameter references must be non-empty")
        return self


class _YamlNode(_YamlModel):
    kind: Literal["source", "transform"]
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    operation: str
    revision: int = Field(ge=1)
    bindings: dict[str, _YamlReference] | None = None
    inputs: list[str] | None = None
    config: dict[str, JSONValue] = Field(default_factory=dict)
    output: _YamlTable | None = None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> _YamlNode:
        """Reject fields that do not belong to the selected node kind."""
        if self.kind == "source":
            if self.inputs is not None or self.output is not None or self.config:
                raise ValueError("Source nodes accept bindings only")
        else:
            if not self.inputs or self.output is None or self.bindings is not None:
                raise ValueError("Transform nodes require inputs and output")
        return self


class _YamlDefinition(_YamlModel):
    api_version: Literal["cfb-data/v1"]
    kind: Literal["dataset", "workflow"]
    id: str
    revision: int = Field(ge=1)
    description: str = Field(min_length=1)
    parameters: dict[str, _YamlParameter]
    nodes: list[_YamlNode] = Field(min_length=1, max_length=_MAX_GRAPH_NODES)
    output_node: str | None = None
    outputs: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_outputs(self) -> _YamlDefinition:
        """Require the output shape belonging to the selected definition kind."""
        if self.kind == "dataset":
            if self.output_node is None or self.outputs is not None:
                raise ValueError("Datasets require output_node only")
        elif not self.outputs or self.output_node is not None:
            raise ValueError("Workflows require non-empty outputs only")
        return self


def load_yaml_definition(path: Path) -> AnalyticsDefinition:
    """Load one hardened YAML dataset definition from a local file.

    :param path: Explicit UTF-8 YAML file.
    :return: Immutable definition compiled to the public Python contract.
    :raises CFBDOptionalDependencyError: If the YAML extra is unavailable.
    :raises CFBDDefinitionError: If parsing or validation fails safely.
    """
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CFBDDefinitionError("YAML definition could not be read") from exc
    return loads_yaml_definition(payload)


def loads_yaml_definition(
    source: str | bytes,
) -> AnalyticsDefinition:
    """Load one hardened YAML dataset definition from text or bytes."""
    try:
        import yaml
        from yaml.constructor import ConstructorError
        from yaml.nodes import MappingNode
        from yaml.tokens import AliasToken, AnchorToken, TagToken
    except ImportError as exc:
        raise CFBDOptionalDependencyError(
            "YAML definitions require the 'cfb-data[yaml]' extra"
        ) from exc

    encoded = source.encode() if isinstance(source, str) else source
    if len(encoded) > _MAX_BYTES:
        raise CFBDDefinitionError("YAML definition exceeds the 1 MiB limit")
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CFBDDefinitionError("YAML definition must be UTF-8") from exc

    class _StrictSafeLoader(yaml.SafeLoader):
        pass

    def construct_mapping(
        loader: _StrictSafeLoader, node: object, deep: bool = False
    ) -> dict[str, object]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "Expected a mapping", None)
        keys: set[str] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=False)
            if not isinstance(key, str):
                raise ConstructorError(None, None, "Mapping keys must be strings", None)
            if key == "<<":
                raise ConstructorError(None, None, "Merge keys are not allowed", None)
            if key in keys:
                raise ConstructorError(None, None, "Duplicate mapping key", None)
            keys.add(key)
        value = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
        return {str(key): item for key, item in value.items()}

    _StrictSafeLoader.add_constructor(  # type: ignore[type-var]
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )
    try:
        for token in yaml.scan(text, Loader=_StrictSafeLoader):
            if isinstance(token, AnchorToken | AliasToken | TagToken):
                raise CFBDDefinitionError(
                    "YAML anchors, aliases, and explicit tags are not allowed"
                )
        documents = list(yaml.load_all(text, Loader=_StrictSafeLoader))
    except CFBDDefinitionError:
        raise
    except yaml.YAMLError as exc:
        raise CFBDDefinitionError("YAML definition is invalid") from exc
    if len(documents) != 1:
        raise CFBDDefinitionError("YAML definitions must contain one document")
    raw = documents[0]
    _validate_tree(raw)
    try:
        json_compatible = json_value(raw)
        definition = _YamlDefinition.model_validate(json_compatible)
    except Exception as exc:
        raise CFBDDefinitionError("YAML definition does not match the schema") from exc
    return _compile_yaml(definition)


def _compile_yaml(
    definition: _YamlDefinition,
) -> AnalyticsDefinition:
    parameter_fields: dict[str, tuple[object, object]] = {}
    for name, spec in definition.parameters.items():
        annotation = _parameter_type(spec.type)
        default: object = PydanticUndefined if spec.required else spec.default
        parameter_fields[name] = (annotation, default)
    parameter_model = create_model(  # type: ignore[call-overload]
        f"YamlParams_{_model_suffix(definition.id, str(definition.revision))}",
        __config__=ConfigDict(extra="forbid", strict=True),
        **parameter_fields,
    )
    nodes: list[SourceNode | TransformNode] = []
    output_contract: TableContract[BaseModel] | None = None
    for node in definition.nodes:
        if node.kind == "source":
            operation = endpoint_operation(node.operation)
            bindings: dict[str, ParameterBinding | LiteralBinding] = {}
            for name, reference in (node.bindings or {}).items():
                if "parameter" in reference.model_fields_set:
                    bindings[name] = ParameterBinding(reference.parameter or "")
                else:
                    bindings[name] = LiteralBinding(reference.literal)
            compiled: SourceNode | TransformNode = SourceNode(
                id=node.id,
                operation_id=operation.id,
                operation_revision=node.revision,
                bindings=bindings,
                output=operation.output,
            )
        else:
            if node.output is None or node.inputs is None:
                raise AssertionError("Validated transform node is incomplete")
            contract = _table_contract(node.output, definition.id, node.id)
            compiled = TransformNode(
                id=node.id,
                operation_id=node.operation,
                operation_revision=node.revision,
                inputs=tuple(node.inputs),
                output=contract,
                config=node.config,
            )
        nodes.append(compiled)
        if node.id == definition.output_node:
            output_contract = compiled.output
    if definition.kind == "dataset":
        if output_contract is None or definition.output_node is None:
            raise CFBDDefinitionError("YAML output node does not exist")
        return DatasetDefinition(
            id=definition.id,
            revision=definition.revision,
            parameter_model=parameter_model,
            nodes=tuple(nodes),
            output_node=definition.output_node,
            output=output_contract,
            description=definition.description,
        )
    if definition.outputs is None:
        raise AssertionError("Validated YAML workflow outputs are missing")
    return WorkflowDefinition(
        id=definition.id,
        revision=definition.revision,
        parameter_model=parameter_model,
        nodes=tuple(nodes),
        outputs=definition.outputs,
        description=definition.description,
    )


def _table_contract(
    value: _YamlTable, definition_id: str, node_id: str
) -> TableContract[BaseModel]:
    fields: dict[str, tuple[object, object]] = {}
    columns: dict[str, ColumnMetadata] = {}
    for field in value.fields:
        annotation = _field_type(field.type)
        if field.nullable:
            # Dynamic schemas intentionally assemble a runtime union annotation.
            annotation = annotation | None  # type: ignore[operator]
            default: object = None
        else:
            default = PydanticUndefined
        fields[field.name] = (annotation, default)
        if field.description is not None:
            columns[field.name] = ColumnMetadata(
                field.description,
                units=field.units,
                semantic_type=field.semantic_type,
            )
    row_model = create_model(  # type: ignore[call-overload]
        f"YamlRow_{_model_suffix(definition_id, node_id, str(value.revision))}",
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )
    return TableContract(
        id=value.id,
        revision=value.revision,
        row_model=row_model,
        grain=value.grain,
        keys=tuple(value.keys),
        order_by=tuple(value.order_by),
        partition_by=tuple(value.partition_by),
        event_time=value.event_time,
        columns=columns,
    )


def _parameter_type(name: str) -> object:
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }[name]


def _field_type(name: str) -> object:
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "datetime": datetime,
        "string_list": list[str],
        "integer_list": list[int],
        "number_list": list[float],
    }[name]


def _model_suffix(*values: str) -> str:
    """Return a deterministic safe suffix for generated Pydantic model names."""
    return hashlib.sha256("\x00".join(values).encode()).hexdigest()[:16]


def _validate_tree(value: object) -> None:
    nodes = 0

    def visit(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_NODES:
            raise CFBDDefinitionError("YAML definition exceeds the node limit")
        if depth > _MAX_DEPTH:
            raise CFBDDefinitionError("YAML definition exceeds the depth limit")
        if isinstance(item, float) and not math.isfinite(item):
            raise CFBDDefinitionError("YAML numbers must be finite")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CFBDDefinitionError("YAML mapping keys must be strings")
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif item is not None and not isinstance(item, str | int | float | bool):
            raise CFBDDefinitionError("YAML values must be JSON-compatible")

    visit(value, 0)


__all__ = ["load_yaml_definition", "loads_yaml_definition"]
