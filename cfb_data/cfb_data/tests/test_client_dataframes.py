"""Test backend-neutral endpoint behavior through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.games.models.pydantic.responses import (
    Game,
    GameMedia,
    GameWeather,
    PlayerGameStats,
    TeamGameStats,
    TeamRecords,
)

from cfb_data import (
    AdvancedBoxScore,
    CalendarRequest,
    CFBDClient,
    CFBDRequestValidationError,
    CFBDResponseValidationError,
    GamesRequest,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _normalize_frame_value(value: object) -> object:
    """Normalize backend-native scalar containers for logical comparison."""
    if isinstance(value, dict):
        return {key: _normalize_frame_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_frame_value(item) for item in value]
    if isinstance(value, pl.Series):
        return [_normalize_frame_value(item) for item in value.to_list()]
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().astimezone(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if value is pd.NA or value is pd.NaT:
        return None
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_calendar_preserves_type_order_values_and_utc_dtype(
    api_server: ServerFactory,
    calendar_response: dict[str, object],
    backend: str,
) -> None:
    observed: dict[str, object] = {}

    async def handler(request: web.Request) -> web.Response:
        observed["path"] = request.path
        observed["query"] = dict(request.query)
        observed["authorization"] = request.headers.get("Authorization")
        return web.json_response([calendar_response])

    async with api_server(handler) as base_url:
        client = CFBDClient(
            "explicit-secret",
            dataframe_backend=backend,
            base_url=base_url,
        )
        async with client:
            frame = await client.games.calendar(year=2024)

    expected_columns = [
        "season",
        "week",
        "season_type",
        "start_date",
        "end_date",
        "first_game_start",
        "last_game_start",
    ]
    assert observed == {
        "path": "/calendar",
        "query": {"year": "2024"},
        "authorization": "Bearer explicit-secret",
    }
    if backend == "pandas":
        assert isinstance(frame, pd.DataFrame)
        assert list(frame.columns) == expected_columns
        assert str(frame.dtypes["season"]) == "int64"
        assert str(frame.dtypes["season_type"]) == "string"
        assert str(frame.dtypes["start_date"]) == "datetime64[ns, UTC]"
        assert frame.loc[0, "start_date"].hour == 4
    else:
        assert isinstance(frame, pl.DataFrame)
        assert frame.columns == expected_columns
        assert frame.schema["season"] == pl.Int64
        assert frame.schema["season_type"] == pl.String
        assert frame.schema["start_date"].time_zone == "UTC"
        assert frame["start_date"][0].utcoffset().total_seconds() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_game_frame_preserves_nulls_lists_structs_and_rows(
    api_server: ServerFactory,
    game_response: dict[str, object],
    backend: str,
) -> None:
    second = dict(game_response)
    second["id"] = 401628348
    second["homeTeam"] = "Georgia"

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response, second])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.games.list(GamesRequest(year=2024))

    expected_columns = list(Game.model_fields)
    if backend == "pandas":
        assert isinstance(frame, pd.DataFrame)
        assert list(frame.columns) == expected_columns
        assert len(frame) == 2
        assert str(frame.dtypes["attendance"]) == "Int64"
        assert str(frame.dtypes["home_postgame_win_probability"]) == "Float64"
        assert str(frame.dtypes["home_line_scores"]) == "object"
        assert str(frame.dtypes["playoff"]) == "object"
        assert pd.isna(frame.loc[0, "attendance"])
        assert frame.loc[0, "home_line_scores"] == [14.0, 28.0, 7.0, 14.0]
        assert frame.loc[0, "playoff"]["round_name"] == "First Round"
        assert isinstance(frame.index, pd.RangeIndex)
    else:
        assert isinstance(frame, pl.DataFrame)
        assert frame.columns == expected_columns
        assert frame.height == 2
        assert frame.schema["attendance"] == pl.Int64
        assert frame.schema["home_line_scores"] == pl.List(pl.Float64)
        assert isinstance(frame.schema["playoff"], pl.Struct)
        assert frame["attendance"][0] is None
        assert frame["home_line_scores"][0].to_list() == [14.0, 28.0, 7.0, 14.0]
        assert frame["playoff"].struct.field("round_name")[0] == "First Round"


@pytest.mark.asyncio
async def test_backends_preserve_identical_logical_values(
    api_server: ServerFactory,
    game_response: dict[str, object],
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as pandas_client:
            pandas_frame = await pandas_client.games.list(year=2024)
        async with CFBDClient(
            "key", dataframe_backend="polars", base_url=base_url
        ) as polars_client:
            polars_frame = await polars_client.games.list(year=2024)

    pandas_records = [
        _normalize_frame_value(record)
        for record in pandas_frame.to_dict(orient="records")
    ]
    polars_records = [
        _normalize_frame_value(record) for record in polars_frame.to_dicts()
    ]
    assert pandas_records == polars_records


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_empty_frames_retain_exact_schema(
    api_server: ServerFactory,
    backend: str,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.games.list(year=2024)

    assert list(frame.columns) == list(Game.model_fields)
    assert len(frame) == 0
    if backend == "pandas":
        assert str(frame.dtypes["attendance"]) == "Int64"
        assert str(frame.dtypes["start_date"]) == "datetime64[ns, UTC]"
        assert str(frame.dtypes["playoff"]) == "object"
    else:
        assert frame.schema["attendance"] == pl.Int64
        assert frame.schema["start_date"].time_zone == "UTC"
        assert isinstance(frame.schema["playoff"], pl.Struct)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_scoreboard_nested_contract_is_native_per_backend(
    api_server: ServerFactory,
    scoreboard_response: dict[str, object],
    backend: str,
) -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response([scoreboard_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.games.scoreboard(classification="fbs")

    if backend == "pandas":
        assert str(frame.dtypes["home_team"]) == "object"
        assert frame.loc[0, "home_team"]["win_probability"] == 0.98
    else:
        assert isinstance(frame.schema["home_team"], pl.Struct)
        assert frame["home_team"].struct.field("win_probability")[0] == 0.98


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_drive_endpoint_uses_the_same_public_interface(
    api_server: ServerFactory,
    drive_response: dict[str, object],
    backend: str,
) -> None:
    observed_query: dict[str, str] = {}

    async def handler(request: web.Request) -> web.Response:
        observed_query.update(request.query)
        return web.json_response([drive_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.drives.list(
                year=2024,
                season_type="regular",
                offense_conference="SEC",
            )

    assert observed_query == {
        "year": "2024",
        "seasonType": "regular",
        "offenseConference": "SEC",
    }
    if backend == "pandas":
        assert isinstance(frame, pd.DataFrame)
        assert frame.loc[0, "start_time"] == {"seconds": 0, "minutes": 15}
    else:
        assert isinstance(frame, pl.DataFrame)
        assert isinstance(frame.schema["start_time"], pl.Struct)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_all_remaining_tabular_endpoints_share_the_backend_contract(
    api_server: ServerFactory,
    backend: str,
) -> None:
    records = {
        "year": 2024,
        "teamId": 333,
        "team": "Alabama",
        "classification": "fbs",
        "conference": "SEC",
        "division": "West",
        "expectedWins": 9.4,
        "total": {"games": 13, "wins": 9, "losses": 4, "ties": 0},
        "conferenceGames": {"games": 8, "wins": 5, "losses": 3, "ties": 0},
        "homeGames": {"games": 7, "wins": 6, "losses": 1, "ties": 0},
        "awayGames": {"games": 5, "wins": 2, "losses": 3, "ties": 0},
        "neutralSiteGames": {"games": 1, "wins": 1, "losses": 0, "ties": 0},
        "regularSeason": {"games": 12, "wins": 9, "losses": 3, "ties": 0},
        "postseason": {"games": 1, "wins": 0, "losses": 1, "ties": 0},
    }
    media = {
        "id": 401628347,
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startTime": "2024-08-31T23:30:00Z",
        "isStartTimeTBD": False,
        "homeTeam": "Alabama",
        "homeConference": "SEC",
        "awayTeam": "Western Kentucky",
        "awayConference": None,
        "mediaType": "tv",
        "outlet": "ESPN",
    }
    weather = {
        "id": 401628347,
        "season": 2024,
        "week": 1,
        "seasonType": "regular",
        "startTime": "2024-08-31T23:30:00Z",
        "gameIndoors": False,
        "homeTeam": "Alabama",
        "homeConference": "SEC",
        "awayTeam": "Western Kentucky",
        "awayConference": None,
        "venueId": 365,
        "venue": "Bryant-Denny Stadium",
        "temperature": 84.0,
        "dewPoint": 70.0,
        "humidity": 58.0,
        "precipitation": 0.0,
        "snowfall": 0.0,
        "windDirection": 180.0,
        "windSpeed": 8.0,
        "pressure": 29.9,
        "weatherConditionCode": 2.0,
        "weatherCondition": "Partly cloudy",
    }
    payloads = {
        "/records": [records],
        "/games/media": [media],
        "/games/weather": [weather],
        "/games/players": [{"id": 401628347, "teams": []}],
        "/games/teams": [{"id": 401628347, "teams": []}],
    }
    observed_queries: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed_queries[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frames = [
                (await client.games.records(team="Alabama"), TeamRecords),
                (
                    await client.games.media(
                        year=2024,
                        season_type="regular",
                        media_type="tv",
                    ),
                    GameMedia,
                ),
                (await client.games.weather(game_id=401628347), GameWeather),
                (
                    await client.games.player_stats(game_id=401628347),
                    PlayerGameStats,
                ),
                (
                    await client.games.team_stats(game_id=401628347),
                    TeamGameStats,
                ),
            ]

    for frame, model in frames:
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1
        expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
        assert isinstance(frame, expected_type)

    assert observed_queries == {
        "/records": {"team": "Alabama"},
        "/games/media": {
            "year": "2024",
            "seasonType": "regular",
            "mediaType": "tv",
        },
        "/games/weather": {"gameId": "401628347"},
        "/games/players": {"id": "401628347"},
        "/games/teams": {"id": "401628347"},
    }


@pytest.mark.asyncio
async def test_request_object_and_keywords_are_mutually_exclusive(
    api_server: ServerFactory,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(TypeError, match="either one positional request"):
                await client.games.calendar(CalendarRequest(year=2024), year=2025)
            with pytest.raises(CFBDRequestValidationError) as exc_info:
                await client.games.calendar(year=1800)

    assert calls == 0
    assert exc_info.value.endpoint == "/calendar"


@pytest.mark.asyncio
async def test_response_validation_precedes_dataframe_conversion(
    api_server: ServerFactory,
) -> None:
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([{"season": 2024}])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError) as exc_info:
                await client.games.calendar(year=2024)

    assert exc_info.value.endpoint == "/calendar"
    assert "season" not in str(exc_info.value)
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_advanced_box_score_is_a_model_for_both_backends(
    api_server: ServerFactory,
    advanced_box_response: dict[str, object],
    backend: str,
) -> None:
    observed_query: dict[str, str] = {}

    async def handler(request: web.Request) -> web.Response:
        observed_query.update(request.query)
        return web.json_response(advanced_box_response)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            result = await client.games.advanced_box_score(game_id=401628347)

    assert isinstance(result, AdvancedBoxScore)
    assert observed_query == {"id": "401628347"}
