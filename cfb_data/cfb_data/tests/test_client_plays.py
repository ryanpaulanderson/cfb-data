"""Test Plays endpoints through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.plays.models.pydantic.responses import (
    Play,
    PlayStat,
    PlayStatType,
    PlayType,
)

from cfb_data import (
    CFBDClient,
    CFBDRequestValidationError,
    CFBDResponseValidationError,
    LiveGame,
    PlaysRequest,
)

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_all_tabular_plays_endpoints_share_the_backend_contract(
    api_server: ServerFactory,
    play_response: dict[str, object],
    play_stat_response: dict[str, object],
    backend: str,
) -> None:
    """Validate routes, aliases, rows, columns, and nested values."""
    payloads = {
        "/plays": [play_response],
        "/plays/types": [{"id": 5, "text": "Rush", "abbreviation": "RUSH"}],
        "/plays/stats": [play_stat_response],
        "/plays/stats/types": [{"id": 1, "name": "Incompletion"}],
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
                (
                    await client.plays.list(
                        year=2024,
                        week=1,
                        offense_conference="Mountain West",
                        play_type="RUSH",
                        season_type="regular",
                    ),
                    Play,
                ),
                (await client.plays.types(), PlayType),
                (
                    await client.plays.stats(
                        game_id=401628452,
                        athlete_id=4794102,
                        stat_type_id=1,
                    ),
                    PlayStat,
                ),
                (await client.plays.stat_types(), PlayStatType),
            ]

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in frames:
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    plays_frame = frames[0][0]
    stats_frame = frames[2][0]
    if backend == "pandas":
        assert plays_frame.loc[0, "clock"] == {"minutes": 15, "seconds": 0}
        assert str(plays_frame.dtypes["wallclock"]) == "datetime64[ns, UTC]"
        assert stats_frame.loc[0, "clock"] == {"minutes": 13, "seconds": 31}
    else:
        assert isinstance(plays_frame.schema["clock"], pl.Struct)
        assert plays_frame.schema["wallclock"].time_zone == "UTC"
        assert isinstance(stats_frame.schema["clock"], pl.Struct)

    assert observed_queries == {
        "/plays": {
            "year": "2024",
            "week": "1",
            "offenseConference": "Mountain West",
            "playType": "RUSH",
            "seasonType": "regular",
        },
        "/plays/types": {},
        "/plays/stats": {
            "gameId": "401628452",
            "athleteId": "4794102",
            "statTypeId": "1",
        },
        "/plays/stats/types": {},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_plays_typed_empty_frame_uses_response_schema(
    api_server: ServerFactory,
    backend: str,
) -> None:
    """Return a typed empty play frame without losing its logical schema."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.plays.list(year=2024, week=1)

    assert list(frame.columns) == list(Play.model_fields)
    assert len(frame) == 0
    if backend == "pandas":
        assert str(frame.dtypes["game_id"]) == "int64"
        assert str(frame.dtypes["wallclock"]) == "datetime64[ns, UTC]"
    else:
        assert frame.schema["game_id"] == pl.Int64
        assert frame.schema["wallclock"].time_zone == "UTC"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_live_plays_returns_one_validated_model_for_both_backends(
    api_server: ServerFactory,
    live_game_response: dict[str, object],
    backend: str,
) -> None:
    """Keep the nested live response independent of DataFrame selection."""
    observed_query: dict[str, str] = {}

    async def handler(request: web.Request) -> web.Response:
        observed_query.update(request.query)
        return web.json_response(live_game_response)

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            result = await client.plays.live(game_id=401628347)

    assert isinstance(result, LiveGame)
    assert result.drives[0].plays[0].team == "Texas"
    assert observed_query == {"gameId": "401628347"}


@pytest.mark.asyncio
async def test_plays_request_validation_stops_before_http(
    api_server: ServerFactory,
) -> None:
    """Reject invalid filters and mixed request styles without a request."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.json_response([])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDRequestValidationError):
                await client.plays.list(year=2024)
            with pytest.raises(CFBDRequestValidationError):
                await client.plays.live(game_id=0)
            with pytest.raises(TypeError, match="either one positional request"):
                await client.plays.list(
                    PlaysRequest(year=2024, week=1),
                    year=2024,
                )

    assert calls == 0


@pytest.mark.asyncio
async def test_plays_response_validation_precedes_dataframe_conversion(
    api_server: ServerFactory,
) -> None:
    """Reject malformed upstream rows without exposing response details."""

    async def handler(request: web.Request) -> web.Response:
        return web.json_response([{"gameId": 401628452}])

    async with api_server(handler) as base_url:
        async with CFBDClient("key", base_url=base_url) as client:
            with pytest.raises(CFBDResponseValidationError) as exc_info:
                await client.plays.list(year=2024, week=1)

    assert exc_info.value.endpoint == "/plays"
    assert "gameId" not in str(exc_info.value)
