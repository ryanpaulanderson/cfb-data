"""Build game-partitioned athlete play-stat associations with coverage evidence."""

from __future__ import annotations

from enum import StrEnum

from cfb_data.analytics import (
    AdaptiveSourceContext,
    CFBDAttemptBudgetExceeded,
    RecipeRef,
    adaptive_source,
    dataset,
    step,
)
from cfb_data.games._operations import GAMES_LIST
from cfb_data.games.models.pydantic.responses import Game
from cfb_data.plays._operations import PLAY_STAT_TYPES, PLAYS_STATS
from cfb_data.plays.models.pydantic.responses import PlayStat, PlayStatType
from pydantic import model_validator


class _CoverageState(StrEnum):
    """Distinguish proven complete game partitions from useful partial ones."""

    complete = "complete"
    partial = "partial"


class PlayPlayerStatRow(PlayStat):
    """Preserve a source play stat and its game-level retrieval coverage."""

    coverage_state: _CoverageState
    coverage_warning: str | None

    @model_validator(mode="after")
    def validate_coverage(self) -> PlayPlayerStatRow:
        """Require a warning exactly when the game partition is partial.

        :return: The validated association and coverage state.
        :raises ValueError: If the warning and state disagree.
        """
        if (self.coverage_state == _CoverageState.partial) != bool(
            self.coverage_warning
        ):
            raise ValueError("Partial play-stat coverage requires a warning")
        return self


def _stat_limit() -> int:
    """Return the documented cap owned by the play-stat operation."""
    limit = PLAYS_STATS.documented_limit
    if limit is None or limit < 1:
        raise ValueError("The play-stat operation has no usable response limit")
    return limit


def _validate_game(games: list[Game], game_id: int) -> Game:
    """Return one exact game with two distinct named participants.

    :param games: Validated game rows from the exact-ID request.
    :param game_id: Requested game identifier.
    :return: The single matching game.
    :raises ValueError: If the game or its participants are ambiguous.
    """
    if len(games) != 1 or games[0].id != game_id:
        raise ValueError(f"Game {game_id} was missing or ambiguous in /games")
    game = games[0]
    if (
        not game.home_team.strip()
        or not game.away_team.strip()
        or game.home_team.casefold() == game.away_team.casefold()
    ):
        raise ValueError(f"Game {game_id} has invalid participant names")
    return game


def _validate_rows(
    rows: list[PlayStat],
    game: Game,
    *,
    limit: int,
    team: str | None = None,
    stat_type: PlayStatType | None = None,
) -> None:
    """Reject rows outside the exact requested game and partition.

    :param rows: Validated play-stat rows from one endpoint request.
    :param game: Exact game and participant context.
    :param limit: Documented maximum response row count.
    :param team: Optional exact team partition.
    :param stat_type: Optional exact statistic-type partition.
    :raises ValueError: If a row or the response size violates its partition.
    """
    if len(rows) > limit:
        raise ValueError(f"Game {game.id} play-stat response exceeded {limit} rows")
    participants = {
        game.home_team.casefold(): game.away_team.casefold(),
        game.away_team.casefold(): game.home_team.casefold(),
    }
    keys: set[tuple[int, str, str, str, str]] = set()
    for row in rows:
        key = _candidate_key(row)
        if key in keys:
            raise ValueError(f"Game {game.id} returned a duplicate play-stat key")
        keys.add(key)
        expected_opponent = participants.get(row.team.casefold())
        if (
            row.game_id != game.id
            or row.season != game.season
            or row.week != game.week
            or expected_opponent != row.opponent.casefold()
            or (team is not None and row.team.casefold() != team.casefold())
            or (stat_type is not None and row.stat_type != stat_type.name)
        ):
            raise ValueError(f"Game {game.id} returned a mismatched play-stat row")


def _candidate_key(row: PlayStat) -> tuple[int, str, str, str, str]:
    """Return the declared association key for one source row."""
    return row.game_id, row.play_id, row.team, row.athlete_id, row.stat_type


def _observed_union(rows: list[PlayStat], game_id: int) -> list[PlayStat]:
    """Keep each observed association once and reject conflicting versions.

    :param rows: Validated rows sampled from overlapping partitions.
    :param game_id: Game identifier used in failure diagnostics.
    :return: Distinct associations in first-observed order.
    :raises ValueError: If repeated keys have different source values.
    """
    observed: dict[tuple[int, str, str, str, str], PlayStat] = {}
    for row in rows:
        key = _candidate_key(row)
        previous = observed.get(key)
        if previous is not None:
            if previous.model_dump() != row.model_dump():
                raise ValueError(f"Game {game_id} play-stat partitions disagree")
            continue
        observed[key] = row
    return list(observed.values())


def _with_coverage(
    rows: list[PlayStat], *, warning: str | None
) -> list[PlayPlayerStatRow]:
    """Attach durable game-level coverage to source-faithful rows.

    :param rows: Distinct validated source associations for one game.
    :param warning: Reason that more associations may exist, if any.
    :return: Associations preserving all upstream fields and nulls.
    """
    return [
        PlayPlayerStatRow.model_validate(
            {
                **row.model_dump(by_alias=True),
                "coverage_state": "partial" if warning else "complete",
                "coverage_warning": warning,
            }
        )
        for row in rows
    ]


def _require_parent_covered(
    parent: list[PlayStat], children: list[PlayStat], game_id: int
) -> None:
    """Require every sampled capped parent row in the child union.

    :param parent: Rows observed in a capped containing partition.
    :param children: Rows assembled from its narrower partitions.
    :param game_id: Game identifier used in failure diagnostics.
    :raises ValueError: If a containing row is absent from the narrower result.
    """
    child_rows = {row.model_dump_json() for row in children}
    if any(row.model_dump_json() not in child_rows for row in parent):
        raise ValueError(f"Game {game_id} play-stat partitions disagree")


