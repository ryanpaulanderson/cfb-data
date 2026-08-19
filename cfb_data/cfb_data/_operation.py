"""Define generic endpoint-operation ownership shared by resources and recipes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor, _response_contract, _serialize_request
from cfb_data._requests import _resolve_request


@dataclass(frozen=True, slots=True)
class _ManyEndpointOperation[RequestT: BaseModel, RowT: BaseModel]:
    """Own one validated model-list endpoint contract."""

    id: str
    revision: int
    endpoint: str
    request_type: type[RequestT]
    response_adapter: TypeAdapter[list[RowT]]
    row_model: type[RowT]
    access_tier: Literal["free", "tier_1", "tier_2"]
    documented_limit: int | None = None
    cost: int = 1

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

    def serialized_parameters(
        self, request: RequestT
    ) -> dict[str, str | int | float | bool]:
        """Return the exact typed upstream request parameters."""
        return _serialize_request(self.endpoint, request)
