"""Load bounded declarative YAML through the ordinary recipe runtime."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import operator
import re
import types
from collections.abc import Callable, Hashable, Mapping
from typing import Any, Literal, Self, cast, get_type_hints, is_typeddict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    create_model,
    model_validator,
)

from cfb_data._tabular import _logical_schema, _logical_schema_digest
from cfb_data.errors import CFBDOptionalDependencyError

from ._recipes import (
    DatasetRecipe,
    SourceRecipe,
    StepRecipe,
    WorkflowRecipe,
    _dataset_declaration,
    _workflow_declaration,
)
from ._registration import _publish_candidate
from .discovery import RecipeSnapshot
from .errors import (
    CFBDRecipeConfigurationError,
    CFBDRecipeDiscoveryError,
    CFBDYamlError,
)

type _JsonValue = (
    None | bool | int | float | str | list[_JsonValue] | dict[str, _JsonValue]
)
type _RecipeObject = (
    SourceRecipe[..., object]
    | StepRecipe[..., object]
    | DatasetRecipe[..., object]
    | WorkflowRecipe[..., object]
)

_MAX_BYTES = 1024 * 1024
_MAX_DEPTH = 32
_MAX_NODES = 1_000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_FORBIDDEN_TEXT = ("${", "{{", "{%")


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
    )


class _YamlType(_StrictModel):
    kind: Literal["string", "integer", "number", "boolean", "list", "struct"]
    nullable: bool = False
    items: _YamlType | None = None
    fields: list[_YamlField] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Require exactly the structural members used by this type kind."""
        if self.kind == "list":
            if self.items is None or self.fields:
                raise ValueError("list types require items and forbid fields")
        elif self.kind == "struct":
            if self.items is not None or not self.fields:
                raise ValueError("struct types require fields and forbid items")
            names = [field.name for field in self.fields]
            if len(names) != len(set(names)):
                raise ValueError("struct field names must be unique")
        elif self.items is not None or self.fields:
            raise ValueError("scalar types forbid items and fields")
        return self


class _YamlField(_StrictModel):
    name: str = Field(min_length=1, max_length=128)
    type: _YamlType
    description: str | None = Field(default=None, max_length=2_000)
    unit: str | None = Field(default=None, max_length=128)
    semantic_type: (
        Literal["identifier", "dimension", "measure", "time", "text"] | None
    ) = None


class _YamlSchema(_StrictModel):
    fields: list[_YamlField] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_names(self) -> Self:
        """Require one deterministic ordered occurrence of every field."""
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("schema field names must be unique")
        return self


class _YamlParameter(_StrictModel):
    name: str = Field(min_length=1, max_length=128)
    type: _YamlType
    default: _JsonValue = None


class _YamlRecipeReference(_StrictModel):
    kind: Literal["source", "step", "dataset", "workflow"]
    id: str = Field(min_length=3, max_length=256)
    revision: int = Field(ge=1)


class _YamlBinding(_StrictModel):
    kind: Literal["parameter", "node", "literal", "list", "mapping"]
    name: str | None = Field(default=None, min_length=1, max_length=128)
    output: str | None = Field(default=None, min_length=1, max_length=128)
    value: _JsonValue = None
    items: list[_YamlBinding] = Field(default_factory=list)
    entries: dict[str, _YamlBinding] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Reject ambiguous expression forms before graph construction."""
        if self.kind == "parameter":
            valid = self.name is not None and self.output is None
            empty = not self.items and not self.entries and self.value is None
        elif self.kind == "node":
            valid = self.name is not None
            empty = not self.items and not self.entries and self.value is None
        elif self.kind == "literal":
            valid = self.name is None and self.output is None
            empty = not self.items and not self.entries
        elif self.kind == "list":
            valid = self.name is None and self.output is None
            empty = not self.entries and self.value is None
        else:
            valid = self.name is None and self.output is None
            empty = not self.items and self.value is None
        if not valid or not empty:
            raise ValueError("binding fields do not match its declared kind")
        return self


class _YamlNode(_StrictModel):
    name: str = Field(min_length=1, max_length=128)
    recipe: _YamlRecipeReference
    alias: str | None = Field(default=None, min_length=1, max_length=128)
    arguments: dict[str, _YamlBinding] = Field(default_factory=dict)


class _YamlDocument(_StrictModel):
    api_version: Literal["cfb_data.analytics/v1"]
    kind: Literal["dataset", "workflow"]
    id: str = Field(min_length=3, max_length=256)
    revision: int = Field(ge=1)
    parameters: list[_YamlParameter] = Field(default_factory=list, max_length=128)
    nodes: list[_YamlNode] = Field(min_length=1, max_length=_MAX_NODES)
    output: _YamlBinding | None = None
    outputs: dict[str, _YamlBinding] | None = None
    output_schema: _YamlSchema | None = Field(default=None, alias="schema")
    grain: str | None = Field(default=None, min_length=1, max_length=512)
    keys: list[str] = Field(default_factory=list)
    order_by: list[str] = Field(default_factory=list)
    partition_by: list[str] = Field(default_factory=list)
    event_time: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Require dataset metadata or named workflow outputs, never both."""
        if "." not in self.id:
            raise ValueError("recipe IDs must be namespaced")
        parameters = [parameter.name for parameter in self.parameters]
        nodes = [node.name for node in self.nodes]
        if len(parameters) != len(set(parameters)):
            raise ValueError("parameter names must be unique")
        if len(nodes) != len(set(nodes)):
            raise ValueError("node names must be unique")
        if self.kind == "dataset":
            if (
                self.output is None
                or self.outputs is not None
                or self.output_schema is None
                or self.grain is None
            ):
                raise ValueError("datasets require output, schema, and grain")
        elif (
            self.outputs is None
            or not self.outputs
            or self.output is not None
            or self.output_schema is not None
            or self.grain is not None
            or self.keys
            or self.order_by
            or self.partition_by
            or self.event_time is not None
        ):
            raise ValueError("workflows require only explicit named outputs")
        return self