def _validate_types(types: list[PlayStatType], game_id: int) -> None:
    """Require a nonempty, unambiguous stat-type vocabulary.

    :param types: Validated source statistic types.
    :param game_id: Game identifier used in failure diagnostics.
    :raises ValueError: If the vocabulary cannot partition named output rows.
    """
    if not types or len({row.id for row in types}) != len(types):
        raise ValueError(f"Game {game_id} has an incomplete stat-type vocabulary")
    if len({row.name for row in types}) != len(types):
        raise ValueError(f"Game {game_id} has indistinguishable stat-type names")


@adaptive_source(
    id="cfbd.play_player_stats.complete_game",
    revision=1,
    output=PlayPlayerStatRow,
    operations=(GAMES_LIST, PLAYS_STATS, PLAY_STAT_TYPES),
    base_requests=2,
)
async def _complete_game(
    context: AdaptiveSourceContext, *, game_id: int
) -> list[PlayPlayerStatRow]:
    """Return validated associations with explicit partial coverage when needed.

    :param context: Budgeted, allowlisted endpoint retrieval context.
    :param game_id: Exact positive game identifier.
    :return: Source associations with durable game-level coverage evidence.
    :raises ValueError: If a partition is malformed or contradictory.
    """
    game = _validate_game(await context.retrieve(GAMES_LIST, game_id=game_id), game_id)
    limit = _stat_limit()
    all_rows = await context.retrieve(PLAYS_STATS, game_id=game_id)
    _validate_rows(all_rows, game, limit=limit)
    if len(all_rows) < limit:
        return _with_coverage(all_rows, warning=None)

    assembled: list[PlayStat] = []
    observed: list[PlayStat] = list(all_rows)
    incomplete: list[str] = []
    vocabulary: list[PlayStatType] | None = None
    try:
        for team in (game.home_team, game.away_team):
            team_rows = await context.retrieve(PLAYS_STATS, game_id=game_id, team=team)
            _validate_rows(team_rows, game, limit=limit, team=team)
            observed.extend(team_rows)
            if len(team_rows) < limit:
                assembled.extend(team_rows)
                continue
            if vocabulary is None:
                vocabulary = await context.retrieve(PLAY_STAT_TYPES)
                _validate_types(vocabulary, game_id)
            type_rows: list[PlayStat] = []
            for stat_type in sorted(vocabulary, key=lambda item: item.id):
                partition = await context.retrieve(
                    PLAYS_STATS,
                    game_id=game_id,
                    team=team,
                    stat_type_id=stat_type.id,
                )
                _validate_rows(
                    partition, game, limit=limit, team=team, stat_type=stat_type
                )
                observed.extend(partition)
                if len(partition) == limit:
                    incomplete.append(
                        f"team {team}, stat type {stat_type.id} reached the "
                        f"{limit:,}-row API limit"
                    )
                type_rows.extend(partition)
            _require_parent_covered(team_rows, type_rows, game_id)
            assembled.extend(type_rows)
    except CFBDAttemptBudgetExceeded as exc:
        return _with_coverage(
            _observed_union(observed, game_id),
            warning=(
                f"Game {game_id}: HTTP attempt budget {exc.limit} was exhausted "
                "before all capped partitions could be checked; more rows may exist"
            ),
        )
    _require_parent_covered(all_rows, assembled, game_id)
    distinct = _observed_union(assembled, game_id)
    if len(distinct) != len(assembled):
        raise ValueError(f"Game {game_id} returned a duplicate play-stat key")
    warning = (
        f"Game {game_id}: " + "; ".join(incomplete) + "; more rows may exist"
        if incomplete
        else None
    )
    return _with_coverage(distinct, warning=warning)


@step(id="cfbd.play_player_stats.merge_games", revision=1, output=PlayPlayerStatRow)
def _merge_games(
    groups: tuple[list[PlayPlayerStatRow], ...],
) -> list[PlayPlayerStatRow]:
    """Merge explicit game partitions in deterministic declared order."""
    return sorted(
        (row for group in groups for row in group),
        key=lambda row: (
            row.game_id,
            row.play_id,
            row.team,
            row.athlete_id,
            row.stat_type,
        ),
    )


@dataset(
    id="cfbd.play_player_stats",
    revision=1,
    row=PlayPlayerStatRow,
    grain="one athlete and named statistic association with a game play",
    keys=("game_id", "play_id", "team", "athlete_id", "stat_type"),
    order_by=("game_id", "play_id", "team", "athlete_id", "stat_type"),
    partition_by=("game_id",),
)
def play_player_stats(
    *, game_ids: tuple[int, ...] | list[int]
) -> RecipeRef[list[PlayPlayerStatRow]]:
    """Build play-player statistics with explicit game-level coverage.

    :param game_ids: Nonempty sequence of unique positive game identifiers.
    :return: Validated athlete play-stat rows and coverage markers.
    :raises ValueError: If the game list is empty, duplicated, or invalid.
    """
    if (
        not isinstance(game_ids, (tuple, list))
        or not game_ids
        or any(type(game_id) is not int or game_id <= 0 for game_id in game_ids)
        or len(set(game_ids)) != len(game_ids)
    ):
        raise ValueError("game_ids must contain unique positive game IDs")
    ordered_ids = tuple(game_ids)
    groups = tuple(
        _complete_game.as_(f"game-{game_id}")(game_id=game_id)
        for game_id in ordered_ids
    )
    return _merge_games(groups)


__all__ = ["play_player_stats"]
