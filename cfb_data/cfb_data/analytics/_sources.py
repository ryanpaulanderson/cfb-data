"""Own typed endpoint operations shared by analytics source nodes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from pydantic import BaseModel, TypeAdapter

from cfb_data._executor import _EndpointExecutor
from cfb_data.analytics.contracts import SourceNode, TableContract, ValueBinding
from cfb_data.betting.models.pydantic.requests import BettingLinesRequest
from cfb_data.betting.models.pydantic.responses import BettingGame
from cfb_data.coaches.models.pydantic.requests import CoachSeasonsRequest
from cfb_data.coaches.models.pydantic.responses import DetailedCoachSeason
from cfb_data.drives.models.pydantic.requests import DrivesRequest
from cfb_data.drives.models.pydantic.responses import Drive
from cfb_data.errors import CFBDDefinitionError
from cfb_data.games.models.pydantic.requests import (
    GamesRequest,
    PlayerGameStatsRequest,
    RecordsRequest,
    TeamGameStatsRequest,
)
from cfb_data.games.models.pydantic.responses import (
    Game,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)
from cfb_data.plays.models.pydantic.requests import PlaysRequest
from cfb_data.plays.models.pydantic.responses import Play
from cfb_data.rankings.models.pydantic.requests import RankingsRequest
from cfb_data.rankings.models.pydantic.responses import PollWeek
from cfb_data.recruiting.models.pydantic.requests import (
    RecruitingPlayersRequest,
    RecruitingTeamsRequest,
)
from cfb_data.recruiting.models.pydantic.responses import (
    Recruit,
    TeamRecruitingRanking,
)
from cfb_data.stats.models.pydantic.requests import (
    AdvancedSeasonStatsRequest,
    PlayerSeasonStatsRequest,
    TeamSeasonStatsRequest,
)
from cfb_data.stats.models.pydantic.responses import (
    AdvancedSeasonStat,
    PlayerStat,
    TeamStat,
)
from cfb_data.teams.models.pydantic.requests import RosterRequest
from cfb_data.teams.models.pydantic.responses import RosterPlayer


@dataclass(frozen=True, slots=True)
class EndpointOperation[RequestT: BaseModel, RowT: BaseModel]:
    """Bind stable source identity to request and response validation."""

    id: str
    revision: int
    endpoint: str
    request_model: type[RequestT]
    response_adapter: TypeAdapter[list[RowT]]
    output: TableContract[RowT]
    access_tier: int = 0
    response_limit: int | None = None

    async def fetch(self, executor: _EndpointExecutor, request: RequestT) -> list[RowT]:
        """Execute and validate one endpoint source operation."""
        return await executor.fetch_many(
            endpoint=self.endpoint,
            request=request,
            response_adapter=self.response_adapter,
        )

    @property
    def request_contract_digest(self) -> str:
        """Return a deterministic request-schema digest."""
        encoded = json.dumps(
            self.request_model.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _contract[RowT: BaseModel](
    id: str,
    row_model: type[RowT],
    *,
    grain: str,
    keys: tuple[str, ...],
    order_by: tuple[str, ...],
    event_time: str | None = None,
) -> TableContract[RowT]:
    return TableContract(
        id=id,
        revision=1,
        row_model=row_model,
        grain=grain,
        keys=keys,
        order_by=order_by,
        event_time=event_time,
    )


_OPERATIONS = (
    EndpointOperation(
        "cfbd.games.list",
        1,
        "/games",
        GamesRequest,
        TypeAdapter(list[Game]),
        _contract(
            "cfbd.source.games",
            Game,
            grain="one upstream game",
            keys=("id",),
            order_by=("season", "week", "start_date", "id"),
            event_time="start_date",
        ),
    ),
    EndpointOperation(
        "cfbd.games.team_stats",
        1,
        "/games/teams",
        TeamGameStatsRequest,
        TypeAdapter(list[TeamGameStats]),
        _contract(
            "cfbd.source.team_game_stats",
            TeamGameStats,
            grain="one upstream game with nested team statistics",
            keys=("id",),
            order_by=("id",),
        ),
    ),
    EndpointOperation(
        "cfbd.games.player_stats",
        1,
        "/games/players",
        PlayerGameStatsRequest,
        TypeAdapter(list[PlayerGameStats]),
        _contract(
            "cfbd.source.player_game_stats",
            PlayerGameStats,
            grain="one upstream game with nested player statistics",
            keys=("id",),
            order_by=("id",),
        ),
    ),
    EndpointOperation(
        "cfbd.games.records",
        1,
        "/records",
        RecordsRequest,
        TypeAdapter(list[TeamRecords]),
        _contract(
            "cfbd.source.team_records",
            TeamRecords,
            grain="one upstream team season record",
            keys=("year", "team_id"),
            order_by=("year", "team_id"),
        ),
    ),
    EndpointOperation(
        "cfbd.drives.list",
        1,
        "/drives",
        DrivesRequest,
        TypeAdapter(list[Drive]),
        _contract(
            "cfbd.source.drives",
            Drive,
            grain="one upstream game-scoped drive",
            keys=("game_id", "id"),
            order_by=("game_id", "drive_number", "id"),
        ),
    ),
    EndpointOperation(
        "cfbd.plays.list",
        1,
        "/plays",
        PlaysRequest,
        TypeAdapter(list[Play]),
        _contract(
            "cfbd.source.plays",
            Play,
            grain="one upstream game-scoped play",
            keys=("game_id", "id"),
            order_by=("game_id", "drive_number", "play_number", "id"),
            event_time="wallclock",
        ),
    ),
    EndpointOperation(
        "cfbd.teams.roster",
        1,
        "/roster",
        RosterRequest,
        TypeAdapter(list[RosterPlayer]),
        _contract(
            "cfbd.source.roster",
            RosterPlayer,
            grain="one upstream athlete roster membership",
            keys=("team", "id"),
            order_by=("team", "id"),
        ),
    ),
    EndpointOperation(
        "cfbd.stats.team_season",
        1,
        "/stats/season",
        TeamSeasonStatsRequest,
        TypeAdapter(list[TeamStat]),
        _contract(
            "cfbd.source.team_season_stats",
            TeamStat,
            grain="one named team statistic in one season",
            keys=("season", "team", "stat_name"),
            order_by=("season", "team", "stat_name"),
        ),
    ),
    EndpointOperation(
        "cfbd.stats.team_season_advanced",
        1,
        "/stats/season/advanced",
        AdvancedSeasonStatsRequest,
        TypeAdapter(list[AdvancedSeasonStat]),
        _contract(
            "cfbd.source.team_season_advanced",
            AdvancedSeasonStat,
            grain="one advanced team season record",
            keys=("season", "team"),
            order_by=("season", "team"),
        ),
    ),
    EndpointOperation(
        "cfbd.stats.player_season",
        1,
        "/stats/player/season",
        PlayerSeasonStatsRequest,
        TypeAdapter(list[PlayerStat]),
        _contract(
            "cfbd.source.player_season_stats",
            PlayerStat,
            grain="one named athlete statistic in one season",
            keys=("season", "team", "player_id", "category", "stat_type"),
            order_by=("season", "team", "player_id", "category", "stat_type"),
        ),
    ),
    EndpointOperation(
        "cfbd.rankings.list",
        1,
        "/rankings",
        RankingsRequest,
        TypeAdapter(list[PollWeek]),
        _contract(
            "cfbd.source.rankings",
            PollWeek,
            grain="one upstream poll week",
            keys=("season", "season_type", "week"),
            order_by=("season", "season_type", "week"),
        ),
    ),
    EndpointOperation(
        "cfbd.betting.lines",
        1,
        "/lines",
        BettingLinesRequest,
        TypeAdapter(list[BettingGame]),
        _contract(
            "cfbd.source.betting_games",
            BettingGame,
            grain="one upstream game with nested provider quotes",
            keys=("id",),
            order_by=("season", "week", "start_date", "id"),
            event_time="start_date",
        ),
    ),
    EndpointOperation(
        "cfbd.recruiting.team_rankings",
        1,
        "/recruiting/teams",
        RecruitingTeamsRequest,
        TypeAdapter(list[TeamRecruitingRanking]),
        _contract(
            "cfbd.source.recruiting_team_rankings",
            TeamRecruitingRanking,
            grain="one upstream team recruiting ranking",
            keys=("year", "team"),
            order_by=("year", "rank", "team"),
        ),
    ),
    EndpointOperation(
        "cfbd.recruiting.players",
        1,
        "/recruiting/players",
        RecruitingPlayersRequest,
        TypeAdapter(list[Recruit]),
        _contract(
            "cfbd.source.recruits",
            Recruit,
            grain="one upstream recruiting prospect",
            keys=("id",),
            order_by=("year", "ranking", "id"),
        ),
    ),
    EndpointOperation(
        "cfbd.coaches.seasons",
        1,
        "/coaches/seasons",
        CoachSeasonsRequest,
        TypeAdapter(list[DetailedCoachSeason]),
        _contract(
            "cfbd.source.coach_seasons",
            DetailedCoachSeason,
            grain="one upstream coach-team-season record",
            keys=("coach", "team", "year"),
            order_by=("year", "coach", "team"),
        ),
    ),
)

ENDPOINT_OPERATIONS = MappingProxyType(
    {
        operation.id: cast(EndpointOperation[BaseModel, BaseModel], operation)
        for operation in _OPERATIONS
    }
)


def endpoint_operation(operation_id: str) -> EndpointOperation[BaseModel, BaseModel]:
    """Resolve a registered internal endpoint operation by stable ID."""
    try:
        return ENDPOINT_OPERATIONS[operation_id]
    except KeyError as exc:
        raise CFBDDefinitionError(
            f"Unknown analytics source operation: {operation_id}"
        ) from exc


def registered_source(
    node_id: str,
    operation_id: str,
    *,
    bindings: Mapping[str, ValueBinding],
) -> SourceNode:
    """Create a source node from one allowlisted endpoint operation.

    :param node_id: Definition-local stable node ID.
    :param operation_id: Registered endpoint operation ID, never a raw path.
    :param bindings: Explicit request-field parameter or literal bindings.
    :return: Immutable source node with the authoritative source table contract.
    :raises CFBDDefinitionError: If the source operation is unknown.
    """
    operation = endpoint_operation(operation_id)
    return SourceNode(
        id=node_id,
        operation_id=operation.id,
        operation_revision=operation.revision,
        bindings=bindings,
        output=operation.output,
    )


__all__ = ["EndpointOperation", "registered_source"]