_YamlType.model_rebuild()
_YamlBinding.model_rebuild()


def load_recipe_yaml(
    text: str,
    *,
    recipes: RecipeSnapshot,
) -> DatasetRecipe[..., object] | WorkflowRecipe[..., object]:
    """Load one safe finite YAML definition as an ordinary callable recipe.

    :param text: One UTF-8 YAML document no larger than one MiB.
    :param recipes: Explicit immutable snapshot used for exact resolution.
    :return: A directly callable dataset or workflow recipe.
    :raises CFBDOptionalDependencyError: If the ``yaml`` extra is unavailable.
    :raises CFBDYamlError: If parsing, security, schema, or binding checks fail.
    """
    if not isinstance(text, str):
        raise CFBDYamlError(category="encoding", line=1, column=1)
    try:
        payload = text.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise CFBDYamlError(category="encoding", line=1, column=1) from exc
    if len(payload) > _MAX_BYTES:
        raise CFBDYamlError(category="size", line=1, column=1)
    raw = _parse_yaml(text)
    _validate_json_tree(raw)
    try:
        document = _YamlDocument.model_validate(raw, strict=True)
    except ValidationError as exc:
        raise CFBDYamlError(category="schema", line=1, column=1) from exc
    try:
        resolved = _resolve_nodes(document, recipes)
        if document.kind == "dataset":
            declared_model = _row_model(document)
            row_model = _validate_output_contract(
                document,
                resolved,
                declared_model,
            )
        else:
            row_model = None
        recipe = _build_recipe(document, resolved, row_model)
    except (CFBDRecipeConfigurationError, CFBDRecipeDiscoveryError, TypeError) as exc:
        raise CFBDYamlError(category="definition", line=1, column=1) from exc
    _publish_candidate(recipe, require_module_binding=False)
    return recipe


def _parse_yaml(text: str) -> object:
    try:
        import yaml
    except ImportError as exc:
        raise CFBDOptionalDependencyError(
            "YAML recipes require the optional 'yaml' extra; install cfb-data[yaml]"
        ) from exc

    class StrictSafeLoader(yaml.SafeLoader):
        """Reject duplicate and non-string mapping keys during construction."""

        def construct_mapping(
            self,
            node: yaml.nodes.MappingNode,
            deep: bool = False,
        ) -> dict[Hashable, Any]:
            # PyYAML's constructor protocol is intentionally untyped at this
            # boundary; every key and value is narrowed immediately below.
            if not isinstance(node, yaml.MappingNode):
                raise CFBDYamlError(
                    category="mapping",
                    line=node.start_mark.line + 1,
                    column=node.start_mark.column + 1,
                )
            mapping: dict[Hashable, Any] = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str) or key == "<<":
                    raise CFBDYamlError(
                        category="mapping_key",
                        line=key_node.start_mark.line + 1,
                        column=key_node.start_mark.column + 1,
                    )
                if key in mapping:
                    raise CFBDYamlError(
                        category="duplicate_key",
                        line=key_node.start_mark.line + 1,
                        column=key_node.start_mark.column + 1,
                    )
                mapping[key] = self.construct_object(value_node, deep=deep)
            return mapping

    try:
        events = tuple(yaml.parse(text, Loader=yaml.SafeLoader))
        documents = 0
        for event in events:
            if isinstance(event, yaml.events.DocumentStartEvent):
                documents += 1
            mark = event.start_mark
            if isinstance(event, yaml.events.AliasEvent) or getattr(
                event, "anchor", None
            ):
                raise CFBDYamlError(
                    category="alias",
                    line=mark.line + 1,
                    column=mark.column + 1,
                )
            if getattr(event, "tag", None) is not None:
                raise CFBDYamlError(
                    category="tag",
                    line=mark.line + 1,
                    column=mark.column + 1,
                )
        if documents != 1:
            raise CFBDYamlError(category="documents", line=1, column=1)
        return yaml.load(text, Loader=StrictSafeLoader)
    except CFBDYamlError:
        raise
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        column = mark.column + 1 if mark is not None else 1
        raise CFBDYamlError(category="syntax", line=line, column=column) from exc


