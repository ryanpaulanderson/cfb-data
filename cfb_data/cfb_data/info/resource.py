"""Expose typed Info endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, TypeAlias, overload

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import UserUsageApi
from cfb_data.info.models.pydantic.requests import InfoUsageRequest
from cfb_data.info.models.pydantic.responses import UserInfo, UserUsage

_UserUsageApiArgument: TypeAlias = UserUsageApi | Literal["all", "cfb", "cbb"]

_USER_INFO = TypeAdapter(UserInfo)
_USER_USAGE = TypeAdapter(UserUsage)


class _EmptyRequest(BaseModel):
    """Represent the empty filter set accepted by ``GET /info``."""

    model_config = ConfigDict(extra="forbid")


_EMPTY_REQUEST = _EmptyRequest()


class InfoResource:
    """Provide validated operational account and usage metadata."""

    def __init__(self, executor: _EndpointExecutor) -> None:
        """Bind the namespace to shared endpoint execution."""
        self._executor = executor

    async def account(self) -> UserInfo:
        """Return metadata for the authenticated API account.

        :return: Validated account tier, quota, products, and feature access.
        :raises CFBDError: If transport or response validation fails.
        """
        return await self._executor.fetch_one(
            endpoint="/info",
            request=_EMPTY_REQUEST,
            response_adapter=_USER_INFO,
        )

    @overload
    async def usage(self, request: InfoUsageRequest, /) -> UserUsage: ...

    @overload
    async def usage(
        self,
        request: None = None,
        /,
        *,
        days: int | None = None,
        limit: int | None = None,
        api: _UserUsageApiArgument | None = None,
    ) -> UserUsage: ...

    async def usage(
        self, request: InfoUsageRequest | None = None, /, **filters: object
    ) -> UserUsage:
        """Return recent shared-pool usage for the authenticated account.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Validated request totals, endpoint aggregates, and recent calls.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, or response validation fails.
        """
        endpoint = "/info/usage"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=InfoUsageRequest,
            request=request,
            filters=filters,
        )
        return await self._executor.fetch_one(
            endpoint=endpoint,
            request=validated,
            response_adapter=_USER_USAGE,
        )


__all__ = ["InfoResource"]
