"""Validate the independent first-party team-seasons recipe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from aiohttp import web
from cfb_data.analytics import AnalyticsConfig, CFBDRunError, ExecutionPolicy, RecipeRun
from cfb_data.enums import SeasonType
from cfb_data_recipes.team_seasons import (
    TeamSeason,
    TeamSeasonCoverage,
    team_seasons,
)

from cfb_data import CFBDClient, DataFrameBackend, RetryPolicy

type ServerFactory = Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    AbstractAsyncContextManager[str],
]


def _record() -> dict[str, object]:
    """Return one complete records-defined team season."""
    return {
        "year": 2024,
        "teamId": 130,
        "team": "Michigan",
        "classification": "fbs",
        "conference": "Big Ten",
        "division": "",
        "expectedWins": 10.2,
        "total": {"games": 15, "wins": 12, "losses": 3, "ties": 0},
        "conferenceGames": {"games": 10, "wins": 8, "losses": 2, "ties": 0},
        "homeGames": {"games": 8, "wins": 8, "losses": 0, "ties": 0},
        "awayGames": {"games": 6, "wins": 3, "losses": 3, "ties": 0},
        "neutralSiteGames": {"games": 1, "wins": 1, "losses": 0, "ties": 0},
        "regularSeason": {"games": 12, "wins": 10, "losses": 2, "ties": 0},
        "postseason": {"games": 3, "wins": 2, "losses": 1, "ties": 0},
    }


def _season_unit(*, defense: bool) -> dict[str, object]:
    """Return one complete advanced-season unit."""
    passing_downs: dict[str, object] = {
        "rate": 0.3,
        "ppa": 0.2,
        "successRate": 0.35,
        "explosiveness": None,
    }
    if defense:
        passing_downs["totalPPA"] = 12.5
    return {
        "plays": 700,
        "drives": 120,
        "ppa": 0.15,
        "totalPPA": 105.0,
        "successRate": 0.42,
        "explosiveness": 1.1,
        "powerSuccess": None,
        "stuffRate": 0.15,
        "lineYards": 3.0,
        "lineYardsTotal": 1200,
        "secondLevelYards": 0.8,
        "secondLevelYardsTotal": 320,
        "openFieldYards": 0.7,
        "openFieldYardsTotal": 280,
        "totalOpportunies": 55,
        "pointsPerOpportunity": 4.1,
        "fieldPosition": {"averageStart": 70.0, "averagePredictedPoints": 1.2},
        "havoc": {"total": 0.18, "frontSeven": 0.1, "db": 0.08},
        "standardDowns": {
            "rate": 0.7,
            "ppa": 0.1,
            "successRate": 0.46,
            "explosiveness": 0.9,
        },
        "passingDowns": passing_downs,
        "rushingPlays": {
            "rate": 0.55,
            "ppa": 0.12,
            "totalPPA": 46.0,
            "successRate": 0.43,
            "explosiveness": 0.8,
        },
        "passingPlays": {
            "rate": 0.45,
            "ppa": 0.18,
            "totalPPA": 59.0,
            "successRate": 0.41,
            "explosiveness": 1.4,
        },
    }


def _advanced() -> dict[str, object]:
    """Return one complete advanced team season."""
    return {
        "season": 2024,
        "team": "Michigan",
        "conference": "Big Ten",
        "offense": _season_unit(defense=False),
        "defense": _season_unit(defense=True),
    }


def _statistics() -> list[dict[str, object]]:
    """Return ordered heterogeneous conventional statistics."""
    return [
        {
            "season": 2024,
            "team": "Michigan",
            "conference": "Big Ten",
            "statName": "firstDowns",
            "statValue": 210,
        },
        {
            "season": 2024,
            "team": "Michigan",
            "conference": "Big Ten",
            "statName": "timeOfPossession",
            "statValue": "22041",
        },
    ]


def _ppa() -> dict[str, object]:
    """Return one complete team-season PPA enrichment row."""
    unit = {
        "overall": 0.2,
        "passing": 0.3,
        "rushing": 0.1,
        "firstDown": 0.2,
        "secondDown": 0.1,
        "thirdDown": 0.3,
        "cumulative": {"total": 100.0, "passing": 60.0, "rushing": 40.0},
    }
    return {
        "season": 2024,
        "conference": "Big Ten",
        "team": "Michigan",
        "offense": unit,
        "defense": unit,
    }


def _talent() -> dict[str, object]:
    """Return one source-shaped team-talent enrichment row."""
    return {"year": 2024, "team": "Michigan", "talent": 982.31}


def _ats() -> dict[str, object]:
    """Return one source-shaped against-the-spread enrichment row."""
    return {
        "year": 2024,
        "teamId": 130,
        "team": "Michigan",
        "conference": "Big Ten",
        "games": 15,
        "atsWins": 9,
        "atsLosses": 5,
        "atsPushes": 1,
        "avgCoverMargin": 3.2,
    }


def _returning_production() -> dict[str, object]:
    """Return one source-shaped returning-production enrichment row."""
    return {
        "season": 2024,
        "team": "Michigan",
        "conference": "Big Ten",
        "totalPPA": 120.5,
        "totalPassingPPA": 65.0,
        "totalReceivingPPA": 31.0,
        "totalRushingPPA": 24.5,
        "percentPPA": 0.62,
        "percentPassingPPA": 0.58,
        "percentReceivingPPA": 0.64,
        "percentRushingPPA": 0.69,
        "usage": 0.61,
        "passingUsage": 0.57,
        "receivingUsage": 0.63,
        "rushingUsage": 0.68,
    }


def _rating_payloads() -> dict[str, object]:
    """Return one valid source row for every attached team rating."""
    offense = {
        "ranking": 10,
        "rating": 30.0,
        "success": None,
        "explosiveness": None,
        "rushing": None,
        "passing": None,
        "standardDowns": None,
        "passingDowns": None,
        "runRate": None,
        "pace": None,
    }
    defense = {
        "ranking": 12,
        "rating": 20.0,
        "success": None,
        "explosiveness": None,
        "rushing": None,
        "passing": None,
        "standardDowns": None,
        "passingDowns": None,
        "havoc": {"total": None, "frontSeven": None, "db": None},
    }
    return {
        "/ratings/core": [
            {
                "year": 2024,
                "throughSeasonType": "postseason",
                "throughWeek": 16,
                "team": "Michigan",
                "conference": "Big Ten",
                "overall": 4.2,
                "offense": 2.1,
                "defense": -2.1,
                "offensePlays": 700,
                "defensePlays": 680,
                "modelVersion": "1.0",
            }
        ],
        "/ratings/sp": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "rating": 20.0,
                "ranking": 10,
                "secondOrderWins": None,
                "sos": None,
                "offense": offense,
                "defense": defense,
                "specialTeams": {"rating": 1.0},
            }
        ],
        "/ratings/srs": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "division": None,
                "rating": 10.0,
                "ranking": 12,
            }
        ],
        "/ratings/elo": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "elo": 1600,
            }
        ],
        "/ratings/fpi": [
            {
                "year": 2024,
                "team": "Michigan",
                "conference": "Big Ten",
                "fpi": 12.5,
                "resumeRanks": {
                    "strengthOfRecord": 10,
                    "fpi": 12,
                    "averageWinProbability": 9,
                    "strengthOfSchedule": 20,
                    "remainingStrengthOfSchedule": None,
                    "gameControl": 11,
                },
                "efficiencies": {
                    "overall": 80.0,
                    "offense": 75.0,
                    "defense": 85.0,
                    "specialTeams": 70.0,
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_recipe_uses_records_universe_and_preserves_ordered_statistics(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Attach heterogeneous statistics without pivoting or changing grain."""

    async def handler(request: web.Request) -> web.Response:
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": _statistics(),
            "/stats/season/advanced": [_advanced()],
        }
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await team_seasons(
                client,
                season=2024,
                team="Michigan",
            )

    assert tuple(frame.columns) == tuple(TeamSeason.model_fields)
    assert len(frame) == 1
    assert frame.loc[0, "team_id"] == 130
    assert [item["name"] for item in frame.loc[0, "statistics"]] == [
        "firstDowns",
        "timeOfPossession",
    ]
    assert [item["value"] for item in frame.loc[0, "statistics"]] == [210, "22041"]
    assert frame.loc[0, "advanced"]["defense"]["passing_downs"]["total_ppa"] == 12.5
    assert frame.loc[0, "ppa_coverage"] == TeamSeasonCoverage.not_requested
    assert frame.loc[0, "ppa"] is None
    assert frame.loc[0, "talent_coverage"] == TeamSeasonCoverage.not_requested
    assert frame.loc[0, "talent"] is None
    assert frame.loc[0, "ats_coverage"] == TeamSeasonCoverage.not_requested
    assert frame.loc[0, "ats"] is None
    assert (
        frame.loc[0, "returning_production_coverage"]
        == TeamSeasonCoverage.not_requested
    )
    assert frame.loc[0, "returning_production"] is None
    for field in ("core", "sp", "srs", "elo", "fpi"):
        assert (
            frame.loc[0, f"{field}_rating_coverage"] == TeamSeasonCoverage.not_requested
        )
        assert frame.loc[0, f"{field}_rating"] is None


