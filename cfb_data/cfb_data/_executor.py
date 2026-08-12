"""Execute endpoints through request serialization and Pydantic validation."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._transport import _HTTPTransport
from cfb_data.base.types import json_object, json_object_list, query_parameters
from cfb_data.errors import (
    CFBDRequestValidationError,
    CFBDResponseValidationError,
    _sanitized_cause,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class _EndpointExecutor:
    """Return validated models without depending on DataFrame presentation."""

    def __init__(self, transport: _HTTPTransport) -> None:
        """Bind endpoint execution to one owned transport.

        :param transport: Context-managed transport used by all endpoint calls.
        """
        self._transport = transport

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
        raw = await self._transport.get_json(
            endpoint,
            _serialize_request(endpoint, request),
        )
        try:
            payload = json_object_list(raw)
            return response_adapter.validate_python(payload)
        except (TypeError, ValidationError) as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDResponseValidationError(endpoint=endpoint) from safe_cause

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
        raw = await self._transport.get_json(
            endpoint,
            _serialize_request(endpoint, request),
        )
        try:
            payload = json_object(raw)
            return response_adapter.validate_python(payload)
        except (TypeError, ValidationError) as exc:
            safe_cause = _sanitized_cause(exc)
        raise CFBDResponseValidationError(endpoint=endpoint) from safe_cause


def _serialize_request(
    endpoint: str, request: BaseModel
) -> dict[str, str | int | float | bool]:
    """Serialize one validated request using its upstream aliases."""
    try:
        return query_parameters(
            request.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
    except TypeError as exc:
        safe_cause = _sanitized_cause(exc)
    raise CFBDRequestValidationError(endpoint=endpoint) from safe_cause
