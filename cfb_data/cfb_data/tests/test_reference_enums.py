"""Test the public live-source team and conference enums."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd
import polars as pl
import pytest
from aiohttp import web
from cfb_data.enums import REFERENCE_SEASON, conferences, teams

from cfb_data import CFBDClient, ConferenceName, GamesRequest, TeamName

ServerFactory = Callable[[Callable[..., object]], AbstractAsyncContextManager[str]]


def test_reference_enum_names_are_exact_upstream_strings() -> None:
    """Expose intuitive members while preserving punctuation and Unicode values."""
    assert REFERENCE_SEASON == 2026
    assert teams is TeamName
    assert conferences is ConferenceName
    assert teams.Michigan == "Michigan"
    assert teams.Hawaii == "Hawai'i"
    assert teams.SanJoseState == "San José State"
    assert teams.TexasAM == "Texas A&M"
    assert conferences.BIGTEN == "Big Ten"
    assert conferences.PRESIDENTS == "Presidents'"


def test_reference_enum_members_are_valid_string_request_values() -> None:
    """Serialize enum members exactly like equivalent literal string filters."""
    request = GamesRequest(
        year=2026,
        team=teams.Michigan,
        conference=conferences.BIGTEN,
    )

    assert request.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "year": 2026,
        "team": "Michigan",
        "conference": "Big Ten",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pandas", "polars"])
async def test_reference_enum_members_filter_and_match_result_strings(
    api_server: ServerFactory,
    game_response: dict[str, object],
    backend: str,
) -> None:
    """Use the same enum member in a request and a returned-frame comparison."""
    game_response["homeTeam"] = "Michigan"
    game_response["homeConference"] = "Big Ten"
    observed_query: dict[str, str] = {}

    async def handler(request: web.Request) -> web.Response:
        observed_query.update(request.query)
        return web.json_response([game_response])

    async with api_server(handler) as base_url:
        async with CFBDClient(
            "key", dataframe_backend=backend, base_url=base_url
        ) as client:
            frame = await client.games.list(
                year=2026,
                team=teams.Michigan,
                conference=conferences.BIGTEN,
            )

    assert observed_query == {
        "year": "2026",
        "team": "Michigan",
        "conference": "Big Ten",
    }
    if backend == "pandas":
        assert isinstance(frame, pd.DataFrame)
        assert frame["home_team"].eq(teams.Michigan).tolist() == [True]
        assert frame["home_conference"].eq(conferences.BIGTEN).tolist() == [True]
    else:
        assert isinstance(frame, pl.DataFrame)
        assert (frame["home_team"] == teams.Michigan).to_list() == [True]
        assert (frame["home_conference"] == conferences.BIGTEN).to_list() == [True]
