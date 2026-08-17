"""Execute endpoints through request serialization and Pydantic validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._observability import (
    _EventDispatcher,
    _failure_category,
    _OperationContext,
)
from cfb_data._transport import _HTTPTransport
from cfb_data.base.types import (
    json_list,
    json_object,
    json_object_list,
    query_parameters,
)
from cfb_data.cache._coordinator import CacheCoordinator
from cfb_data.errors import (
    CFBDRequestValidationError,
    CFBDResponseValidationError,
    _sanitized_cause,
)
from cfb_data.observability import (
    RetrievalFinished,
    RetrievalOutcome,
    RetrievalStarted,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_ValueT = TypeVar("_ValueT")


class _EndpointExecutor:
    """Return validated models without depending on DataFrame presentation."""

    def __init__(
        self,
        transport: _HTTPTransport,
        cache_coordinator: CacheCoordinator,
        *,
        event_dispatcher: _EventDispatcher,
    ) -> None:
        """Bind endpoint execution to one owned transport.

        :param transport: Context-managed transport used by all endpoint calls.
        :param cache_coordinator: Cache policy and refresh coordinator.
        :param event_dispatcher: Optional-observer event dispatcher.
        """
        self._transport = transport
        self._cache_coordinator = cache_coordinator
        self._event_dispatcher = event_dispatcher

    async def fetch_many(
        self,
        *,
        endpoint: str,
        request: BaseModel,
        response_adapter: TypeAdapter[list[_ModelT]],
    ) -> list[_ModelT]:
        """Fetch and validate a list response in API order.

        :param endpoint: Fixed endpoint path.
        :param request: Validated endpoint request model.
        :param response_adapter: Typed list-response validator.
        :return: Validated models in upstream row order.
        :raises CFBDResponseValidationError: If response shape or values fail.
        """
        return await self._execute(
            endpoint=endpoint,
            request=request,
            response_contract=_response_contract(response_adapter),
            validate=lambda raw: _validate_many(endpoint, raw, response_adapter),
        )

    async def fetch_one(
        self,
        *,
        endpoint: str,
        request: BaseModel,
        response_adapter: TypeAdapter[_ModelT],
    ) -> _ModelT:
        """Fetch and validate one model response.

        :param endpoint: Fixed endpoint path.
        :param request: Validated endpoint request model.
        :param response_adapter: Typed object-response validator.
        :return: Validated response model.
        :raises CFBDResponseValidationError: If response shape or values fail.
        """
        return await self._execute(
            endpoint=endpoint,
            request=request,
            response_contract=_response_contract(response_adapter),
            validate=lambda raw: _validate_one(endpoint, raw, response_adapter),
        )

    async def fetch_values(
        self,
        *,
        endpoint: str,
        request: BaseModel,
        response_adapter: TypeAdapter[list[_ValueT]],
    ) -> list[_ValueT]:
        """Fetch and validate a JSON-array response in API order.

        :param endpoint: Fixed endpoint path.
        :param request: Validated endpoint request model.
        :param response_adapter: Typed array-response validator.
        :return: Validated values in upstream order.
        :raises CFBDResponseValidationError: If response shape or values fail.
        """
        return await self._execute(
            endpoint=endpoint,
            request=request,
            response_contract=_response_contract(response_adapter),
            validate=lambda raw: _validate_values(endpoint, raw, response_adapter),
        )

    async def _execute[ValueT](
        self,
        *,
        endpoint: str,
        request: BaseModel,
        response_contract: str,
        validate: Callable[[object], ValueT],
    ) -> ValueT:
        """Execute and observe one serialized, validated endpoint retrieval.

        :param endpoint: Fixed endpoint path.
        :param request: Validated endpoint request model.
        :param response_contract: Stable response-schema fingerprint.
        :param validate: Callable that validates the decoded response.
        :return: Validated response value.
        """
        parameters = _serialize_request(endpoint, request)
        context = self._event_dispatcher.new_operation(endpoint)
        if context is not None:
            self._event_dispatcher.emit(
                RetrievalStarted(
                    client_id=context.client_id,
                    operation_id=context.operation_id,
                    endpoint=endpoint,
                    parameter_names=tuple(sorted(parameters)),
                    cache_mode=self._cache_coordinator.current_mode,
                )
            )
        try:
            value = await self._cache_coordinator.execute(
                endpoint=endpoint,
                parameters=parameters,
                response_contract=response_contract,
                validate=validate,
                context=context,
            )
        except asyncio.CancelledError as exc:
            self._emit_finished(context, RetrievalOutcome.cancelled, None, exc)
            raise
        except Exception as exc:
            self._emit_finished(context, RetrievalOutcome.error, None, exc)
            raise
        self._emit_finished(context, RetrievalOutcome.success, _row_count(value), None)
        return value

    def _emit_finished(
        self,
        context: _OperationContext | None,
        outcome: RetrievalOutcome,
        row_count: int | None,
        error: BaseException | None,
    ) -> None:
        """Emit one terminal retrieval event when observation is enabled."""
        if context is None or not self._event_dispatcher.enabled:
            return
        self._event_dispatcher.emit(
            RetrievalFinished(
                client_id=context.client_id,
                operation_id=context.operation_id,
                endpoint=context.endpoint,
                outcome=outcome,
                source=context.source,
                row_count=row_count,
                duration_seconds=self._event_dispatcher.elapsed(context.started_at),
                failure_category=(
                    _failure_category(error) if error is not None else None
                ),
            )
        )


def _row_count(value: object) -> int:
    """Return the validated logical row count for one endpoint result."""
    return len(value) if isinstance(value, list) else 1


def _serialize_request(
    endpoint: str, request: BaseModel
) -> dict[str, str | int | float | bool]:
    """Serialize one validated request using its upstream aliases."""
    try:
        parameters = query_parameters(
            request.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        return parameters
    except TypeError as exc:
        safe_cause = _sanitized_cause(exc)
    raise CFBDRequestValidationError(endpoint=endpoint) from safe_cause


def _response_contract[ValueT](response_adapter: TypeAdapter[ValueT]) -> str:
    """Return a versioned deterministic identity for a Pydantic response schema."""
    schema = json.dumps(
        response_adapter.json_schema(), sort_keys=True, separators=(",", ":")
    ).encode()
    return f"pydantic-json-schema:v1:{hashlib.sha256(schema).hexdigest()}"


def _validate_many[ModelT: BaseModel](
    endpoint: str,
    raw: object,
    response_adapter: TypeAdapter[list[ModelT]],
) -> list[ModelT]:
    """Validate one decoded model-list response with a sanitized cause."""
    try:
        return response_adapter.validate_python(json_object_list(raw))
    except (TypeError, ValidationError) as exc:
        safe_cause = _sanitized_cause(exc)
    raise CFBDResponseValidationError(endpoint=endpoint) from safe_cause


def _validate_one[ModelT: BaseModel](
    endpoint: str,
    raw: object,
    response_adapter: TypeAdapter[ModelT],
) -> ModelT:
    """Validate one decoded model response with a sanitized cause."""
    try:
        return response_adapter.validate_python(json_object(raw))
    except (TypeError, ValidationError) as exc:
        safe_cause = _sanitized_cause(exc)
    raise CFBDResponseValidationError(endpoint=endpoint) from safe_cause


def _validate_values[ValueT](
    endpoint: str,
    raw: object,
    response_adapter: TypeAdapter[list[ValueT]],
) -> list[ValueT]:
    """Validate one decoded scalar-list response with a sanitized cause."""
    try:
        return response_adapter.validate_python(json_list(raw))
    except (TypeError, ValidationError) as exc:
        safe_cause = _sanitized_cause(exc)
    raise CFBDResponseValidationError(endpoint=endpoint) from safe_cause
