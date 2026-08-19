"""Register a trusted portable dataset from ordinary Python or a notebook."""

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from cfb_data.base.types import JSONValue
from cfb_data.games.models.pydantic.responses import Game
from pydantic import BaseModel, ConfigDict, Field

from cfb_data import (
    AnalyticsConfig,
    CFBDClient,
    DatasetCatalog,
    DatasetDefinition,
    ParameterBinding,
    RegisteredTransform,
    TableContract,
    TransformBackend,
    TransformNode,
    TransformRegistry,
    registered_source,
)


class CompletedGamesParams(BaseModel):
    """Validate selectors for the completed-games analytical table."""

    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=1869)
    team: str | None = None


COMPLETED_GAMES = TableContract(
    id="example.completed_games.table",
    revision=1,
    row_model=Game,
    grain="one completed selected game",
    keys=("id",),
    order_by=("season", "week", "start_date", "id"),
    partition_by=("season",),
    event_time="start_date",
)


def keep_completed_games(
    inputs: Mapping[str, Sequence[BaseModel]],
    parameters: BaseModel,
    config: Mapping[str, JSONValue],
) -> Sequence[BaseModel]:
    """Keep completed validated games without changing their source fields."""
    del parameters, config
    return [row for row in inputs["games"] if isinstance(row, Game) and row.completed]


DEFINITION = DatasetDefinition(
    id="example.completed_games",
    revision=1,
    parameter_model=CompletedGamesParams,
    nodes=(
        registered_source(
            "games",
            "cfbd.games.list",
            bindings={
                "year": ParameterBinding("year"),
                "team": ParameterBinding("team"),
            },
        ),
        TransformNode(
            id="result",
            operation_id="example.transform.keep_completed",
            operation_revision=1,
            inputs=("games",),
            output=COMPLETED_GAMES,
        ),
    ),
    output_node="result",
    output=COMPLETED_GAMES,
    description="Selected games whose validated source status is completed.",
)

ANALYTICS = AnalyticsConfig(
    path=Path(".cfb-data-analytics"),
    catalog=DatasetCatalog({DEFINITION.id: DEFINITION}),
    transforms=TransformRegistry(
        {
            "example.transform.keep_completed": RegisteredTransform(
                id="example.transform.keep_completed",
                revision=1,
                backend=TransformBackend.portable,
                deterministic=True,
                callable=keep_completed_games,
            )
        }
    ),
)


async def main() -> None:
    """Run the custom definition through the same durable engine as built-ins."""
    async with CFBDClient(analytics=ANALYTICS) as client:
        run = await client.datasets.run(
            DEFINITION.id,
            params={"year": 2024, "team": "Penn State"},
        )
    print(run.frame.head())
    print("run:", run.run_id, "artifact:", run.artifact.descriptor.artifact_id)


if __name__ == "__main__":
    asyncio.run(main())
