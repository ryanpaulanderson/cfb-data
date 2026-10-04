"""Calculate raw-play Success Rate and opponent-adjusted College ALY with Redis.

Run with ``CFBD_API_KEY`` set and Redis listening on localhost. Explicit weeks
bound retrieval; automatic ALY selection requires at least two weeks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from cfb_data.analytics import AnalyticsConfig, ExecutionPolicy
from cfb_data.enums import Classification
from cfb_data_recipes.line_yards import line_yards
from cfb_data_recipes.success_rate import success_rate

from cfb_data import CFBDClient, RedisCacheConfig


async def main() -> None:
    """Calculate the opening two FBS weeks and export each named product."""
    output = Path("outputs/calculated-metrics")
    output.mkdir(parents=True, exist_ok=True)
    policy = ExecutionPolicy(max_http_attempts=12)
    async with CFBDClient(
        cache=RedisCacheConfig(url="redis://127.0.0.1:6379/0"),
        analytics=AnalyticsConfig(root=Path(".analytics/calculated-metrics")),
    ) as client:
        success = await success_rate.run(
            client,
            year=2024,
            weeks=(1, 2),
            classification=Classification.fbs,
            policy=policy,
        )
        adjusted = await line_yards.run(
            client,
            year=2024,
            weeks=(1, 2),
            classification=Classification.fbs,
            policy=policy,
        )
    for prefix, run in (("success", success), ("line-yards", adjusted)):
        for name, artifact in run.artifacts.items():
            artifact.export_parquet(output / f"{prefix}-{name}.parquet")
        print(prefix, run.actual_http_attempts, run.reused_nodes)


if __name__ == "__main__":
    asyncio.run(main())