def _validate_json_tree(value: object, *, depth: int = 0) -> int:
    if depth > _MAX_DEPTH:
        raise CFBDYamlError(category="depth", line=1, column=1)
    if value is None or isinstance(value, bool | int | str):
        if isinstance(value, str) and any(token in value for token in _FORBIDDEN_TEXT):
            raise CFBDYamlError(category="interpolation", line=1, column=1)
        return 1
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CFBDYamlError(category="number", line=1, column=1)
        return 1
    count = 1
    if isinstance(value, list):
        for item in value:
            count += _validate_json_tree(item, depth=depth + 1)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CFBDYamlError(category="mapping_key", line=1, column=1)
            count += 1 + _validate_json_tree(item, depth=depth + 1)
    else:
        raise CFBDYamlError(category="value", line=1, column=1)
    if count > _MAX_NODES:
        raise CFBDYamlError(category="nodes", line=1, column=1)
    return count


def _resolve_nodes(
    document: _YamlDocument,
    recipes: RecipeSnapshot,
) -> Mapping[str, tuple[_YamlNode, _RecipeObject]]:
    parameters = {parameter.name: parameter for parameter in document.parameters}
    resolved: dict[str, tuple[_YamlNode, _RecipeObject]] = {}
    invocations: dict[tuple[str, str, int], str | None] = {}
    for node in document.nodes:
        _require_slug(node.name)
        if node.alias is not None:
            _require_slug(node.alias)
        candidate = recipes._resolve(
            kind=node.recipe.kind,
            recipe_id=node.recipe.id,
            revision=node.recipe.revision,
        )
        if not isinstance(
            candidate,
            SourceRecipe | StepRecipe | DatasetRecipe | WorkflowRecipe,
        ):
            raise CFBDRecipeDiscoveryError("Snapshot resolved an invalid recipe")
        recipe = cast(_RecipeObject, candidate)
        key = (node.recipe.kind, node.recipe.id, node.recipe.revision)
        if key in invocations and node.alias is None:
            raise CFBDRecipeConfigurationError(
                "Repeated YAML recipe calls require explicit aliases"
            )
        invocations[key] = node.alias
        _validate_bindings(node, recipe, parameters, resolved)
        resolved[node.name] = (node, recipe)
    if document.kind == "dataset":
        if document.output is None:
            raise AssertionError("Validated YAML dataset lacks output")
        outputs: Mapping[str, _YamlBinding] | None = {"value": document.output}
    else:
        outputs = document.outputs
    if outputs is None:
        raise AssertionError("Validated YAML document lacks outputs")
    for binding in outputs.values():
        _validate_binding(binding, parameters, resolved)
    return resolved


def _validate_bindings(
    node: _YamlNode,
    recipe: _RecipeObject,
    parameters: Mapping[str, _YamlParameter],
    resolved: Mapping[str, tuple[_YamlNode, _RecipeObject]],
) -> None:
    signature = recipe._signature
    try:
        bound = signature.bind(**{name: object() for name in node.arguments})
        bound.apply_defaults()
    except TypeError as exc:
        raise CFBDRecipeConfigurationError(
            "YAML node arguments do not match the recipe signature"
        ) from exc
    hints = get_type_hints(recipe._function, include_extras=True)
    for name, binding in node.arguments.items():
        _validate_binding(binding, parameters, resolved)
        if binding.kind == "literal":
            try:
                TypeAdapter(hints[name]).validate_python(binding.value, strict=True)
            except (KeyError, ValidationError, TypeError) as exc:
                raise CFBDRecipeConfigurationError(
                    "YAML literal violates the recipe parameter contract"
                ) from exc
        elif binding.kind == "parameter":
            parameter = parameters.get(binding.name or "")
            if parameter is None:
                raise CFBDRecipeConfigurationError(
                    "YAML parameter binding is unavailable"
                )
            if _annotation(parameter.type, name) != hints[name]:
                raise CFBDRecipeConfigurationError(
                    "YAML parameter and recipe annotations differ"
                )