@pytest.mark.asyncio
async def test_recipe_has_four_way_canonical_parity(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Produce one logical team-season table across frames and executors."""
    pytest.importorskip("polars")
    pytest.importorskip("distributed")
    calls: dict[str, int] = {
        "/records": 0,
        "/stats/season": 0,
        "/stats/season/advanced": 0,
        "/ppa/teams": 0,
        "/talent": 0,
        "/teams/ats": 0,
        "/player/returning": 0,
        **{path: 0 for path in _rating_payloads()},
    }

    async def handler(request: web.Request) -> web.Response:
        calls[request.path] += 1
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": _statistics(),
            "/stats/season/advanced": [_advanced()],
            "/ppa/teams": [_ppa()],
            "/talent": [_talent()],
            "/teams/ats": [_ats()],
            "/player/returning": [_returning_production()],
            **_rating_payloads(),
        }
        return web.json_response(payloads[request.path])

    combinations: tuple[tuple[DataFrameBackend, Literal["local", "dask"]], ...] = (
        ("pandas", "local"),
        ("polars", "local"),
        ("pandas", "dask"),
        ("polars", "dask"),
    )
    digests: list[str] = []
    records: list[list[dict[str, object]]] = []
    async with api_server(handler) as base_url:
        for backend, executor in combinations:
            async with CFBDClient(
                "team-seasons-key",
                base_url=base_url,
                dataframe_backend=backend,
                retry_policy=RetryPolicy(max_attempts=1),
                analytics=AnalyticsConfig(root=tmp_path / f"{backend}-{executor}"),
            ) as client:
                run: RecipeRun[pd.DataFrame] = await team_seasons.run(
                    client,
                    season=2024,
                    include_ppa=True,
                    include_talent=True,
                    include_ats=True,
                    include_returning_production=True,
                    include_core_rating=True,
                    include_sp_rating=True,
                    include_srs_rating=True,
                    include_elo_rating=True,
                    elo_week=16,
                    elo_season_type=SeasonType.postseason,
                    include_fpi_rating=True,
                    policy=ExecutionPolicy(executor=executor, dask_max_workers=1),
                )
            digests.append(run.artifact.descriptor.content_digest)
            restored = run.artifact.load()
            records.append(restored.to_dict(orient="records"))
            assert restored.loc[0, "ppa_coverage"] == TeamSeasonCoverage.present
            assert restored.loc[0, "ppa"]["offense"]["overall"] == 0.2
            assert restored.loc[0, "talent_coverage"] == TeamSeasonCoverage.present
            assert restored.loc[0, "talent"]["talent"] == 982.31
            assert restored.loc[0, "ats_coverage"] == TeamSeasonCoverage.present
            assert restored.loc[0, "ats"]["ats_wins"] == 9
            assert (
                restored.loc[0, "returning_production_coverage"]
                == TeamSeasonCoverage.present
            )
            assert restored.loc[0, "returning_production"]["percent_ppa"] == 0.62
            assert restored.loc[0, "core_rating"]["overall"] == 4.2
            assert restored.loc[0, "sp_rating"]["rating"] == 20.0
            assert restored.loc[0, "srs_rating"]["rating"] == 10.0
            assert restored.loc[0, "elo_rating"]["elo"] == 1600
            assert restored.loc[0, "fpi_rating"]["fpi"] == 12.5

    assert calls == {
        "/records": 4,
        "/stats/season": 4,
        "/stats/season/advanced": 4,
        "/ppa/teams": 4,
        "/talent": 4,
        "/teams/ats": 4,
        "/player/returning": 4,
        **{path: 4 for path in _rating_payloads()},
    }
    assert len(set(digests)) == 1
    assert all(result == records[0] for result in records[1:])


@pytest.mark.asyncio
async def test_required_statistical_coverage_fails_closed(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Fail rather than publish a records row missing required statistics."""

    async def handler(request: web.Request) -> web.Response:
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": [],
            "/stats/season/advanced": [_advanced()],
        }
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            with pytest.raises(CFBDRunError) as exc_info:
                await team_seasons(client, season=2024)

    assert exc_info.value.node_id.endswith("cfbd.team_seasons.compose@4")
    assert exc_info.value.category == "ValueError"


