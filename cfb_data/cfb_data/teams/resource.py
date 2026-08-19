"""Expose typed Teams endpoints through the primary client."""

from __future__ import annotations

from typing import Literal, overload

from pydantic import TypeAdapter

from cfb_data._dataframes import _DataFrameAdapter
from cfb_data._executor import _EndpointExecutor
from cfb_data._requests import _resolve_request
from cfb_data.enums import Classification
from cfb_data.teams._operations import ROSTER_LIST, TEAM_ATS, TEAM_TALENT, TEAMS_LIST
from cfb_data.teams.models.pydantic.requests import (
    FBSTeamsRequest,
    RosterRequest,
    TalentRequest,
    TeamATSRequest,
    TeamMatchupRequest,
    TeamsRequest,
)
from cfb_data.teams.models.pydantic.responses import (
    Matchup,
    Team,
)

type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
_TEAM_ROWS = TypeAdapter(list[Team])
_MATCHUP = TypeAdapter(Matchup)


class TeamsResource[FrameT]:
    """Provide validated Teams endpoints with backend-specific frame results."""

    def __init__(
        self,
        executor: _EndpointExecutor,
        dataframe_adapter: _DataFrameAdapter[FrameT],
    ) -> None:
        """Bind the namespace to shared execution and presentation services."""
        self._executor = executor
        self._dataframe_adapter = dataframe_adapter

    @overload
    async def list(self, request: TeamsRequest, /) -> FrameT: ...

    @overload
    async def list(
        self,
        request: None = None,
        /,
        *,
        conference: str | None = None,
        year: int | None = None,
    ) -> FrameT: ...

    async def list(
        self, request: TeamsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return teams as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Team`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAMS_LIST.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def fbs(self, request: FBSTeamsRequest, /) -> FrameT: ...

    @overload
    async def fbs(
        self, request: None = None, /, *, year: int | None = None
    ) -> FrameT: ...

    async def fbs(
        self, request: FBSTeamsRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return FBS teams as the selected DataFrame type.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``Team`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/teams/fbs"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=FBSTeamsRequest,
            request=request,
            filters=filters,
        )
        rows = await self._executor.fetch_many(
            endpoint=endpoint, request=validated, response_adapter=_TEAM_ROWS
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=Team, models=rows
        )

    @overload
    async def matchup(self, request: TeamMatchupRequest, /) -> FrameT: ...

    @overload
    async def matchup(
        self,
        request: None = None,
        /,
        *,
        team1: str,
        team2: str,
        min_year: int | None = None,
        max_year: int | None = None,
    ) -> FrameT: ...

    async def matchup(
        self, request: TeamMatchupRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return one matchup summary with nested games as a selected frame.

        pandas stores ``games`` in an ``object`` column. Polars stores the same
        logical values in a native ``List[Struct]`` column.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: One-row eager frame containing the validated matchup summary.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        endpoint = "/teams/matchup"
        validated = _resolve_request(
            endpoint=endpoint,
            request_type=TeamMatchupRequest,
            request=request,
            filters=filters,
        )
        matchup = await self._executor.fetch_one(
            endpoint=endpoint, request=validated, response_adapter=_MATCHUP
        )
        return self._dataframe_adapter.from_models(
            endpoint=endpoint, row_model=Matchup, models=[matchup]
        )

    @overload
    async def ats(self, request: TeamATSRequest, /) -> FrameT: ...

    @overload
    async def ats(
        self,
        request: None = None,
        /,
        *,
        year: int,
        conference: str | None = None,
        team: str | None = None,
    ) -> FrameT: ...

    async def ats(
        self, request: TeamATSRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team against-the-spread records as the selected frame.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamATS`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_ATS.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def roster(self, request: RosterRequest, /) -> FrameT: ...

    @overload
    async def roster(
        self,
        request: None = None,
        /,
        *,
        team: str | None = None,
        year: int | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT: ...

    async def roster(
        self, request: RosterRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return historical roster players as the selected frame.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``RosterPlayer`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await ROSTER_LIST.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )

    @overload
    async def talent(self, request: TalentRequest, /) -> FrameT: ...

    @overload
    async def talent(self, request: None = None, /, *, year: int) -> FrameT: ...

    async def talent(
        self, request: TalentRequest | None = None, /, **filters: object
    ) -> FrameT:
        """Return team talent ratings as the selected frame.

        :param request: Validated request model, mutually exclusive with filters.
        :param filters: Explicit snake-case endpoint filters.
        :return: Eager frame containing validated ``TeamTalent`` rows.
        :raises TypeError: If request styles are mixed or the model type is wrong.
        :raises CFBDError: If request, transport, response, or conversion fails.
        """
        return await TEAM_TALENT.fetch_frame(
            self._executor,
            self._dataframe_adapter,
            request=request,
            filters=filters,
        )
