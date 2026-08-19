"""Define the bounded Arrow and JSON transport used by Dask providers."""

from __future__ import annotations

import hashlib
import inspect
import json
import platform
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from types import GenericAlias
from typing import Literal, cast, get_args, get_origin, get_type_hints

import pyarrow as pa
import pyarrow.ipc as ipc
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
)

from ._recipes import StepRecipe
from .errors import CFBDExecutorError

type _ParameterKind = Literal["json", "table"]
type _WorkerResult = tuple[bytes, bytes]

_PROTOCOL_VERSION = 1
_DIAGNOSTIC_LIMIT_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class _EncodedParameter:
    """Carry one bounded JSON or canonical Arrow transform parameter."""

    kind: _ParameterKind
    payload: bytes
    row_model: type[BaseModel] | None = None
    identity: _AnalyticsTableIdentity | None = None
    annotation: object | None = None


def _encode_parameters(
    recipe: StepRecipe[..., object],
    parameters: Mapping[str, object],
) -> tuple[Mapping[str, _EncodedParameter], int]:
    """Validate and encode coordinator-owned transform parameters."""
    hints = get_type_hints(recipe._function, include_extras=True)
    encoded: dict[str, _EncodedParameter] = {}
    total = 0
    for name, value in parameters.items():
        annotation = hints.get(name)
        if annotation is None:
            raise CFBDExecutorError(provider="dask", category="parameter_contract")
        row_model = _list_row_model(annotation)
        if row_model is not None:
            identity = _recipe_identity(recipe, label=f"input.{name}")
            try:
                rows = _row_list_adapter(row_model).validate_python(value, strict=True)
                table = _analytics_arrow_table_from_models(
                    row_model=row_model,
                    models=rows,
                    identity=identity,
                )
                payload = _write_ipc(table)
            except (ValidationError, ValueError, TypeError, pa.ArrowException) as exc:
                raise CFBDExecutorError(
                    provider="dask",
                    category="parameter_contract",
                ) from exc
            item = _EncodedParameter(
                kind="table",
                payload=payload,
                row_model=row_model,
                identity=identity,
            )
        else:
            try:
                adapter: TypeAdapter[object] = TypeAdapter(
                    annotation,
                    config=ConfigDict(strict=True),
                )
                payload = adapter.dump_json(value)
                adapter.validate_json(payload, strict=True)
                _validate_json_bytes(payload)
            except (ValidationError, ValueError, TypeError) as exc:
                raise CFBDExecutorError(
                    provider="dask",
                    category="parameter_contract",
                ) from exc
            item = _EncodedParameter(
                kind="json",
                payload=payload,
                annotation=annotation,
            )
        total += len(item.payload)
        encoded[name] = item
    return encoded, total


