"""Test Adjusted Metrics and Info through the installed public client."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.adjusted_metrics import (
    AdjustedTeamMetrics,
    KickerPAAR,
    PlayerWeightedEPA,
)
from pydantic import ValidationError

from cfb_data import CFBDClient, InfoUsageRequest, UserInfo, UserUsage

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def _adjusted_team() -> dict[str, object]:
    return {
        "year": 2024,
        "teamId": 130,
        "team": "Michigan",
        "conference": "Big Ten",
        "epa": {"total": 0.12, "passing": 0.18, "rushing": 0.07},
        "epaAllowed": {"total": -0.04, "passing": -0.02, "rushing": -0.06},
        "successRate": {
            "total": 0.45,
            "standardDowns": 0.49,
            "passingDowns": 0.37,
        },
        "successRateAllowed": {
            "total": 0.38,
            "standardDowns": 0.40,
            "passingDowns": 0.33,
        },
        "rushing": {
            "lineYards": 3.1,
            "secondLevelYards": 1.2,
            "openFieldYards": 0.7,
            "highlightYards": 1.9,
        },
        "rushingAllowed": {
            "lineYards": 2.3,
            "secondLevelYards": 0.8,
            "openFieldYards": 0.3,
            "highlightYards": 1.1,
        },
        "explosiveness": 1.28,
        "explosivenessAllowed": 0.91,
    }


def _player_wepa() -> dict[str, object]:
    return {
        "year": 2024,
        "athleteId": "44212186",
        "athleteName": "Example Player",
        "position": "QB",
        "team": "Michigan",
        "conference": "Big Ten",
        "wepa": 21.4,
        "plays": 230,
    }


def _payloads() -> dict[str, object]:
    return {
        "/wepa/team/season": [_adjusted_team()],
        "/wepa/players/passing": [_player_wepa()],
        "/wepa/players/rushing": [_player_wepa()],
        "/wepa/players/kicking": [
            {
                "year": 2024,
                "athleteId": "44300000",
                "athleteName": "Example Kicker",
                "team": "Michigan",
                "conference": "Big Ten",
                "paar": 4.2,
                "attempts": 24,
            }
        ],
        "/info": {
            "patronLevel": 1,
            "tierName": "Tier 1",
            "monthlyLimit": 1000,
            "remainingCalls": 900,
            "usedCalls": 100,
            "resetAt": "2026-09-01T00:00:00-04:00",
            "sharedPool": True,
            "products": ["cfb", "cbb"],
            "features": {
                "adjustedMetrics": True,
                "weather": False,
                "scoreboard": False,
                "livePlayByPlay": False,
                "graphQl": False,
            },
        },
        "/info/usage": {
            "window": {
                "start": "2026-08-12T00:00:00-04:00",
                "end": "2026-08-13T12:00:00-04:00",
            },
            "api": "cfb",
            "totals": {
                "requests": 10,
                "cfbRequests": 10,
                "cbbRequests": 0,
                "uniqueEndpoints": 4,
            },
            "topEndpoints": [
                {
                    "api": "cfb",
                    "endpoint": "/games",
                    "requests": 4,
                    "lastUsedAt": "2026-08-13T11:55:00-04:00",
                }
            ],
            "recentRequests": [
                {
                    "api": "cfb",
                    "endpoint": "/info",
                    "requestedAt": "2026-08-13T12:00:00-04:00",
                }
            ],
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_all_adjusted_metrics_and_info_routes_preserve_contracts(
    api_server: ServerFactory, backend: str
) -> None:
    payloads = _payloads()
    observed: dict[str, dict[str, str]] = {}

    async def handler(request: web.Request) -> web.Response:
        observed[request.path] = dict(request.query)
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            team = await client.adjusted_metrics.team_season(year=2024, team="Michigan")
            passing = await client.adjusted_metrics.player_passing(
                year=2024, team="Michigan", position="QB"
            )
            rushing = await client.adjusted_metrics.player_rushing(
                year=2024, team="Michigan", position="QB"
            )
            kicking = await client.adjusted_metrics.kicker_paar(
                year=2024, team="Michigan"
            )
            account = await client.info.account()
            usage = await client.info.usage(days=1, limit=1, api="cfb")

    expected_type = pd.DataFrame if backend == "pandas" else pl.DataFrame
    for frame, model in (
        (team, AdjustedTeamMetrics),
        (passing, PlayerWeightedEPA),
        (rushing, PlayerWeightedEPA),
        (kicking, KickerPAAR),
    ):
        assert isinstance(frame, expected_type)
        assert list(frame.columns) == list(model.model_fields)
        assert len(frame) == 1

    if backend == "pandas":
        assert team.loc[0, "success_rate"]["standard_downs"] == 0.49
    else:
        assert team["success_rate"].struct.field("standard_downs")[0] == 0.49

    assert isinstance(account, UserInfo)
    assert isinstance(usage, UserUsage)
    assert account.reset_at.tzinfo is UTC
    assert usage.window.start.tzinfo is UTC
    assert usage.top_endpoints[0].last_used_at.tzinfo is UTC
    assert observed["/wepa/players/passing"] == {
        "year": "2024",
        "team": "Michigan",
        "position": "QB",
    }
    assert observed["/info"] == {}
    assert observed["/info/usage"] == {"days": "1", "limit": "1", "api": "cfb"}


def test_adjusted_metrics_and_info_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        InfoUsageRequest(days=32)

    payload = _adjusted_team()
    payload["successRate"] = {
        "total": 0.45,
        "standardDowns": 1.1,
        "passingDowns": 0.37,
    }
    with pytest.raises(ValidationError):
        AdjustedTeamMetrics.model_validate(payload)


def test_info_rejects_naive_operational_timestamp() -> None:
    payload = _payloads()["/info"]
    assert isinstance(payload, dict)
    payload["resetAt"] = "2026-09-01T00:00:00"

    with pytest.raises(ValidationError, match="timezone-aware"):
        UserInfo.model_validate(payload)
