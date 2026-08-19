"""Execute pure local transform and dataset validation boundaries."""

from __future__ import annotations

import asyncio
import secrets
import time
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal, TypeVar, cast, get_args, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter, ValidationError

from cfb_data._observability import _failure_category
from cfb_data._tabular import (
    _analytics_arrow_table_from_models,
    _analytics_models_from_arrow_table,
    _AnalyticsTableIdentity,
    _logical_schema,
    _logical_schema_digest,
)

from ._artifact_contract import _DatasetContractEvidence
from ._artifacts import _json_schema_digest, _JsonArtifactCodec, _TableArtifactCodec
from ._checkpoints import (
    _checkpoint_scope,
    _node_fingerprint,
    _OutputContractIdentity,
    _SourceBehavior,
    _UpstreamArtifactIdentity,
)
from ._compiler import _digest
from ._compute import _TransformExecutorSession
from ._contracts import _table_row_model
from ._execution import _NodeResult, _resolve_arguments
from ._graph import _CompiledNode, _NodeRef, _ValueRef
from ._observability import _AnalyticsDispatcher
from ._persistence import (
    _ArtifactObjectStore,
    _CheckpointCandidate,
    _NodeState,
    _RunDatabase,
    _StoredArtifact,
)
from ._recipes import StepRecipe
from .errors import (
    CFBDArtifactCorruptionError,
    CFBDPersistenceError,
    CFBDRecipeCompilationError,
)
from .observability import AnalyticsEvent, AnalyticsEventType, AnalyticsOutcome

type _Backend = Literal["pandas", "polars"]

_DEFAULT_LEASE_TTL: Final = timedelta(seconds=30)
_DEFAULT_LEASE_POLL_SECONDS: Final = 0.05


@dataclass(frozen=True, slots=True)
class _NodeLease:
    """Identify one run's token-owned deterministic transform lease."""

    key: str
    owner_token: str


