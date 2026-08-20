"""Execute the finite YAML workflow through the ordinary recipe runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cfb_data.analytics import WorkflowRecipe, discover_recipes, load_recipe_yaml

from cfb_data import CFBDClient

_DEFINITION = Path(__file__).with_name("penn_state_games.yaml")


async def main() -> None:
    """Print one YAML-composed workflow output."""
    recipe = load_recipe_yaml(
        _DEFINITION.read_text(encoding="utf-8"),
        recipes=discover_recipes(),
    )
    if not isinstance(recipe, WorkflowRecipe):
        raise RuntimeError("Expected a workflow definition")
    async with CFBDClient() as client:
        outputs = await recipe(client, year=2024, team="Penn State")
    print(outputs["game_summaries"])


if __name__ == "__main__":
    asyncio.run(main())