def _validate_binding(
    binding: _YamlBinding,
    parameters: Mapping[str, _YamlParameter],
    resolved: Mapping[str, tuple[_YamlNode, _RecipeObject]],
) -> None:
    if binding.kind == "parameter" and binding.name not in parameters:
        raise CFBDRecipeConfigurationError("YAML references an unknown parameter")
    if binding.kind == "node":
        target = resolved.get(binding.name or "")
        if target is None:
            raise CFBDRecipeConfigurationError(
                "YAML nodes may reference only earlier declared nodes"
            )
        target_kind = target[0].recipe.kind
        if (target_kind == "workflow") != (binding.output is not None):
            raise CFBDRecipeConfigurationError(
                "Workflow bindings require one explicit named output"
            )
        if target_kind == "workflow" and binding.output is not None:
            return_type = get_type_hints(
                target[1]._function,
                include_extras=True,
            )["return"]
            annotations = getattr(return_type, "__annotations__", {})
            if not is_typeddict(return_type) or binding.output not in annotations:
                raise CFBDRecipeConfigurationError(
                    "YAML workflow selection requires a declared named output"
                )
    for item in binding.items:
        _validate_binding(item, parameters, resolved)
    for item in binding.entries.values():
        _validate_binding(item, parameters, resolved)


def _row_model(document: _YamlDocument) -> type[BaseModel]:
    schema = document.output_schema
    if schema is None:
        raise AssertionError("Validated YAML dataset lacks a schema")
    return _struct_model(
        schema.fields,
        name=f"Yaml_{hashlib.sha256(document.id.encode()).hexdigest()[:16]}",
    )


def _struct_model(fields: list[_YamlField], *, name: str) -> type[BaseModel]:
    definitions: dict[str, tuple[object, object]] = {}
    for field in fields:
        _require_field_name(field.name)
        annotation = _annotation(field.type, f"{name}_{field.name}")
        metadata: dict[str, Any] = {
            key: value
            for key, value in {
                "semantic_type": field.semantic_type,
                "unit": field.unit,
            }.items()
            if value is not None
        }
        definitions[field.name] = (
            annotation,
            Field(
                ...,
                description=field.description,
                json_schema_extra=metadata or None,
            ),
        )
    # Pydantic's dynamic model API necessarily accepts heterogeneous field
    # declarations; the result is immediately narrowed to ``type[BaseModel]``.
    dynamic_definitions: dict[str, Any] = dict(definitions)
    model_factory = cast(Callable[..., type[BaseModel]], create_model)
    model = model_factory(
        name,
        __config__=ConfigDict(extra="forbid", frozen=True, strict=True),
        __module__="cfb_data.analytics.yaml",
        **dynamic_definitions,
    )
    return model


def _annotation(value: _YamlType, name: str) -> object:
    scalar: dict[str, object] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    if value.kind in scalar:
        annotation = scalar[value.kind]
    elif value.kind == "list":
        if value.items is None:
            raise AssertionError("Validated list type lacks items")
        annotation = types.GenericAlias(
            list,
            _annotation(value.items, f"{name}_item"),
        )
    else:
        annotation = _struct_model(value.fields, name=f"{name}_struct")
    return operator.or_(annotation, type(None)) if value.nullable else annotation


def _validate_output_contract(
    document: _YamlDocument,
    resolved: Mapping[str, tuple[_YamlNode, _RecipeObject]],
    row_model: type[BaseModel],
) -> type[BaseModel]:
    if document.kind != "dataset" or document.output is None:
        raise AssertionError("Validated YAML dataset lacks its table contract")
    binding = document.output
    if binding.kind != "node" or binding.output is not None:
        raise CFBDRecipeConfigurationError(
            "YAML dataset output must bind one table-producing node"
        )
    target = resolved[binding.name or ""][1]
    output_type = target._declaration.output_type
    if not isinstance(output_type, type) or not issubclass(output_type, BaseModel):
        raise CFBDRecipeConfigurationError(
            "YAML dataset output does not declare a table row model"
        )
    expected = _logical_schema_digest(_logical_schema(output_type))
    actual = _logical_schema_digest(_logical_schema(row_model))
    if expected != actual:
        raise CFBDRecipeConfigurationError(
            "YAML output schema differs from its selected recipe output"
        )
    return output_type


