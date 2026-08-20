"""Black-box tests for the modular recipe authoring boundary."""

from __future__ import annotations

import inspect

import pytest
from cfb_data.analytics import (
    CFBDRecipeConfigurationError,
    CFBDRecipeParameterError,
    CFBDRecipeUsageError,
    DatasetRecipe,
    RecipeRef,
    SourceContext,
    SourceRecipe,
    StepRecipe,
    WorkflowRecipe,
    dataset,
    source,
    step,
    workflow,
)
from pydantic import BaseModel

from cfb_data import CFBDClient


class _SourceRow(BaseModel):
    """Represent a test source row."""

    game_id: int
    year: int


class _DatasetRow(BaseModel):
    """Represent a test dataset row."""

    game_id: int
    year: int


@source(id="tests.authoring_games", revision=1, output=_SourceRow, cost=1)
async def _games(context: SourceContext[_SourceRow], *, year: int) -> list[_SourceRow]:
    """Retrieve test games."""
    return await context.retrieve(year=year)


@step(id="tests.authoring_normalize", revision=1, output=_DatasetRow)
def _normalize(rows: list[_SourceRow]) -> list[_DatasetRow]:
    """Normalize test games."""
    return [_DatasetRow(game_id=row.game_id, year=row.year) for row in rows]


@dataset(
    id="tests.authoring_game_summaries",
    revision=1,
    row=_DatasetRow,
    grain="one game",
    keys=("game_id",),
    order_by=("year", "game_id"),
)
def _game_summaries(year: int, team: str | None = None) -> RecipeRef[list[_DatasetRow]]:
    """Build a test game-summary graph."""
    del team
    return _normalize(_games(year=year))


@workflow(id="tests.authoring_game_analysis", revision=1)
def _game_analysis(year: int) -> dict[str, RecipeRef[list[_DatasetRow]]]:
    """Build a test workflow graph."""
    return {"games": _game_summaries(year=year)}


@dataset(
    row=_DatasetRow,
    grain="one game",
    keys=("game_id",),
    order_by=("year", "game_id"),
)
def _threshold_games(threshold: float) -> RecipeRef[list[_DatasetRow]]:
    """Build a notebook-style dataset with one finite float parameter."""
    del threshold
    return _game_summaries(year=2024)


def test_decorators_create_typed_immutable_callable_recipes() -> None:
    """Expose each authored boundary as a stable immutable recipe object."""
    assert isinstance(_games, SourceRecipe)
    assert isinstance(_normalize, StepRecipe)
    assert isinstance(_game_summaries, DatasetRecipe)
    assert isinstance(_game_analysis, WorkflowRecipe)
    assert (_game_summaries.kind, _game_summaries.id, _game_summaries.revision) == (
        "dataset",
        "tests.authoring_game_summaries",
        1,
    )

    with pytest.raises(AttributeError, match="immutable"):
        _game_summaries.extra = object()


def test_dataset_signature_preserves_client_and_analytical_parameters() -> None:
    """Present an explicit client without polluting the builder signature."""
    parameters = tuple(inspect.signature(_game_summaries).parameters.values())

    assert [parameter.name for parameter in parameters] == ["client", "year", "team"]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_ONLY
    assert parameters[2].default is None


def test_sources_and_steps_are_build_only_top_level_values() -> None:
    """Reject direct source and transform calls outside graph construction."""
    with pytest.raises(CFBDRecipeUsageError, match="dataset or workflow"):
        _games(year=2024)
    with pytest.raises(CFBDRecipeUsageError, match="dataset or workflow"):
        _normalize([])


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -float("inf")])
async def test_non_finite_parameters_raise_typed_recipe_errors(
    threshold: float,
) -> None:
    """Reject non-finite analytical parameters through the public plan API."""
    async with CFBDClient("parameter-test-key") as client:
        with pytest.raises(CFBDRecipeParameterError, match="validation failed"):
            await _threshold_games.plan(client, threshold)


def test_datasets_require_an_explicit_client_at_top_level() -> None:
    """Reject a top-level analytical call that omits its client."""
    with pytest.raises(CFBDRecipeUsageError, match="CFBDClient"):
        _game_summaries(year=2024)


def test_aliases_preserve_recipe_kind_and_are_immutable() -> None:
    """Create stable repeated-child aliases without changing the source recipe."""
    aliased = _game_summaries.as_("home")

    assert isinstance(aliased, DatasetRecipe)
    assert aliased.id == _game_summaries.id
    assert aliased is not _game_summaries
    with pytest.raises(CFBDRecipeConfigurationError, match="aliases"):
        _game_summaries.as_("")


@pytest.mark.parametrize("reserved", ["client", "policy", "plan", "resume_from"])
def test_dataset_declarations_reject_framework_control_names(reserved: str) -> None:
    """Reserve execution controls rather than treating them as analytical data."""
    namespace: dict[str, object] = {}
    exec(
        f"def invalid({reserved}: int) -> object:\n    return object()",
        namespace,
    )

    with pytest.raises(CFBDRecipeConfigurationError, match="reserved"):
        dataset(
            id=f"tests.invalid_{reserved}",
            revision=1,
            row=_DatasetRow,
            grain="one game",
            keys=("game_id",),
        )(namespace["invalid"])


def test_dataset_metadata_must_reference_declared_row_fields() -> None:
    """Reject invalid keys before graph compilation or I/O."""
    with pytest.raises(CFBDRecipeConfigurationError, match="keys"):

        @dataset(
            id="tests.invalid_keys",
            revision=1,
            row=_DatasetRow,
            grain="one game",
            keys=("missing",),
        )
        def invalid(year: int) -> RecipeRef[list[_DatasetRow]]:
            """Build an invalid test recipe."""
            return _game_summaries(year=year)