def _execute_transform_worker(
    function: Callable[..., object],
    parameters: Mapping[str, _EncodedParameter],
    output_model: type[BaseModel],
    output_identity: _AnalyticsTableIdentity,
    transfer_limit_bytes: int,
) -> _WorkerResult:
    """Execute one transport-only worker task without coordinator capabilities."""
    decoded: dict[str, object] = {}
    input_bytes = 0
    for name, parameter in parameters.items():
        input_bytes += len(parameter.payload)
        if input_bytes > transfer_limit_bytes:
            raise ValueError("transform input exceeds transfer limit")
        if parameter.kind == "table":
            if parameter.row_model is None or parameter.identity is None:
                raise ValueError("table parameter lacks its contract")
            decoded[name] = _decode_table_parameter(parameter)
            continue
        annotation = parameter.annotation
        if annotation is None:
            raise ValueError("JSON parameter lacks its contract")
        adapter: TypeAdapter[object] = TypeAdapter(
            annotation,
            config=ConfigDict(strict=True),
        )
        decoded[name] = adapter.validate_json(parameter.payload, strict=True)
    python_version = platform.python_version()
    raw = function(**decoded)
    if inspect.isawaitable(raw):
        raise TypeError("Dask transform returned an awaitable")
    rows = _row_list_adapter(output_model).validate_python(raw, strict=True)
    table = _analytics_arrow_table_from_models(
        row_model=output_model,
        models=rows,
        identity=output_identity,
    )
    payload = _write_ipc(table)
    if len(payload) > transfer_limit_bytes:
        raise ValueError("transform output exceeds transfer limit")
    diagnostics = json.dumps(
        {
            "input_bytes": input_bytes,
            "output_bytes": len(payload),
            "protocol": _PROTOCOL_VERSION,
            "python": python_version,
            "rows": len(rows),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    if len(diagnostics) > _DIAGNOSTIC_LIMIT_BYTES:
        raise ValueError("transform diagnostics exceed limit")
    return payload, diagnostics


def _decode_output(
    payload: bytes,
    row_model: type[BaseModel],
    identity: _AnalyticsTableIdentity,
) -> list[BaseModel]:
    """Revalidate a worker table at the coordinator boundary."""
    try:
        table = _read_ipc(payload)
        return _analytics_models_from_arrow_table(
            row_model=row_model,
            response_adapter=_row_list_adapter(row_model),
            table=table,
            identity=identity,
        )
    except (ValidationError, ValueError, TypeError, pa.ArrowException) as exc:
        raise CFBDExecutorError(
            provider="dask",
            category="output_contract",
        ) from exc


def _output_model(recipe: StepRecipe[..., object]) -> type[BaseModel]:
    """Return the required Pydantic output model for worker transport."""
    output = recipe._declaration.output_type
    if not isinstance(output, type) or not issubclass(output, BaseModel):
        raise CFBDExecutorError(provider="dask", category="output_contract")
    return output


def _recipe_identity(
    recipe: StepRecipe[..., object],
    *,
    label: str,
) -> _AnalyticsTableIdentity:
    """Derive a transport-only table identity from recipe metadata."""
    stable = recipe.id
    revision = recipe.revision
    if stable is None or revision is None:
        digest = hashlib.sha256(
            f"{recipe.__module__}:{recipe.__qualname__}:{label}".encode()
        ).hexdigest()
        return _AnalyticsTableIdentity(
            output_id=f"cfb_data.transport.{digest}",
            revision=1,
        )
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]
    return _AnalyticsTableIdentity(
        output_id=f"cfb_data.transport.{stable}.{digest}",
        revision=revision,
    )


def _worker_capabilities() -> bytes:
    """Return bounded worker environment evidence for the provider handshake."""
    return json.dumps(
        {
            "cfb_data": version("cfb-data"),
            "protocol": _PROTOCOL_VERSION,
            "pyarrow": version("pyarrow"),
            "pydantic": version("pydantic"),
            "python": (
                f"{platform.python_version_tuple()[0]}."
                f"{platform.python_version_tuple()[1]}"
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _validate_capabilities(
    capabilities: object,
    *,
    expected_workers: int,
) -> None:
    """Require every managed worker to match the coordinator environment."""
    if not isinstance(capabilities, Mapping) or len(capabilities) != expected_workers:
        raise CFBDExecutorError(provider="dask", category="capability")
    expected = _worker_capabilities()
    for address, payload in capabilities.items():
        if not isinstance(address, str) or not isinstance(payload, bytes):
            raise CFBDExecutorError(provider="dask", category="capability")
        if payload != expected:
            raise CFBDExecutorError(provider="dask", category="environment")


def _validate_diagnostics(payload: bytes) -> None:
    """Validate bounded worker diagnostics without trusting their contents."""
    if len(payload) > _DIAGNOSTIC_LIMIT_BYTES:
        raise CFBDExecutorError(provider="dask", category="diagnostics")
    try:
        value = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CFBDExecutorError(provider="dask", category="diagnostics") from exc
    if not isinstance(value, dict) or set(value) != {
        "input_bytes",
        "output_bytes",
        "protocol",
        "python",
        "rows",
    }:
        raise CFBDExecutorError(provider="dask", category="diagnostics")
    if value["protocol"] != _PROTOCOL_VERSION:
        raise CFBDExecutorError(provider="dask", category="diagnostics")
    if not all(
        isinstance(value[name], int) and not isinstance(value[name], bool)
        for name in ("input_bytes", "output_bytes", "rows")
    ) or not isinstance(value["python"], str):
        raise CFBDExecutorError(provider="dask", category="diagnostics")


def _decode_table_parameter(parameter: _EncodedParameter) -> list[BaseModel]:
    if parameter.row_model is None or parameter.identity is None:
        raise ValueError("table parameter lacks its contract")
    table = _read_ipc(parameter.payload)
    return _analytics_models_from_arrow_table(
        row_model=parameter.row_model,
        response_adapter=_row_list_adapter(parameter.row_model),
        table=table,
        identity=parameter.identity,
    )


def _write_ipc(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def _read_ipc(payload: bytes) -> pa.Table:
    source = pa.BufferReader(payload)
    with ipc.open_stream(source) as reader:
        table = reader.read_all()
    if source.tell() != len(payload):
        raise ValueError("Arrow stream contains trailing bytes")
    table.validate(full=True)
    return table


def _list_row_model(annotation: object) -> type[BaseModel] | None:
    if get_origin(annotation) is not list:
        return None
    arguments = get_args(annotation)
    if len(arguments) != 1:
        return None
    row_model = arguments[0]
    if isinstance(row_model, type) and issubclass(row_model, BaseModel):
        return row_model
    return None


def _row_list_adapter(row_model: type[BaseModel]) -> TypeAdapter[list[BaseModel]]:
    list_type = GenericAlias(list, row_model)
    return cast(TypeAdapter[list[BaseModel]], TypeAdapter(list_type))


def _validate_json_bytes(payload: bytes) -> None:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON token {value} is forbidden")

    json.loads(payload, parse_constant=reject_constant)


__all__: tuple[str, ...] = ()
