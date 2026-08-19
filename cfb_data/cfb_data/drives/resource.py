"""Expose typed drive endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from pydantic import TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.drives.models.pydantic.requests import DrivesRequest
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.enums import Classification, SeasonType

type _SeasonTypeArgument = (
    SeasonType
    | Literal[
        "regular",
        "postseason",
        "both",
        "allstar",
        "spring_regular",
        "spring_postseason",
    ]
)
type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
_DRIVE_ROWS = TypeAdapter(list[Drive])


class DrivesResource[FrameT]:
    """Provide validated Drives endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: DrivesRequest, /) -> FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        year: int,
        season_type: _SeasonTypeArgument | None = None,
        week: int | None = None,
        team: str | None = None,
        offense: str | None = None,
        defense: str | None = None,
        conference: str | None = None,
        offense_conference: str | None = None,
        defense_conference: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def list(
        self,
        request: DrivesRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return drives in upstream order as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Drive`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/drives"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=DrivesRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=_DRIVE_ROWS,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=Drive,
            models=rows,
        )
