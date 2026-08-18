"""Build endpoint request models from the two supported call styles."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from cfb_data.errors import CFBDRequestValidationError


def _resolve_request[RequestT: BaseModel](
    *,
    endpoint: str,
    request_type: type[RequestT],
    request: BaseModel | None,
    filters: Mapping[str, object],
) -> RequestT:
    """Return a supplied request or validate explicit keyword filters."""
    if request is not None:
        if filters:
            raise TypeError(
                "Pass either one positional request model or keyword filters, not both"
            )
        if not isinstance(request, request_type):
            raise TypeError(
                f"{endpoint} requires {request_type.__name__}, "
                f"not {type(request).__name__}"
            )
        return request

    try:
        return request_type.model_validate(filters)
    except ValidationError as exc:
        raise CFBDRequestValidationError(endpoint=endpoint) from exc
