"""Expose typed Conferences endpoints through the primary client."""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from typing import Literal, TypeVar, overload

from pydantic import BaseModel, TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.conferences.models.pydantic.requests import (
    ConferenceAffiliationsRequest,
    ConferenceChangesRequest,
    ConferencesRequest,
)
from cfb_data.conferences.models.pydantic.responses import (
    Conference,
    ConferenceClassification,
    TeamConferenceAffiliation,
    TeamConferenceChange,
)

_RequestT = TypeVar("_RequestT", bound=BaseModel)
_RowT = TypeVar("_RowT", bound=BaseModel)
type _ClassificationArgument = (
    ConferenceClassification | Literal["fbs", "fcs", "ii", "ii/iii", "iii"]
)
_CONFERENCE_ROWS = TypeAdapter(list[Conference])
_CHANGE_ROWS = TypeAdapter(list[TeamConferenceChange])
_AFFILIATION_ROWS = TypeAdapter(list[TeamConferenceAffiliation])


class ConferencesResource[FrameT]:
    """Provide Conferences endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: ConferencesRequest, /) -> FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        year: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def list(
        self, request: ConferencesRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return conferences as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Conference`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/conferences",
            request_type=ConferencesRequest,
            request=request,
            filters=filters,
            response_adapter=_CONFERENCE_ROWS,
            row_model=Conference,
        )

    @overload
    async def changes(self, request: ConferenceChangesRequest, /) -> FrameT: ...

    @overload
    async def changes(self, request: None = None, /, *, year: int) -> FrameT: ...

    async def changes(
        self, request: ConferenceChangesRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team conference changes as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated change rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/conferences/changes",
            request_type=ConferenceChangesRequest,
            request=request,
            filters=filters,
            response_adapter=_CHANGE_ROWS,
            row_model=TeamConferenceChange,
        )

    @overload
    async def affiliations(
        self, request: ConferenceAffiliationsRequest, /
    ) -> FrameT: ...

    @overload
    async def affiliations(
        self,
        request: None = None,
        /,
        *,
        team: str | None = None,
        conference: str | None = None,
        year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def affiliations(
        self,
        request: ConferenceAffiliationsRequest | None = None,
        /,
        **filters: object,
    ) -> FrameT:
        """Return historical affiliations as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated affiliation rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await self._fetch_many(
            endpoint="/conferences/affiliations",
            request_type=ConferenceAffiliationsRequest,
            request=request,
            filters=filters,
            response_adapter=_AFFILIATION_ROWS,
            row_model=TeamConferenceAffiliation,
        )

    async def _fetch_many(
        self,
        *,
        endpoint: str,
        request_type: type[_RequestT],
        request: _RequestT | None,
        filters: Mapping[str, object],
        response_adapter: TypeAdapter[builtins.list[_RowT]],
        row_model: type[_RowT],
    ) -> FrameT:
        """Validate, fetch, and convert one Conferences list route."""
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=request_type,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint,
            request=validated,
            response_adapter=response_adapter,
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint,
            row_model=row_model,
            models=rows,
        )
