"""Focused tests for pure immutable recipe graph compilation."""

from __future__ import annotations

import pytest
from cfb_data.analytics import (
    CFBDRecipeCompilationError,
    RecipeRef,
    SourceContext,
    dataset,
    require_one,
    source,
    value,
    workflow,
)
from cfb_data.analytics._compiler import _compile_recipe
from cfb_data.tests.test_analytics_authoring import (
    _DatasetRow,
    _game_analysis,
    _game_summaries,
)
from pydantic import BaseModel


class _GameContext(BaseModel):
    """Represent selectors resolved from one game ID."""

    game_id: int
    season: int
    week: int


class _PlayRow(BaseModel):
    """Represent one test play."""

    play_id: str
    season: int
    week: int


@source(id="tests.game_context", revision=1, output=_GameContext, cost=1)
async def _game_context(
    context: SourceContext[_GameContext], *, game_id: int
) -> list[_GameContext]:
    """Retrieve context for one game."""
    return await context.retrieve(game_id=game_id)


@source(id="tests.plays", revision=1, output=_PlayRow, cost=1)
async def _plays(
    context: SourceContext[_PlayRow], *, year: int, week: int
) -> list[_PlayRow]:
    """Retrieve the containing play partition."""
    return await context.retrieve(year=year, week=week)


@dataset(
    id="tests.single_game_plays",
    revision=1,
    row=_PlayRow,
    grain="one play",
    keys=("play_id",),
    order_by=("play_id",),
)
def _single_game_plays(game_id: int) -> RecipeRef[list[_PlayRow]]:
    """Build a fixed graph with selectors resolved from game context."""
    selected_game = require_one(_game_context(game_id=game_id))
    return _plays.bind(
        year=value(selected_game, path=("season",), expected_type=int),
        week=value(selected_game, path=("week",), expected_type=int),
    )


def test_compilation_is_deterministic_and_topological() -> None:
    """Compile nested boundaries in dependency order with stable fingerprints."""
    first = _compile_recipe(_game_analysis, (), {"year": 2024})
    second = _compile_recipe(_game_analysis, (), {"year": 2024})

    assert first == second
    assert [node.kind for node in first.nodes] == [
        "source",
        "step",
        "dataset",
        "workflow",
    ]
    positions = {node.node_id: index for index, node in enumerate(first.nodes)}
    assert all(
        positions[dependency] < positions[node.node_id]
        for node in first.nodes
        for dependency in node.dependencies
    )
    assert tuple(first.outputs) == ("games",)


def test_omitted_and_explicit_null_parameters_have_distinct_identity() -> None:
    """Preserve caller intent in parameter and graph fingerprints."""
    omitted = _compile_recipe(_game_summaries, (), {"year": 2024})
    explicit = _compile_recipe(_game_summaries, (), {"year": 2024, "team": None})

    assert omitted.parameter_fingerprint != explicit.parameter_fingerprint
    assert omitted.graph_fingerprint != explicit.graph_fingerprint


def test_repeated_children_use_explicit_stable_aliases() -> None:
    """Allow repeated child recipes only through explicit invocation identity."""

    @workflow(id="tests.matchup", revision=1)
    def matchup(year: int) -> dict[str, RecipeRef[list[_DatasetRow]]]:
        return {
            "home": _game_summaries.as_("home")(year=year, team="Penn State"),
            "away": _game_summaries.as_("away")(year=year, team="Ohio State"),
        }

    graph = _compile_recipe(matchup, (), {"year": 2024})

    assert any("/home/" in f"{node.node_id}/" for node in graph.nodes)
    assert any("/away/" in f"{node.node_id}/" for node in graph.nodes)


def test_different_unaliased_repeated_children_fail_compilation() -> None:
    """Reject order-dependent repeated-child identity before operational I/O."""

    @workflow(id="tests.invalid_matchup", revision=1)
    def invalid_matchup(year: int) -> dict[str, RecipeRef[list[_DatasetRow]]]:
        return {
            "home": _game_summaries(year=year, team="Penn State"),
            "away": _game_summaries(year=year, team="Ohio State"),
        }

    with pytest.raises(CFBDRecipeCompilationError, match="require as_"):
        _compile_recipe(invalid_matchup, (), {"year": 2024})


def test_recursive_recipe_composition_fails_before_execution() -> None:
    """Reject recursively expanded recipe builders during pure compilation."""

    @dataset(
        id="tests.recursive",
        revision=1,
        row=_DatasetRow,
        grain="one game",
        keys=("game_id",),
    )
    def recursive(year: int) -> RecipeRef[list[_DatasetRow]]:
        return recursive(year=year)

    with pytest.raises(CFBDRecipeCompilationError, match="Recursive"):
        _compile_recipe(recursive, (), {"year": 2024})


def test_compiler_enforces_the_expanded_node_limit() -> None:
    """Bound graph expansion before source or transform work can start."""
    with pytest.raises(CFBDRecipeCompilationError, match="node limit"):
        _compile_recipe(_game_analysis, (), {"year": 2024}, max_nodes=2)


def test_late_bound_source_parameters_keep_a_fixed_graph() -> None:
    """Bind upstream scalars without source-dependent node expansion."""
    graph = _compile_recipe(_single_game_plays, (), {"game_id": 401628515})

    assert [node.kind for node in graph.nodes] == [
        "source",
        "step",
        "source",
        "dataset",
    ]
    plays = graph.nodes[2]
    assert plays.dependencies == (graph.nodes[1].node_id,)
    assert {argument.kind for argument in plays.arguments.values()} == {"value"}


def test_late_bound_scalar_types_are_checked_during_compilation() -> None:
    """Reject incompatible selector bindings before source execution."""

    @dataset(
        id="tests.invalid_bound_source",
        revision=1,
        row=_PlayRow,
        grain="one play",
        keys=("play_id",),
    )
    def invalid_bound_source(game_id: int) -> RecipeRef[list[_PlayRow]]:
        selected_game = require_one(_game_context(game_id=game_id))
        return _plays.bind(
            year=value(selected_game, path=("season",), expected_type=str),
            week=value(selected_game, path=("week",), expected_type=int),
        )

    with pytest.raises(CFBDRecipeCompilationError, match="scalar type"):
        _compile_recipe(invalid_bound_source, (), {"game_id": 401628515})
