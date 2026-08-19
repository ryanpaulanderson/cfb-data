"""Expose curated multi-output analytical workflows."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._attempt_budget import _attempt_budget_scope
from cfb_data._observability import _failure_category
from cfb_data._tabular import _models_from_arrow_table
from cfb_data.analytics._catalog import (
    COACH_SEASONS,
    GAME_SUMMARIES,
    POLL_RANKINGS,
    RECRUITING_CLASSES,
    TEAM_GAMES,
    TEAM_SEASONS,
)
from cfb_data.analytics._engine import (
    DatasetRun,
    _AnalyticsEngine,
    _execution_resources_scope,
)
from cfb_data.analytics._models import (
    GameSummary,
    ProgramHistoryParams,
    SingleGameWorkflowParams,
    TeamSeasonWorkflowParams,
)
from cfb_data.analytics.artifacts import ArtifactRef
from cfb_data.analytics.contracts import (
    DatasetPlan,
    ExecutionPolicy,
    PlannedStep,
    QualityResult,
    SourceCoverage,
    WorkflowDefinition,
    WorkflowPlan,
)
from cfb_data.analytics.datasets import DatasetsResource
from cfb_data.errors import (
    CFBDAnalyticsError,
    CFBDDefinitionError,
    CFBDRunError,
)

_CURATED_WORKFLOWS = frozenset(
    {
        "cfbd.team_season_analysis",
        "cfbd.single_game_analysis",
        "cfbd.program_history",
    }
)


@dataclass(frozen=True, slots=True)
class WorkflowOutputs[FrameT](Mapping[str, FrameT]):
    """Expose immutable named DataFrame outputs from one workflow."""

    _items: Mapping[str, FrameT] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_items", MappingProxyType(dict(self._items)))

    def __getitem__(self, key: str) -> FrameT:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True, slots=True)
class WorkflowRun[FrameT]:
    """Return named outputs and immutable child artifact evidence."""

    run_id: str
    definition_id: str
    outputs: WorkflowOutputs[FrameT]
    artifacts: Mapping[str, tuple[ArtifactRef, ...]]
    child_run_ids: tuple[str, ...]
    reused_steps: tuple[str, ...]
    quality: Mapping[str, tuple[QualityResult, ...]]
    coverage: Mapping[str, tuple[SourceCoverage, ...]]
    parent_run_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifacts",
            MappingProxyType(
                {name: tuple(refs) for name, refs in self.artifacts.items()}
            ),
        )
        object.__setattr__(self, "quality", MappingProxyType(dict(self.quality)))
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))


class WorkflowsResource[FrameT]:
    """Run three curated workflows through the shared dataset engine."""

    def __init__(
        self,
        engine: _AnalyticsEngine[FrameT],
        datasets: DatasetsResource[FrameT],
        default_policy: ExecutionPolicy,
    ) -> None:
        self._engine = engine
        self._datasets = datasets
        self._default_policy = default_policy

    async def plan(
        self,
        definition: str | WorkflowDefinition[BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
    ) -> WorkflowPlan:
        """Plan one curated workflow without making an API request."""
        selected = policy or self._default_policy
        if not isinstance(definition, str) or definition not in _CURATED_WORKFLOWS:
            return await self._engine.plan_workflow(
                definition,
                params=params,
                policy=selected,
            )
        validated: BaseModel
        plans: tuple[DatasetPlan, ...]
        outputs: tuple[str, ...]
        if definition == "cfbd.team_season_analysis":
            validated = _workflow_params(TeamSeasonWorkflowParams, params)
            plans = await self._team_season_plans(validated, selected)
            source_keys = self._source_keys(_team_season_calls(validated))
            outputs = (
                "game_summaries",
                "team_games",
                "player_game_stats",
                "rosters",
                "team_seasons",
                "player_seasons",
                "coach_seasons",
            )
        elif definition == "cfbd.single_game_analysis":
            validated = _workflow_params(SingleGameWorkflowParams, params)
            plans = ()
            source_keys = frozenset()
            outputs = (
                "game_summaries",
                "team_games",
                "player_game_stats",
                "drives",
                "plays",
                "betting_lines",
            )
        elif definition == "cfbd.program_history":
            validated = _workflow_params(ProgramHistoryParams, params)
            plans = await self._program_history_plans(validated, selected)
            source_keys = self._source_keys(_program_history_calls(validated))
            outputs = (
                "game_summaries",
                "team_games",
                "team_seasons",
                "recruiting_classes",
                "coach_seasons",
                "poll_rankings",
            )
        else:
            raise CFBDDefinitionError(f"Unknown workflow definition: {definition}")

        if definition == "cfbd.single_game_analysis":
            logical_requests = 6
            worst_case = 6 * self._engine.max_attempts_per_request
            steps = tuple(
                PlannedStep(
                    id=name,
                    kind="dataset",
                    dependencies=("game_summaries",)
                    if name in {"drives", "plays"}
                    else (),
                    operation_id=f"cfbd.{name}",
                    checkpoint_candidate=True,
                )
                for name in outputs
            )
        else:
            logical_requests = len(source_keys)
            worst_case = logical_requests * self._engine.max_attempts_per_request
            steps = tuple(
                PlannedStep(
                    id=f"dataset_{index:03d}",
                    kind="dataset",
                    dependencies=(),
                    operation_id=plan.definition_id,
                    checkpoint_candidate=True,
                )
                for index, plan in enumerate(plans)
            )
        if worst_case > selected.max_http_attempts:
            raise CFBDDefinitionError(
                "Planned workflow attempts exceed the execution budget"
            )
        return WorkflowPlan(
            definition_id=definition,
            definition_revision=1,
            parameter_fingerprint=_parameter_digest(validated),
            steps=steps,
            outputs=outputs,
            logical_source_requests=logical_requests,
            worst_case_http_attempts=worst_case,
        )

    async def run(
        self,
        definition: str | WorkflowDefinition[BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
    ) -> WorkflowRun[FrameT]:
        """Run one curated workflow and return named frames and artifacts."""
        selected = policy or self._default_policy
        if not isinstance(definition, str) or definition not in _CURATED_WORKFLOWS:
            executed = await self._engine.run_workflow_definition(
                definition,
                params=params,
                policy=selected,
                resume_from=resume_from,
            )
            return WorkflowRun(
                run_id=executed.run_id,
                definition_id=executed.definition_id,
                outputs=WorkflowOutputs(executed.frames),
                artifacts={
                    name: (artifact,) for name, artifact in executed.artifacts.items()
                },
                child_run_ids=(),
                reused_steps=executed.reused_steps,
                quality=executed.quality,
                coverage=executed.coverage,
                parent_run_id=executed.parent_run_id,
            )
        plan = await self.plan(definition, params=params, policy=selected)
        run_id, parent_run_id, started_at = await self._engine.begin_workflow_run(
            definition_id=definition,
            definition_revision=plan.definition_revision,
            parameter_digest=plan.parameter_fingerprint,
            resume_from=resume_from,
            step_count=len(plan.steps),
        )
        try:
            with (
                _attempt_budget_scope(selected.max_http_attempts),
                _execution_resources_scope(selected),
            ):
                if definition == "cfbd.team_season_analysis":
                    result = await self._run_team_season(
                        _workflow_params(TeamSeasonWorkflowParams, params), selected
                    )
                elif definition == "cfbd.single_game_analysis":
                    result = await self._run_single_game(
                        _workflow_params(SingleGameWorkflowParams, params), selected
                    )
                elif definition == "cfbd.program_history":
                    result = await self._run_program_history(
                        _workflow_params(ProgramHistoryParams, params), selected
                    )
                else:
                    raise CFBDDefinitionError(
                        f"Unknown workflow definition: {definition}"
                    )
            await self._engine.complete_workflow_run(
                run_id=run_id,
                definition_id=definition,
                artifacts=result.artifacts,
                step_count=len(plan.steps),
                started_at=started_at,
            )
            return replace(
                result,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
        except asyncio.CancelledError:
            await self._engine.fail_workflow_run(
                run_id=run_id,
                definition_id=definition,
                step_id="workflow",
                category="cancelled",
                cancelled=True,
                step_count=len(plan.steps),
                started_at=started_at,
            )
            raise
        except Exception as exc:
            cause = _workflow_failure(exc)
            step_id = cause.step_id if isinstance(cause, CFBDRunError) else "workflow"
            category = (
                cause.category
                if isinstance(cause, CFBDRunError)
                else _failure_category(cause)
            )
            await self._engine.fail_workflow_run(
                run_id=run_id,
                definition_id=definition,
                step_id=step_id,
                category=category,
                cancelled=False,
                step_count=len(plan.steps),
                started_at=started_at,
            )
            raise CFBDRunError(
                run_id=run_id,
                step_id=step_id,
                category=category,
            ) from cause

    async def team_season_analysis(
        self,
        *,
        season: int,
        team: str,
        policy: ExecutionPolicy | None = None,
    ) -> WorkflowOutputs[FrameT]:
        """Return the default team-season analytical outputs."""
        return (
            await self.run(
                "cfbd.team_season_analysis",
                params={"season": season, "team": team},
                policy=policy,
            )
        ).outputs

    async def single_game_analysis(
        self,
        *,
        game_id: int,
        policy: ExecutionPolicy | None = None,
    ) -> WorkflowOutputs[FrameT]:
        """Return the default single-game analytical outputs."""
        return (
            await self.run(
                "cfbd.single_game_analysis",
                params={"game_id": game_id},
                policy=policy,
            )
        ).outputs

    async def program_history(
        self,
        *,
        team: str,
        start_year: int,
        end_year: int,
        policy: ExecutionPolicy | None = None,
    ) -> WorkflowOutputs[FrameT]:
        """Return bounded multi-season program-history outputs."""
        return (
            await self.run(
                "cfbd.program_history",
                params={
                    "team": team,
                    "start_year": start_year,
                    "end_year": end_year,
                },
                policy=policy,
            )
        ).outputs

    async def _run_team_season(
        self, params: TeamSeasonWorkflowParams, policy: ExecutionPolicy
    ) -> WorkflowRun[FrameT]:
        calls = _team_season_calls(params)
        runs = await self._run_children(calls, policy)
        return _workflow_run("cfbd.team_season_analysis", runs)

    async def _run_single_game(
        self, params: SingleGameWorkflowParams, policy: ExecutionPolicy
    ) -> WorkflowRun[FrameT]:
        game_run = await self._datasets.run(
            "cfbd.game_summaries",
            params={"game_id": params.game_id},
            policy=policy,
        )
        game = _one_game(game_run)
        calls: dict[str, tuple[str, Mapping[str, object]]] = {
            "team_games": (
                "cfbd.team_games",
                {"game_id": params.game_id},
            ),
            "player_game_stats": (
                "cfbd.player_game_stats",
                {"game_id": params.game_id},
            ),
            "drives": (
                "cfbd.drives",
                {
                    "year": game.season,
                    "week": game.week,
                    "season_type": game.season_type,
                    "team": game.home_team,
                    "game_id": game.id,
                },
            ),
            "plays": (
                "cfbd.plays",
                {
                    "year": game.season,
                    "week": game.week,
                    "season_type": game.season_type,
                    "team": game.home_team,
                    "game_id": game.id,
                },
            ),
            "betting_lines": (
                "cfbd.betting_lines",
                {"game_id": params.game_id},
            ),
        }
        runs = {"game_summaries": game_run}
        runs.update(await self._run_children(calls, policy))
        return _workflow_run("cfbd.single_game_analysis", runs)

    async def _run_program_history(
        self, params: ProgramHistoryParams, policy: ExecutionPolicy
    ) -> WorkflowRun[FrameT]:
        calls = _program_history_calls(params)
        child_runs = await self._run_children(calls, policy)
        groups: dict[str, list[DatasetRun[FrameT]]] = {
            "game_summaries": [],
            "team_games": [],
            "team_seasons": [],
            "recruiting_classes": [],
            "coach_seasons": [],
            "poll_rankings": [],
        }
        for name, run in child_runs.items():
            groups[name.split(":", 1)[0]].append(run)
        contracts = {
            "game_summaries": GAME_SUMMARIES,
            "team_games": TEAM_GAMES,
            "team_seasons": TEAM_SEASONS,
            "recruiting_classes": RECRUITING_CLASSES,
            "coach_seasons": COACH_SEASONS,
            "poll_rankings": POLL_RANKINGS,
        }
        frames: dict[str, FrameT] = {}
        artifacts: dict[str, tuple[ArtifactRef, ...]] = {}
        for name, runs in groups.items():
            refs = tuple(run.artifact for run in runs)
            artifacts[name] = refs
            frames[name] = await self._engine.materialize_artifacts(
                contracts[name], refs
            )
        return WorkflowRun(
            run_id="pending",
            definition_id="cfbd.program_history",
            outputs=WorkflowOutputs(frames),
            artifacts=artifacts,
            child_run_ids=tuple(run.run_id for run in child_runs.values()),
            reused_steps=tuple(
                f"{name}:{step}"
                for name, run in child_runs.items()
                for step in run.reused_steps
            ),
            quality={
                name: tuple(result for run in runs for result in run.quality)
                for name, runs in groups.items()
            },
            coverage={
                name: tuple(result for run in runs for result in run.coverage)
                for name, runs in groups.items()
            },
            parent_run_id=None,
        )

    async def _run_children(
        self,
        calls: Mapping[str, tuple[str, Mapping[str, object]]],
        policy: ExecutionPolicy,
    ) -> dict[str, DatasetRun[FrameT]]:
        tasks: dict[str, asyncio.Task[DatasetRun[FrameT]]] = {}
        async with asyncio.TaskGroup() as group:
            for name, (definition, params) in calls.items():
                tasks[name] = group.create_task(
                    self._datasets.run(definition, params=params, policy=policy)
                )
        return {name: tasks[name].result() for name in calls}

    def _source_keys(
        self,
        calls: Mapping[str, tuple[str, Mapping[str, object]]],
    ) -> frozenset[str]:
        keys: set[str] = set()
        for definition, params in calls.values():
            keys.update(self._engine.source_request_keys(definition, params=params))
        return frozenset(keys)

    async def _team_season_plans(
        self, params: TeamSeasonWorkflowParams, policy: ExecutionPolicy
    ) -> tuple[DatasetPlan, ...]:
        return tuple(
            [
                await self._datasets.plan(definition, params=values, policy=policy)
                for definition, values in _team_season_calls(params).values()
            ]
        )

    async def _program_history_plans(
        self, params: ProgramHistoryParams, policy: ExecutionPolicy
    ) -> tuple[DatasetPlan, ...]:
        plans: list[DatasetPlan] = []
        for definition, values in _program_history_calls(params).values():
            plans.append(
                await self._datasets.plan(definition, params=values, policy=policy)
            )
        return tuple(plans)


def _workflow_run[FrameT](
    definition_id: str, runs: Mapping[str, DatasetRun[FrameT]]
) -> WorkflowRun[FrameT]:
    return WorkflowRun(
        run_id="pending",
        definition_id=definition_id,
        outputs=WorkflowOutputs({name: run.frame for name, run in runs.items()}),
        artifacts={name: (run.artifact,) for name, run in runs.items()},
        child_run_ids=tuple(run.run_id for run in runs.values()),
        reused_steps=tuple(
            f"{name}:{step}" for name, run in runs.items() for step in run.reused_steps
        ),
        quality={name: run.quality for name, run in runs.items()},
        coverage={name: run.coverage for name, run in runs.items()},
        parent_run_id=None,
    )


def _team_season_calls(
    params: TeamSeasonWorkflowParams,
) -> dict[str, tuple[str, Mapping[str, object]]]:
    """Return the single source of truth for team-season child datasets."""
    return {
        "game_summaries": (
            "cfbd.game_summaries",
            {"year": params.season, "team": params.team},
        ),
        "team_games": (
            "cfbd.team_games",
            {"year": params.season, "team": params.team},
        ),
        "player_game_stats": (
            "cfbd.player_game_stats",
            {"year": params.season, "team": params.team},
        ),
        "rosters": (
            "cfbd.rosters",
            {"season": params.season, "team": params.team},
        ),
        "team_seasons": (
            "cfbd.team_seasons",
            {"season": params.season, "team": params.team},
        ),
        "player_seasons": (
            "cfbd.player_seasons",
            {"season": params.season, "team": params.team},
        ),
        "coach_seasons": (
            "cfbd.coach_seasons",
            {"year": params.season, "team": params.team},
        ),
    }


def _program_history_calls(
    params: ProgramHistoryParams,
) -> dict[str, tuple[str, Mapping[str, object]]]:
    """Return deterministic bounded child datasets for program history."""
    calls: dict[str, tuple[str, Mapping[str, object]]] = {}
    for year in range(params.start_year, params.end_year + 1):
        suffix = str(year)
        calls[f"game_summaries:{suffix}"] = (
            "cfbd.game_summaries",
            {"year": year, "team": params.team},
        )
        calls[f"team_games:{suffix}"] = (
            "cfbd.team_games",
            {"year": year, "team": params.team},
        )
        calls[f"team_seasons:{suffix}"] = (
            "cfbd.team_seasons",
            {"season": year, "team": params.team},
        )
        calls[f"recruiting_classes:{suffix}"] = (
            "cfbd.recruiting_classes",
            {"class_year": year, "team": params.team},
        )
        calls[f"poll_rankings:{suffix}"] = (
            "cfbd.poll_rankings",
            {"season": year, "team": params.team},
        )
    calls["coach_seasons:range"] = (
        "cfbd.coach_seasons",
        {
            "team": params.team,
            "min_year": params.start_year,
            "max_year": params.end_year,
        },
    )
    return calls


def _one_game[FrameT](run: DatasetRun[FrameT]) -> GameSummary:
    table = run.artifact.load_table()
    rows = _models_from_arrow_table(
        row_model=GameSummary,
        response_adapter=TypeAdapter(list[GameSummary]),
        table=table,
    )
    if len(rows) != 1:
        raise CFBDAnalyticsError(
            "Single-game workflow selector did not return one game"
        )
    return rows[0]


def _workflow_params[ParamsT: BaseModel](
    model: type[ParamsT], params: Mapping[str, object] | BaseModel
) -> ParamsT:
    if isinstance(params, model):
        return params
    if isinstance(params, BaseModel):
        raise CFBDDefinitionError("Workflow parameter model is incompatible")
    try:
        return model.model_validate(dict(params))
    except ValidationError as exc:
        raise CFBDDefinitionError("Workflow parameters are invalid") from exc


def _parameter_digest(parameters: BaseModel) -> str:
    from cfb_data.analytics.contracts import parameter_fingerprint

    return parameter_fingerprint(parameters)


def _workflow_failure(exception: Exception) -> Exception:
    """Return the first child failure from a TaskGroup exception tree."""
    if isinstance(exception, ExceptionGroup):
        for child in exception.exceptions:
            if isinstance(child, Exception):
                return _workflow_failure(child)
    return exception


__all__ = ["WorkflowOutputs", "WorkflowRun", "WorkflowsResource"]
