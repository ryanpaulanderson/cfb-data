"""Expose typed Venues endpoints through the primary client."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data.venues.models.pydantic.responses import Venue

_FrameT = TypeVar("_FrameT")
_VENUE_ROWS = TypeAdapter(list[Venue])


class _VenuesRequest(BaseModel):
    """Represent the empty filter set accepted by ``GET /venues``."""

    model_config = ConfigDict(extra="forbid")


_VENUES_REQUEST = _VenuesRequest()


class VenuesResource(Generic[_FrameT]):
    """Provide validated Venues endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[_FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    async def list(self) -> _FrameT:
        """Return venues in upstream order as the selected DataFrame type.

        :return: Eager frame containing validated ``Venue`` rows.
        :raises CFBDError: If transport, response, or conversion fails.
        """
        endpoint = "/venues"
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=_VENUES_REQUEST,
            response_adapter=_VENUE_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=Venue,
            models=rows,
        )
