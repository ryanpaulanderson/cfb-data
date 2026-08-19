"""Run one notebook-friendly durable dataset and inspect its evidence."""

import asyncio
from pathlib import Path

from cfb_data import AnalyticsConfig, CFBDClient, ExecutionPolicy


async def main() -> None:
    """Build, inspect, and export one team-season analytical table."""
    analytics = AnalyticsConfig(path=Path(".cfb-data-analytics"))
    async with CFBDClient(analytics=analytics) as client:
        plan = await client.datasets.plan(
            "cfbd.team_seasons",
            params={"season": 2024, "team": "Penn State"},
        )
        print("worst-case HTTP attempts:", plan.worst_case_http_attempts)
        run = await client.datasets.run(
            "cfbd.team_seasons",
            params={"season": 2024, "team": "Penn State"},
            policy=ExecutionPolicy(max_http_attempts=40),
        )

    print(run.frame.head())
    run.artifact.export_parquet("team-seasons.parquet")


if __name__ == "__main__":
    asyncio.run(main())
