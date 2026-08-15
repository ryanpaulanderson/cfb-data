"""Exercise one bounded cache and identity flow against the real CFBD API."""

import os
from pathlib import Path

import pytest

from cfb_data import CFBDClient, FreshnessMode, SQLiteCacheConfig


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_live_api_populates_response_cache_and_identity_catalog(
    tmp_path: Path,
) -> None:
    """Spend one real request, then prove response and identity work locally."""
    if os.getenv("CFB_DATA_RUN_LIVE_API") != "1":
        pytest.skip("set CFB_DATA_RUN_LIVE_API=1 for the bounded real-API test")
    api_key = os.getenv("CFBD_API_KEY")
    if not api_key:
        pytest.skip("set CFBD_API_KEY for the bounded real-API test")

    async with CFBDClient(
        api_key,
        cache=SQLiteCacheConfig(path=tmp_path / "live-cache.sqlite3"),
    ) as client:
        first = await client.teams.list()
        assert not first.empty

        with client.cache_mode("local_only"):
            second = await client.teams.list()
        assert first.equals(second)

        school = str(first.iloc[0]["school"])
        team = await client.identities.teams.resolve(
            school, freshness=FreshnessMode.local_only
        )
        assert team.school == school
