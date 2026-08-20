"""Define generic endpoint-operation ownership shared by resources and recipes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import GenericAlias
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor, _response_contract, _serialize_request
from cfb_data._requests import _resolve_request


class _EndpointOperation[RequestT: BaseModel, RowT: BaseModel](ABC):
    """Own the common contract for one validated endpoint operation."""

    id: str
    revision: int
    endpoint: str
    request_type: type[RequestT]
    row_model: type[RowT]
    access_tier: Literal["free", "tier_1", "tier_2"]
    documented_limit: int | None
    cost: int

    def resolve(
        self,
        request: RequestT | None,
        filters: dict[str, object],
    ) -> RequestT:
        """Return the one authoritative validated request model."""
        return _resolve_request(
            endpoint=self.endpoint,
            request_type=self.request_type,
            request=request,
            filters=filters,
        )

    @abstractmethod
    async def fetch(
        self,
        executor: _EndpointExecutor,
        request: RequestT,
    ) -> list[RowT]:
        """Return one normalized row list through the shared executor."""

    @property
    @abstractmethod
    def rows_adapter(self) -> TypeAdapter[list[RowT]]:
        """Return the adapter for the normalized analytical row list."""

    @property
    @abstractmethod
    def response_contract(self) -> str:
        """Return the actual HTTP response schema fingerprint."""

    def serialized_parameters(
        self, request: RequestT
    ) -> dict[str, str | int | float | bool]:
        """Return the exact typed upstream request parameters."""
        return _serialize_request(self.endpoint, request)


@dataclass(frozen=True, slots=True)
class _ManyEndpointOperation[RequestT: BaseModel, RowT: BaseModel](
    _EndpointOperation[RequestT, RowT]
):
    """Own one endpoint whose HTTP response is a model list."""

    id: str
    revision: int
    endpoint: str
    request_type: type[RequestT]
    response_adapter: TypeAdapter[list[RowT]]
    row_model: type[RowT]
    access_tier: Literal["free", "tier_1", "tier_2"]
    documented_limit: int | None = None
    cost: int = 1

    async def fetch(
        self,
        executor: _EndpointExecutor,
        request: RequestT,
    ) -> list[RowT]:
        """Return validated rows through the shared endpoint executor."""
        return await executor.fetch_many(
            endpoint=self.endpoint,
            request=request,
            response_adapter=self.response_adapter,
        )

    @property
    def rows_adapter(self) -> TypeAdapter[list[RowT]]:
        """Return the HTTP list adapter as the analytical row adapter."""
        return self.response_adapter

    async def fetch_frame[FrameT](
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
        request: RequestT | None,
        filters: dict[str, object],
    ) -> FrameT:
        """Validate, retrieve, and present rows for a public resource method."""
        validated = self.resolve(request, filters)
        rows = await self.fetch(executor, validated)
        return dataframe_adapter.from_models(
            endpoint=self.endpoint,
            row_model=self.row_model,
            models=rows,
        )

    @property
    def response_contract(self) -> str:
        """Return the stable response schema fingerprint used by the cache."""
        return _response_contract(self.response_adapter)


@dataclass(frozen=True, slots=True)
class _OneEndpointOperation[RequestT: BaseModel, RowT: BaseModel](
    _EndpointOperation[RequestT, RowT]
):
    """Own one endpoint whose HTTP response is one validated model."""

    id: str
    revision: int
    endpoint: str
    request_type: type[RequestT]
    response_adapter: TypeAdapter[RowT]
    row_model: type[RowT]
    access_tier: Literal["free", "tier_1", "tier_2"]
    documented_limit: int | None = None
    cost: int = 1

    async def fetch(
        self,
        executor: _EndpointExecutor,
        request: RequestT,
    ) -> list[RowT]:
        """Wrap the validated HTTP object in the analytical row list."""
        return [await self.fetch_one(executor, request)]

    async def fetch_one(
        self,
        executor: _EndpointExecutor,
        request: RequestT,
    ) -> RowT:
        """Return the validated object through the shared endpoint executor."""
        return await executor.fetch_one(
            endpoint=self.endpoint,
            request=request,
            response_adapter=self.response_adapter,
        )

    @property
    def rows_adapter(self) -> TypeAdapter[list[RowT]]:
        """Return the normalized analytical row-list adapter."""
        annotation = GenericAlias(list, self.row_model)
        return TypeAdapter(annotation)

    @property
    def response_contract(self) -> str:
        """Return the stable single-object response schema fingerprint."""
        return _response_contract(self.response_adapter)