class _TransformRunner:
    """Own local transform validation, checkpointing, and node evidence."""

    def __init__(
        self,
        *,
        provider: _TransformExecutorSession,
        database: _RunDatabase,
        object_store: _ArtifactObjectStore,
        run_id: str,
        credential_scope: str,
        parent_run_id: str | None,
        source_behavior: _SourceBehavior,
        checkpoint_nodes: frozenset[str] | None = None,
        recompute_nodes: frozenset[str] = frozenset(),
        backend: _Backend,
        dispatcher: _AnalyticsDispatcher,
        max_compute_attempts: int = 1,
        compute_timeout_seconds: float | None = None,
        lease_ttl: timedelta = _DEFAULT_LEASE_TTL,
        lease_poll_seconds: float = _DEFAULT_LEASE_POLL_SECONDS,
    ) -> None:
        """Initialize one run-scoped local transformation runner."""
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("Transform lease TTL must be positive")
        if lease_poll_seconds <= 0:
            raise ValueError("Transform lease polling interval must be positive")
        if max_compute_attempts < 1:
            raise ValueError("Transform compute attempts must be positive")
        if compute_timeout_seconds is not None and compute_timeout_seconds <= 0:
            raise ValueError("Transform timeout must be positive")
        self._provider = provider
        self._database = database
        self._object_store = object_store
        self._run_id = run_id
        self._credential_scope = credential_scope
        self._parent_run_id = parent_run_id
        self._source_behavior = source_behavior
        self._checkpoint_nodes = checkpoint_nodes
        self._recompute_nodes = recompute_nodes
        self._backend = backend
        self._dispatcher = dispatcher
        self._max_compute_attempts = max_compute_attempts
        self._compute_timeout_seconds = compute_timeout_seconds
        self._lease_ttl = lease_ttl
        self._lease_poll_seconds = lease_poll_seconds

    async def run_batch(
        self,
        nodes: Sequence[_CompiledNode],
        results: Mapping[str, _NodeResult],
    ) -> Mapping[str, _NodeResult]:
        """Execute ready local nodes and cancel all siblings on failure."""
        tasks = [
            asyncio.create_task(
                self._run_node(node, results),
                name=f"cfb-data-transform:{node.node_id}",
            )
            for node in nodes
        ]
        if not tasks:
            return {}
        try:
            return {node_id: result for node_id, result in await asyncio.gather(*tasks)}
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _run_node(
        self,
        node: _CompiledNode,
        results: Mapping[str, _NodeResult],
    ) -> tuple[str, _NodeResult]:
        if node.kind not in {"step", "dataset"}:
            raise CFBDRecipeCompilationError(
                "Local transform runner accepts only steps and datasets"
            )
        placement = self._placement(node)
        await asyncio.to_thread(
            self._database.transition_node,
            self._run_id,
            node.node_id,
            "ready",
        )
        self._emit(
            AnalyticsEventType.step_ready,
            node.node_id,
            placement=placement,
        )
        parameters = _resolve_arguments(
            node.arguments,
            results,
            allow_node_values=True,
        )
        row_model = _table_row_model(node, required=False)
        output_identity = _output_identity(node)
        control_adapter = _control_adapter(node, results) if row_model is None else None
        output_contract = _output_contract(
            output_identity,
            row_model=row_model,
            control_adapter=control_adapter,
        )
        upstream = _upstream_identities(node, results)
        fingerprint = _node_fingerprint(
            node,
            parameters=_semantic_parameters(node, parameters),
            upstream=upstream,
            outputs=(output_contract,),
            backend=self._backend,
        )
        scope = _checkpoint_scope(
            node,
            parent_run_id=self._parent_run_id,
            source_behavior=self._source_behavior,
            checkpoint_eligible=self._checkpoint_eligible(node),
        )
        if node.node_id in self._recompute_nodes:
            scope = "none"
        reused = await self._load_compatible_checkpoint(
            node,
            row_model=row_model,
            control_adapter=control_adapter,
            output_identity=output_identity,
            fingerprint=fingerprint,
            scope=scope,
        )
        if reused is not None:
            return node.node_id, reused

        lease: _NodeLease | None = None
        if (
            fingerprint is not None
            and node.declaration.deterministic
            and self._checkpoint_eligible(node)
            and scope in {"global", "parent_then_global"}
        ):
            reused, lease = await self._reuse_or_acquire_lease(
                node,
                row_model=row_model,
                control_adapter=control_adapter,
                output_identity=output_identity,
                fingerprint=fingerprint,
                scope=scope,
                placement=placement,
            )
            if reused is not None:
                return node.node_id, reused

        renewal: asyncio.Task[None] | None = None
        try:
            await asyncio.to_thread(
                self._database.transition_node,
                self._run_id,
                node.node_id,
                "running",
            )
            self._emit(
                AnalyticsEventType.step_started,
                node.node_id,
                placement=placement,
            )
            if lease is not None:
                renewal = asyncio.create_task(
                    self._renew_lease(lease),
                    name=f"cfb-data-node-lease:{node.node_id}",
                )
            started = time.monotonic()
            try:
                raw = await self._compute(node, parameters)
                await self._require_live_renewal(renewal)
                value: object
                if row_model is not None:
                    rows, artifact, fingerprint = await asyncio.to_thread(
                        self._validate_store_and_bind_table,
                        raw,
                        row_model,
                        output_identity,
                        node,
                        fingerprint,
                        placement,
                        self._checkpoint_eligible(node),
                        lease,
                    )
                    value = rows
                    row_count: int | None = len(rows)
                else:
                    control_value, artifact, fingerprint = await asyncio.to_thread(
                        self._validate_store_and_bind_control,
                        raw,
                        _require_control_adapter(control_adapter),
                        output_identity,
                        node,
                        fingerprint,
                        placement,
                        self._checkpoint_eligible(node),
                        lease,
                    )
                    value = control_value
                    row_count = None
            except asyncio.CancelledError:
                await self._terminal(node.node_id, "cancelled", "cancelled")
                self._emit(
                    AnalyticsEventType.step_cancelled,
                    node.node_id,
                    placement=placement,
                    outcome=AnalyticsOutcome.cancelled,
                    duration=time.monotonic() - started,
                )
                raise
            except Exception as exc:
                category = _failure_category(exc)
                await self._terminal(node.node_id, "failed", category)
                self._emit(
                    AnalyticsEventType.step_failed,
                    node.node_id,
                    placement=placement,
                    outcome=AnalyticsOutcome.error,
                    failure_category=category,
                    duration=time.monotonic() - started,
                )
                raise
            self._emit(
                AnalyticsEventType.step_completed,
                node.node_id,
                placement=placement,
                outcome=AnalyticsOutcome.success,
                artifact=artifact.content_digest,
                row_count=row_count,
                duration=time.monotonic() - started,
            )
            return node.node_id, _NodeResult(
                value=value,
                artifact=artifact,
                node_fingerprint=fingerprint,
                row_model=row_model,
            )
        finally:
            await self._close_lease(node, lease, renewal, placement=placement)

    async def _compute(
        self,
        node: _CompiledNode,
        parameters: Mapping[str, object],
    ) -> object:
        if node.kind == "dataset":
            return parameters["value"]
        recipe = cast(StepRecipe[..., object], node.recipe)
        for attempt in range(1, self._max_compute_attempts + 1):
            try:
                if self._compute_timeout_seconds is None:
                    return await self._provider.execute(recipe, parameters)
                async with asyncio.timeout(self._compute_timeout_seconds):
                    return await self._provider.execute(recipe, parameters)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= self._max_compute_attempts:
                    raise
                self._emit(
                    AnalyticsEventType.step_retry,
                    node.node_id,
                    placement=self._provider.placement,
                    outcome=AnalyticsOutcome.error,
                    failure_category=_failure_category(exc),
                    attempt_id=str(attempt),
                )
        raise RuntimeError("Transform attempt loop exhausted")

    def _validate_store_and_bind_table(
        self,
        raw: object,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        node: _CompiledNode,
        fingerprint: str | None,
        placement: Literal["coordinator", "local", "dask"],
        checkpoint_eligible: bool,
        lease: _NodeLease | None,
    ) -> tuple[list[BaseModel], _StoredArtifact, str]:
        try:
            rows = _row_list_adapter(row_model).validate_python(raw)
        except ValidationError as exc:
            raise CFBDRecipeCompilationError(
                "Transform output violates its declared row contract"
            ) from exc
        if node.kind == "dataset":
            _validate_dataset_quality(node, rows)
        table = _analytics_arrow_table_from_models(
            row_model=row_model,
            models=rows,
            identity=identity,
        )
        with self._object_store.staging_directory() as directory:
            staged = _TableArtifactCodec().stage(
                directory=directory,
                table=table,
                row_model=row_model,
                identity=identity,
                dataset=_dataset_contract(node),
            )
            resolved_fingerprint = self._resolved_fingerprint(
                node,
                fingerprint,
                staged.manifest.content_digest,
            )
            artifact, _ = self._database.publish_completed_node(
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=resolved_fingerprint,
                staged=staged,
                object_store=self._object_store,
                placement=placement,
                checkpoint_eligible=checkpoint_eligible,
                lease_key=None if lease is None else lease.key,
                lease_owner_token=None if lease is None else lease.owner_token,
            )
        return rows, artifact, resolved_fingerprint

    def _validate_store_and_bind_control(
        self,
        raw: object,
        adapter: TypeAdapter[object],
        identity: _AnalyticsTableIdentity,
        node: _CompiledNode,
        fingerprint: str | None,
        placement: Literal["coordinator", "local", "dask"],
        checkpoint_eligible: bool,
        lease: _NodeLease | None,
    ) -> tuple[object, _StoredArtifact, str]:
        """Validate, publish, and bind one bounded modeled-JSON control value."""
        try:
            value = adapter.validate_python(raw, strict=True)
        except ValidationError as exc:
            raise CFBDRecipeCompilationError(
                "Transform output violates its declared control contract"
            ) from exc
        with self._object_store.staging_directory() as directory:
            staged = _JsonArtifactCodec().stage(
                directory=directory,
                value=value,
                adapter=adapter,
                identity=identity,
            )
            resolved_fingerprint = self._resolved_fingerprint(
                node,
                fingerprint,
                staged.manifest.content_digest,
            )
            artifact, _ = self._database.publish_completed_node(
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=resolved_fingerprint,
                staged=staged,
                object_store=self._object_store,
                placement=placement,
                checkpoint_eligible=checkpoint_eligible,
                lease_key=None if lease is None else lease.key,
                lease_owner_token=None if lease is None else lease.owner_token,
            )
        return value, artifact, resolved_fingerprint

    async def _load_compatible_checkpoint(
        self,
        node: _CompiledNode,
        *,
        row_model: type[BaseModel] | None,
        control_adapter: TypeAdapter[object] | None,
        output_identity: _AnalyticsTableIdentity,
        fingerprint: str | None,
        scope: Literal["none", "parent", "parent_then_global", "global"],
    ) -> _NodeResult | None:
        """Load and bind one compatible validated checkpoint when present."""
        if fingerprint is None:
            return None
        candidate = await asyncio.to_thread(
            self._database.find_checkpoint,
            node_fingerprint=fingerprint,
            output_name="value",
            scope=scope,
            parent_run_id=self._parent_run_id,
            credential_scope=self._credential_scope,
        )
        if candidate is None:
            return None
        if row_model is not None:
            return await self._load_table_candidate(
                node,
                row_model,
                output_identity,
                fingerprint,
                candidate,
            )
        return await self._load_control_candidate(
            node,
            _require_control_adapter(control_adapter),
            output_identity,
            fingerprint,
            candidate,
        )

    async def _reuse_or_acquire_lease(
        self,
        node: _CompiledNode,
        *,
        row_model: type[BaseModel] | None,
        control_adapter: TypeAdapter[object] | None,
        output_identity: _AnalyticsTableIdentity,
        fingerprint: str,
        scope: Literal["global", "parent_then_global"],
        placement: Literal["coordinator", "local", "dask"],
    ) -> tuple[_NodeResult | None, _NodeLease | None]:
        """Reuse a winner's checkpoint or acquire exclusive compute ownership."""
        lease = _NodeLease(
            key=_digest(
                {
                    "credential_scope": self._credential_scope,
                    "node_fingerprint": fingerprint,
                    "output_name": "value",
                }
            ),
            owner_token=secrets.token_hex(32),
        )
        waited = False
        while True:
            acquired = await asyncio.to_thread(
                self._database.acquire_node_lease,
                lease_key=lease.key,
                owner_token=lease.owner_token,
                run_id=self._run_id,
                node_id=node.node_id,
                ttl=self._lease_ttl,
            )
            if acquired:
                reused = await self._load_compatible_checkpoint(
                    node,
                    row_model=row_model,
                    control_adapter=control_adapter,
                    output_identity=output_identity,
                    fingerprint=fingerprint,
                    scope=scope,
                )
                if reused is not None:
                    await self._close_lease(
                        node,
                        lease,
                        None,
                        placement=placement,
                    )
                    return reused, None
                return None, lease
            if not waited:
                self._emit(
                    AnalyticsEventType.resource_wait,
                    node.node_id,
                    placement=placement,
                )
                waited = True
            await asyncio.sleep(self._lease_poll_seconds)
            reused = await self._load_compatible_checkpoint(
                node,
                row_model=row_model,
                control_adapter=control_adapter,
                output_identity=output_identity,
                fingerprint=fingerprint,
                scope=scope,
            )
            if reused is not None:
                return reused, None

    async def _renew_lease(self, lease: _NodeLease) -> None:
        """Renew one lease until cancelled or fail closed when ownership is lost."""
        interval = self._lease_ttl.total_seconds() / 3
        while True:
            await asyncio.sleep(interval)
            renewed = await asyncio.to_thread(
                self._database.renew_node_lease,
                lease_key=lease.key,
                owner_token=lease.owner_token,
                ttl=self._lease_ttl,
            )
            if not renewed:
                raise CFBDPersistenceError(category="node_lease_lost")

    @staticmethod
    async def _require_live_renewal(renewal: asyncio.Task[None] | None) -> None:
        """Propagate a completed renewal failure before artifact validation."""
        if renewal is not None and renewal.done():
            await renewal

    async def _close_lease(
        self,
        node: _CompiledNode,
        lease: _NodeLease | None,
        renewal: asyncio.Task[None] | None,
        *,
        placement: Literal["coordinator", "local", "dask"],
    ) -> None:
        """Stop renewal and release ownership without masking primary failures."""
        if renewal is not None:
            renewal.cancel()
            outcomes = await asyncio.gather(renewal, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    self._emit(
                        AnalyticsEventType.checkpoint_rejected,
                        node.node_id,
                        placement=placement,
                        outcome=AnalyticsOutcome.error,
                        failure_category=_failure_category(outcome),
                    )
        if lease is None:
            return
        try:
            await asyncio.to_thread(
                self._database.release_node_lease,
                lease_key=lease.key,
                owner_token=lease.owner_token,
            )
        except Exception as exc:
            self._emit(
                AnalyticsEventType.checkpoint_rejected,
                node.node_id,
                placement=placement,
                outcome=AnalyticsOutcome.error,
                failure_category=_failure_category(exc),
            )

    def _resolved_fingerprint(
        self,
        node: _CompiledNode,
        fingerprint: str | None,
        content_digest: str,
    ) -> str:
        """Bind nondeterministic steps to their originating run and content."""
        if fingerprint is not None:
            return fingerprint
        return _digest(
            {
                "originating_run": self._run_id,
                "node": node.node_id,
                "artifact": content_digest,
            }
        )

    def _checkpoint_eligible(self, node: _CompiledNode) -> bool:
        """Return whether this run may publish reusable evidence for a node."""
        return self._checkpoint_nodes is None or node.node_id in self._checkpoint_nodes

    async def _load_table_candidate(
        self,
        node: _CompiledNode,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        fingerprint: str,
        candidate: _CheckpointCandidate,
    ) -> _NodeResult | None:
        try:
            rows = await asyncio.to_thread(
                self._load_rows,
                node,
                row_model,
                identity,
                candidate,
            )
            await asyncio.to_thread(
                self._database.bind_reused_node,
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=fingerprint,
                candidate=candidate,
                checkpoint_eligible=self._checkpoint_eligible(node),
            )
        except CFBDArtifactCorruptionError:
            self._emit(
                AnalyticsEventType.checkpoint_corrupt,
                node.node_id,
                placement=candidate.binding.placement,
                outcome=AnalyticsOutcome.corrupt,
            )
            return None
        self._emit(
            AnalyticsEventType.step_reused,
            node.node_id,
            placement=candidate.binding.placement,
            outcome=AnalyticsOutcome.reused,
            artifact=candidate.binding.content_digest,
            row_count=len(rows),
        )
        return _NodeResult(
            value=rows,
            artifact=_StoredArtifact(
                content_digest=candidate.binding.content_digest,
                manifest=candidate.manifest,
            ),
            node_fingerprint=fingerprint,
            row_model=row_model,
        )

    async def _load_control_candidate(
        self,
        node: _CompiledNode,
        adapter: TypeAdapter[object],
        identity: _AnalyticsTableIdentity,
        fingerprint: str,
        candidate: _CheckpointCandidate,
    ) -> _NodeResult | None:
        """Load and bind one validated modeled-JSON checkpoint."""
        try:
            value = await asyncio.to_thread(
                _JsonArtifactCodec().load,
                directory=self._object_store.directory(
                    candidate.binding.content_digest
                ),
                manifest=candidate.manifest,
                adapter=adapter,
                identity=identity,
            )
            await asyncio.to_thread(
                self._database.bind_reused_node,
                run_id=self._run_id,
                node_id=node.node_id,
                output_name="value",
                node_fingerprint=fingerprint,
                candidate=candidate,
                checkpoint_eligible=self._checkpoint_eligible(node),
            )
        except CFBDArtifactCorruptionError:
            self._emit(
                AnalyticsEventType.checkpoint_corrupt,
                node.node_id,
                placement=candidate.binding.placement,
                outcome=AnalyticsOutcome.corrupt,
            )
            return None
        self._emit(
            AnalyticsEventType.step_reused,
            node.node_id,
            placement=candidate.binding.placement,
            outcome=AnalyticsOutcome.reused,
            artifact=candidate.binding.content_digest,
        )
        return _NodeResult(
            value=value,
            artifact=_StoredArtifact(
                content_digest=candidate.binding.content_digest,
                manifest=candidate.manifest,
            ),
            node_fingerprint=fingerprint,
            row_model=None,
        )

    def _load_rows(
        self,
        node: _CompiledNode,
        row_model: type[BaseModel],
        identity: _AnalyticsTableIdentity,
        candidate: _CheckpointCandidate,
    ) -> list[BaseModel]:
        table = _TableArtifactCodec().load(
            directory=self._object_store.directory(candidate.binding.content_digest),
            manifest=candidate.manifest,
            row_model=row_model,
            identity=identity,
            dataset=_dataset_contract(node),
        )
        return _analytics_models_from_arrow_table(
            row_model=row_model,
            response_adapter=_row_list_adapter(row_model),
            table=table,
            identity=identity,
        )

    async def _terminal(
        self,
        node_id: str,
        state: _NodeState,
        category: str,
    ) -> None:
        await asyncio.to_thread(
            self._database.transition_node,
            self._run_id,
            node_id,
            state,
            failure_category=category,
        )

    def _emit(
        self,
        event_type: AnalyticsEventType,
        node_id: str,
        *,
        placement: Literal["coordinator", "local", "dask"],
        outcome: AnalyticsOutcome | None = None,
        artifact: str | None = None,
        row_count: int | None = None,
        failure_category: str | None = None,
        duration: float | None = None,
        attempt_id: str | None = None,
    ) -> None:
        self._dispatcher.emit(
            AnalyticsEvent(
                event_type=event_type,
                run_id=self._run_id,
                node_id=node_id,
                attempt_id=attempt_id,
                outcome=outcome,
                placement=placement,
                artifact_digest=artifact,
                row_count=row_count,
                failure_category=failure_category,
                duration_seconds=duration,
            )
        )

    def _placement(
        self,
        node: _CompiledNode,
    ) -> Literal["coordinator", "local", "dask"]:
        """Attribute pure compute without claiming dataset validation ran remotely."""
        return self._provider.placement if node.kind == "step" else "coordinator"


def _output_identity(node: _CompiledNode) -> _AnalyticsTableIdentity:
    recipe_id = node.declaration.recipe_id
    revision = node.declaration.revision
    if recipe_id is None or revision is None:
        return _AnalyticsTableIdentity(
            output_id=f"notebook.{_digest(node.node_id)[:32]}",
            revision=1,
        )
    return _AnalyticsTableIdentity(output_id=recipe_id, revision=revision)


def _output_contract(
    identity: _AnalyticsTableIdentity,
    *,
    row_model: type[BaseModel] | None,
    control_adapter: TypeAdapter[object] | None,
) -> _OutputContractIdentity:
    """Describe one table or modeled-JSON compatibility boundary."""
    if row_model is not None:
        return _OutputContractIdentity(
            name="value",
            output_id=identity.output_id,
            revision=identity.revision,
            schema_digest=_logical_schema_digest(_logical_schema(row_model)),
            codec_id=_TableArtifactCodec.codec_id,
            codec_version=_TableArtifactCodec.codec_version,
        )
    adapter = _require_control_adapter(control_adapter)
    return _OutputContractIdentity(
        name="value",
        output_id=identity.output_id,
        revision=identity.revision,
        schema_digest=_json_schema_digest(adapter),
        codec_id=_JsonArtifactCodec.codec_id,
        codec_version=_JsonArtifactCodec.codec_version,
    )


def _control_adapter(
    node: _CompiledNode,
    results: Mapping[str, _NodeResult],
) -> TypeAdapter[object]:
    """Resolve a concrete modeled-JSON contract for a non-tabular step."""
    if node.kind != "step" or not isinstance(node.recipe, StepRecipe):
        raise CFBDRecipeCompilationError(
            "Only steps may produce modeled-JSON control values"
        )
    hints = get_type_hints(node.recipe._function, include_extras=True)
    return_type = hints["return"]
    declared = node.declaration.output_type
    if declared is not None:
        if return_type is not declared:
            raise CFBDRecipeCompilationError(
                "Control step return annotation and declared output differ"
            )
        return cast(TypeAdapter[object], TypeAdapter(declared))
    if isinstance(return_type, TypeVar):
        return _resolve_typevar_control(node, results, hints, return_type)
    try:
        return cast(TypeAdapter[object], TypeAdapter(return_type))
    except TypeError as exc:
        raise CFBDRecipeCompilationError(
            "Control step requires a concrete Pydantic-compatible return contract"
        ) from exc


def _resolve_typevar_control(
    node: _CompiledNode,
    results: Mapping[str, _NodeResult],
    hints: Mapping[str, object],
    return_type: TypeVar,
) -> TypeAdapter[object]:
    """Resolve a generic control output from one matching table input."""
    for name, annotation in hints.items():
        arguments = get_args(annotation)
        if (
            name == "return"
            or get_origin(annotation) is not list
            or len(arguments) != 1
            or arguments[0] is not return_type
        ):
            continue
        argument = node.arguments.get(name)
        node_id = getattr(argument.value, "node_id", None) if argument else None
        upstream = results.get(node_id) if isinstance(node_id, str) else None
        if upstream is not None and upstream.row_model is not None:
            return cast(TypeAdapter[object], TypeAdapter(upstream.row_model))
    raise CFBDRecipeCompilationError(
        "Generic control step output cannot be resolved from its table input"
    )


def _require_control_adapter(
    adapter: TypeAdapter[object] | None,
) -> TypeAdapter[object]:
    if adapter is None:
        raise CFBDRecipeCompilationError("Control output contract is unavailable")
    return adapter


def _upstream_identities(
    node: _CompiledNode,
    results: Mapping[str, _NodeResult],
) -> tuple[_UpstreamArtifactIdentity, ...]:
    return tuple(
        _UpstreamArtifactIdentity(
            dependency=dependency,
            output_name="value",
            content_digest=results[dependency].artifact.content_digest,
        )
        for dependency in node.dependencies
    )


def _semantic_parameters(
    node: _CompiledNode,
    resolved: Mapping[str, object],
) -> dict[str, object]:
    """Retain literals and binding shape without hashing upstream row values."""
    semantic: dict[str, object] = {}
    for name, argument in node.arguments.items():
        if argument.kind == "literal":
            semantic[name] = resolved[name]
            continue
        if argument.kind == "node":
            node_id = getattr(argument.value, "node_id", None)
            semantic[name] = {
                "upstream_index": node.dependencies.index(node_id),
            }
            continue
        if argument.kind == "structure":
            semantic[name] = _structured_semantics(
                argument.value,
                node.dependencies,
            )
            continue
        scalar = cast(_ValueRef, argument.value)
        reference = scalar.path
        expected_type = scalar.expected_type
        if not isinstance(reference, tuple) or not isinstance(expected_type, type):
            raise CFBDRecipeCompilationError("Scalar binding metadata is invalid")
        semantic[name] = {
            "upstream_index": node.dependencies.index(scalar.node_id),
            "path": reference,
            "type": f"{expected_type.__module__}:{expected_type.__qualname__}",
        }
    return semantic


def _structured_semantics(
    value: object,
    dependencies: tuple[str, ...],
) -> object:
    """Represent structured references without hashing resolved row values."""
    if isinstance(value, _NodeRef):
        return {"upstream_index": dependencies.index(value.node_id)}
    if isinstance(value, _ValueRef):
        return {
            "upstream_index": dependencies.index(value.node_id),
            "path": value.path,
            "type": f"{value.expected_type.__module__}:{value.expected_type.__qualname__}",
        }
    if isinstance(value, Mapping):
        return {
            key: _structured_semantics(item, dependencies)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_structured_semantics(item, dependencies) for item in value]
    if isinstance(value, tuple):
        return tuple(_structured_semantics(item, dependencies) for item in value)
    return value


def _validate_dataset_quality(
    node: _CompiledNode,
    rows: Sequence[BaseModel],
) -> None:
    """Validate declared uniqueness and preexisting deterministic ordering."""
    keys = node.declaration.keys
    if keys:
        seen: set[tuple[object, ...]] = set()
        for row in rows:
            key = tuple(getattr(row, field) for field in keys)
            if any(value is None for value in key):
                raise ValueError("Dataset candidate keys cannot contain nulls")
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ValueError("Dataset candidate keys must be hashable") from exc
            if duplicate:
                raise ValueError("Dataset candidate keys are not unique")
    order_by = node.declaration.order_by
    if order_by:
        order = [tuple(getattr(row, field) for field in order_by) for row in rows]
        try:
            if order != sorted(order):
                raise ValueError("Dataset rows violate declared deterministic order")
        except TypeError as exc:
            raise ValueError(
                "Dataset ordering fields are not mutually comparable"
            ) from exc


def _dataset_contract(node: _CompiledNode) -> _DatasetContractEvidence | None:
    """Project one dataset declaration into stable artifact semantics."""
    if node.kind != "dataset":
        return None
    grain = node.declaration.grain
    if grain is None:
        raise CFBDRecipeCompilationError("Dataset grain is unavailable")
    return _DatasetContractEvidence(
        grain=grain,
        keys=node.declaration.keys,
        order_by=node.declaration.order_by,
        partition_by=node.declaration.partition_by,
        event_time=node.declaration.event_time,
    )


def _row_list_adapter(
    row_model: type[BaseModel],
) -> TypeAdapter[list[BaseModel]]:
    """Build a typed list adapter from a runtime-declared row model."""
    annotation = types.GenericAlias(list, row_model)
    return cast(TypeAdapter[list[BaseModel]], TypeAdapter(annotation))


__all__: tuple[str, ...] = ()