@pytest.mark.asyncio
async def test_requested_empty_ppa_is_explicit_without_changing_universe(
    api_server: ServerFactory,
    tmp_path: Path,
) -> None:
    """Preserve a records row when optional PPA is valid-empty."""

    async def handler(request: web.Request) -> web.Response:
        payloads: dict[str, object] = {
            "/records": [_record()],
            "/stats/season": _statistics(),
            "/stats/season/advanced": [_advanced()],
            "/ppa/teams": [],
            "/talent": [],
            "/teams/ats": [],
            "/player/returning": [],
            **{path: [] for path in _rating_payloads()},
        }
        return web.json_response(payloads[request.path])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "team-seasons-key",
            base_url=base_url,
            retry_policy=RetryPolicy(max_attempts=1),
            analytics=AnalyticsConfig(root=tmp_path / "analytics"),
        ) as client:
            frame: pd.DataFrame = await team_seasons(
                client,
                season=2024,
                team="Michigan",
                include_ppa=True,
                include_talent=True,
                include_ats=True,
                include_returning_production=True,
                include_core_rating=True,
                include_sp_rating=True,
                include_srs_rating=True,
                include_elo_rating=True,
                include_fpi_rating=True,
            )

    assert len(frame) == 1
    assert frame.loc[0, "ppa_coverage"] == TeamSeasonCoverage.empty
    assert frame.loc[0, "ppa"] is None
    assert frame.loc[0, "talent_coverage"] == TeamSeasonCoverage.empty
    assert frame.loc[0, "talent"] is None
    assert frame.loc[0, "ats_coverage"] == TeamSeasonCoverage.empty
    assert frame.loc[0, "ats"] is None
    assert frame.loc[0, "returning_production_coverage"] == TeamSeasonCoverage.empty
    assert frame.loc[0, "returning_production"] is None
    for field in ("core", "sp", "srs", "elo", "fpi"):
        assert frame.loc[0, f"{field}_rating_coverage"] == TeamSeasonCoverage.empty
        assert frame.loc[0, f"{field}_rating"] is None
