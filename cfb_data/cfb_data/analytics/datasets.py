"""Expose curated datasets and advanced execution controls."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from cfb_data.analytics._engine import DatasetRun, _AnalyticsEngine
from cfb_data.analytics.artifacts import ArtifactDescriptor, RunDescriptor
from cfb_data.analytics.contracts import (
    DatasetDefinition,
    DatasetPlan,
    ExecutionPolicy,
)
from cfb_data.enums import Classification, RankingPoll, SeasonType

type _SeasonTypeArgument = (
    SeasonType
    | Literal[
        "regular",
        "postseason",
        "both",
        "allstar",
        "spring_regular",
        "spring_postseason",
    ]
)
type _ClassificationArgument = Classification | Literal["fbs", "fcs", "ii", "iii"]
type _RankingPollArgument = RankingPoll | Literal["cfp"]


class DatasetsResource[FrameT]:
    """Run validated curated datasets through one shared analytics engine."""

    def __init__(self, engine: _AnalyticsEngine[FrameT]) -> None:
        self._engine = engine

    async def plan(
        self,
        definition: str | DatasetDefinition[BaseModel, BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
    ) -> DatasetPlan:
        """Compile and inspect a dataset without making an API request."""
        return await self._engine.plan_dataset(definition, params=params, policy=policy)

    async def run(
        self,
        definition: str | DatasetDefinition[BaseModel, BaseModel],
        *,
        params: Mapping[str, object] | BaseModel,
        policy: ExecutionPolicy | None = None,
        resume_from: str | None = None,
    ) -> DatasetRun[FrameT]:
        """Run a dataset and return its frame and immutable execution evidence."""
        return await self._engine.run_dataset(
            definition,
            params=params,
            policy=policy,
            resume_from=resume_from,
        )

    async def game_summaries(
        self,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
    ) -> FrameT:
        """Return one row per selected game with conservative result semantics."""
        run = await self.run(
            "cfbd.game_summaries",
            params={
                "year": year,
                "week": week,
                "season_type": season_type,
                "team": team,
                "conference": conference,
                "game_id": game_id,
            },
        )
        return run.frame

    async def team_games(
        self,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
    ) -> FrameT:
        """Return exactly two team-perspective rows for each selected game."""
        return (
            await self.run(
                "cfbd.team_games",
                params={
                    "year": year,
                    "week": week,
                    "season_type": season_type,
                    "team": team,
                    "conference": conference,
                    "game_id": game_id,
                },
            )
        ).frame

    async def player_game_stats(
        self,
        *,
        year: int | None = None,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
    ) -> FrameT:
        """Return long-form player display statistics for selected games."""
        return (
            await self.run(
                "cfbd.player_game_stats",
                params={
                    "year": year,
                    "week": week,
                    "season_type": season_type,
                    "team": team,
                    "conference": conference,
                    "game_id": game_id,
                },
            )
        ).frame

    async def drives(
        self,
        *,
        year: int,
        week: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        offense: str | None = None,
        defense: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
    ) -> FrameT:
        """Return validated drives with explicit clock and score arithmetic."""
        return (
            await self.run(
                "cfbd.drives",
                params={
                    "year": year,
                    "week": week,
                    "season_type": season_type,
                    "team": team,
                    "offense": offense,
                    "defense": defense,
                    "conference": conference,
                    "game_id": game_id,
                },
            )
        ).frame

    async def plays(
        self,
        *,
        year: int,
        week: int,
        season_type: _SeasonTypeArgument | None = None,
        team: str | None = None,
        offense: str | None = None,
        defense: str | None = None,
        conference: str | None = None,
        game_id: int | None = None,
    ) -> FrameT:
        """Return validated historical plays with stable perspective fields."""
        return (
            await self.run(
                "cfbd.plays",
                params={
                    "year": year,
                    "week": week,
                    "season_type": season_type,
                    "team": team,
                    "offense": offense,
                    "defense": defense,
                    "conference": conference,
                    "game_id": game_id,
                },
            )
        ).frame

    async def rosters(
        self,
        *,
        season: int,
        team: str | None = None,
        classification: _ClassificationArgument | None = None,
    ) -> FrameT:
        """Return roster memberships with explicit roster season."""
        return (
            await self.run(
                "cfbd.rosters",
                params={
                    "season": season,
                    "team": team,
                    "classification": classification,
                },
            )
        ).frame

    async def team_seasons(
        self,
        *,
        season: int | None = None,
        team: str | None = None,
        conference: str | None = None,
    ) -> FrameT:
        """Return record-established team seasons with common stat groups."""
        return (
            await self.run(
                "cfbd.team_seasons",
                params={"season": season, "team": team, "conference": conference},
            )
        ).frame

    async def player_seasons(
        self,
        *,
        season: int,
        team: str | None = None,
        conference: str | None = None,
        category: str | None = None,
    ) -> FrameT:
        """Return the union of roster and season-stat athlete evidence."""
        return (
            await self.run(
                "cfbd.player_seasons",
                params={
                    "season": season,
                    "team": team,
                    "conference": conference,
                    "category": category,
                },
            )
        ).frame

    async def poll_rankings(
        self,
        *,
        season: int,
        season_type: _SeasonTypeArgument | None = None,
        week: int | None = None,
        poll: _RankingPollArgument | None = None,
        team: str | None = None,
    ) -> FrameT:
        """Return long-form poll snapshots preserving source ordinals."""
        return (
            await self.run(
                "cfbd.poll_rankings",
                params={
                    "season": season,
                    "season_type": season_type,
                    "week": week,
                    "poll": poll,
                    "team": team,
                },
            )
        ).frame

    async def betting_lines(
        self,
        *,
        game_id: int | None = None,
        season: int | None = None,
        season_type: _SeasonTypeArgument | None = None,
        week: int | None = None,
        team: str | None = None,
        provider: str | None = None,
    ) -> FrameT:
        """Return provider quotes without implicit provider selection."""
        return (
            await self.run(
                "cfbd.betting_lines",
                params={
                    "game_id": game_id,
                    "season": season,
                    "season_type": season_type,
                    "week": week,
                    "team": team,
                    "provider": provider,
                },
            )
        ).frame

    async def recruiting_classes(
        self, *, class_year: int, team: str | None = None
    ) -> FrameT:
        """Return ranked and commitment-backed recruiting classes."""
        return (
            await self.run(
                "cfbd.recruiting_classes",
                params={"class_year": class_year, "team": team},
            )
        ).frame

    async def coach_seasons(
        self,
        *,
        team: str | None = None,
        year: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
    ) -> FrameT:
        """Return detailed coach-team-season attribution rows."""
        return (
            await self.run(
                "cfbd.coach_seasons",
                params={
                    "team": team,
                    "year": year,
                    "min_year": min_year,
                    "max_year": max_year,
                },
            )
        ).frame

    @property
    def artifact_store_path(self) -> Path:
        """Return the configured opaque store root for operational inspection."""
        return self._engine.artifact_store_path

    async def prune_artifacts(self, *, dry_run: bool = True) -> tuple[str, ...]:
        """List or explicitly prune unreferenced, unpinned artifacts."""
        return await self._engine.prune_artifacts(dry_run=dry_run)

    async def cleanup_orphans(
        self,
        *,
        older_than: timedelta = timedelta(days=1),
    ) -> int:
        """Remove stale staging directories left by interrupted writers."""
        return await self._engine.cleanup_orphans(older_than=older_than)

    async def list_artifacts(
        self, *, limit: int = 100
    ) -> tuple[ArtifactDescriptor, ...]:
        """List newest safe artifact descriptors without loading table content."""
        return await self._engine.list_artifacts(limit=limit)

    async def inspect_artifact(self, artifact_id: str) -> ArtifactDescriptor:
        """Inspect one artifact through its opaque public identifier."""
        return await self._engine.inspect_artifact(artifact_id)

    async def pin_artifact(self, artifact_id: str, *, pinned: bool = True) -> None:
        """Pin or unpin one artifact against explicit garbage collection."""
        await self._engine.pin_artifact(artifact_id, pinned=pinned)

    async def list_runs(
        self,
        *,
        definition_id: str | None = None,
        limit: int = 100,
    ) -> tuple[RunDescriptor, ...]:
        """List newest safe run descriptors with optional definition filtering."""
        return await self._engine.list_runs(
            definition_id=definition_id,
            limit=limit,
        )

    async def inspect_run(self, run_id: str) -> RunDescriptor:
        """Inspect one immutable run by its safe identifier."""
        return await self._engine.inspect_run(run_id)


__all__ = ["DatasetRun", "DatasetsResource"]
