"""Exercise the reusable centered-model steps through their public dataset flow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from cfb_data.analytics import (
    AnalyticsConfig,
    CFBDRunError,
    ExecutionPolicy,
    RecipeRef,
    SourceContext,
    Table,
    dataset,
    source,
)
from cfb_data.analytics.modeling import (
    BlockPenalty,
    EffectObservation,
    ModelCoefficient,
    additive_statistics,
    fit_additive_model,
)

from cfb_data import CFBDClient


@source(id="tests.modeling.design", revision=1, output=EffectObservation, cost=0)
async def _design(
    context: SourceContext[EffectObservation], *, failure: str | None
) -> list[EffectObservation]:
    del context
    rows: list[EffectObservation] = []
    for index, (level, response) in enumerate((("A", 3.0), ("B", 5.0), ("A", 4.0))):
        for block, category in (("intercept", "constant"), ("team", level)):
            if failure == "missing_block" and index == 1 and block == "team":
                continue
            rows.append(
                EffectObservation(
                    observation_id=str(index),
                    cluster_id=str(index),
                    block=block,
                    level=category,
                    value=1.0,
                    response=response
                    + (1 if failure == "response_conflict" and block == "team" else 0),
                    weight=1.0,
                )
            )
    if failure == "duplicate":
        rows.append(rows[1])
    return rows


@dataset(
    id="tests.modeling.fit",
    revision=1,
    row=ModelCoefficient,
    grain="one centered coefficient",
    keys=("block", "level"),
    order_by=("block", "level"),
)
def _fit(*, failure: str | None = None, max_parameters: int = 8) -> RecipeRef[Table]:
    return fit_additive_model(
        additive_statistics(_design(failure=failure)),
        penalties=(BlockPenalty(block="team", penalty=4),),
        max_parameters=max_parameters,
    )


@pytest.mark.asyncio
async def test_centered_model_preserves_global_observation_contract(
    tmp_path: Path,
) -> None:
    async with CFBDClient("key", analytics=AnalyticsConfig(root=tmp_path)) as client:
        result = (
            await _fit.run(client, policy=ExecutionPolicy(table_partition_rows=1))
        ).value
    assert isinstance(result, pd.DataFrame)
    effects = result.set_index(["block", "level"])
    assert effects.loc[("intercept", "constant"), "estimate"] == pytest.approx(4)
    assert effects.loc[("team", "A"), "estimate"] == pytest.approx(-3 / 26)
    assert effects.loc[("team", "B"), "estimate"] == pytest.approx(3 / 13)
    assert result["observations"].tolist() == [3, 3, 3]
    assert result["clusters"].tolist() == [3, 3, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["response_conflict", "duplicate", "missing_block", "bound"]
)
async def test_model_rejects_global_conflicts_and_resource_overrun(
    tmp_path: Path, failure: str
) -> None:
    async with CFBDClient("key", analytics=AnalyticsConfig(root=tmp_path)) as client:
        with pytest.raises(CFBDRunError):
            await _fit.run(
                client,
                failure=None if failure == "bound" else failure,
                max_parameters=2 if failure == "bound" else 8,
                policy=ExecutionPolicy(table_partition_rows=1),
            )