def _build_recipe(
    document: _YamlDocument,
    resolved: Mapping[str, tuple[_YamlNode, _RecipeObject]],
    row_model: type[BaseModel] | None,
) -> DatasetRecipe[..., object] | WorkflowRecipe[..., object]:
    def yaml_builder(**parameters: object) -> object:
        values: dict[str, object] = {}
        for name, (node, target) in resolved.items():
            selected = target.as_(node.alias) if node.alias is not None else target
            arguments = {
                key: _evaluate_binding(binding, parameters, values)
                for key, binding in node.arguments.items()
            }
            values[name] = selected(**arguments)
        if document.kind == "dataset":
            if document.output is None:
                raise AssertionError("Validated YAML dataset lacks output")
            return _evaluate_binding(document.output, parameters, values)
        if document.outputs is None:
            raise AssertionError("Validated YAML workflow lacks outputs")
        return {
            name: _evaluate_binding(binding, parameters, values)
            for name, binding in document.outputs.items()
        }

    function_name = "yaml_" + re.sub(r"[^A-Za-z0-9_]", "_", document.id)
    annotations: dict[str, object] = {}
    signature_parameters: list[inspect.Parameter] = []
    for parameter in document.parameters:
        _require_field_name(parameter.name)
        annotation = _annotation(parameter.type, f"parameter_{parameter.name}")
        annotations[parameter.name] = annotation
        default: object = inspect.Parameter.empty
        if "default" in parameter.model_fields_set:
            try:
                default = TypeAdapter(annotation).validate_python(
                    parameter.default,
                    strict=True,
                )
            except (ValidationError, TypeError) as exc:
                raise CFBDRecipeConfigurationError(
                    "YAML parameter default violates its declared type"
                ) from exc
        signature_parameters.append(
            inspect.Parameter(
                parameter.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
    return_annotation: object = object
    annotations["return"] = return_annotation
    yaml_builder.__name__ = function_name
    yaml_builder.__qualname__ = function_name
    yaml_builder.__module__ = "cfb_data.analytics.yaml"
    yaml_builder.__annotations__ = annotations
    yaml_builder.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        signature_parameters,
        return_annotation=return_annotation,
    )
    yaml_builder.__cfb_recipe_diagnostic__ = _document_digest(  # type: ignore[attr-defined]
        document
    )
    if document.kind == "dataset":
        if row_model is None or document.grain is None:
            raise AssertionError("Validated YAML dataset lacks metadata")
        declaration = _dataset_declaration(
            recipe_id=document.id,
            revision=document.revision,
            row=row_model,
            grain=document.grain,
            keys=tuple(document.keys),
            order_by=tuple(document.order_by),
            partition_by=tuple(document.partition_by),
            event_time=document.event_time,
        )
        return DatasetRecipe(cast(Callable[..., object], yaml_builder), declaration)
    declaration = _workflow_declaration(
        recipe_id=document.id,
        revision=document.revision,
    )
    return WorkflowRecipe(cast(Callable[..., object], yaml_builder), declaration)


def _evaluate_binding(
    binding: _YamlBinding,
    parameters: Mapping[str, object],
    nodes: Mapping[str, object],
) -> object:
    if binding.kind == "parameter":
        return parameters[binding.name or ""]
    if binding.kind == "node":
        value = nodes[binding.name or ""]
        if binding.output is not None:
            if not isinstance(value, Mapping):
                raise CFBDRecipeConfigurationError(
                    "Selected YAML workflow output is unavailable"
                )
            return value[binding.output]
        return value
    if binding.kind == "literal":
        return binding.value
    if binding.kind == "list":
        return [_evaluate_binding(item, parameters, nodes) for item in binding.items]
    return {
        key: _evaluate_binding(item, parameters, nodes)
        for key, item in binding.entries.items()
    }


def _document_digest(document: _YamlDocument) -> str:
    payload = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_slug(value: str) -> None:
    if _IDENTIFIER.fullmatch(value) is None:
        raise CFBDRecipeConfigurationError("YAML node aliases must be slugs")


def _require_field_name(value: str) -> None:
    if not value.isidentifier() or value.startswith("_"):
        raise CFBDRecipeConfigurationError(
            "YAML parameter and schema names must be public identifiers"
        )


__all__ = ["load_recipe_yaml"]
