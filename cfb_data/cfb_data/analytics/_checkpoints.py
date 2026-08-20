"""Compute per-boundary checkpoint identity and recovery scope."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from ._compiler import _digest
from ._graph import _CompiledNode

type _DataFrameBackend = Literal["pandas", "polars"]
type _SourceBehavior = Literal["preserve_snapshot", "normal_freshness", "refresh"]
type _CheckpointScope = Literal["none", "parent", "parent_then_global", "global"]

_PORTABLE_BACKENDS = frozenset({"pandas", "polars"})


@dataclass(frozen=True, slots=True)
class _OutputContractIdentity:
    """Describe compatibility-relevant identity for one named node output."""

    name: str
    output_id: str
    revision: int
    schema_digest: str
    codec_id: str
    codec_version: int


@dataclass(frozen=True, slots=True)
class _UpstreamArtifactIdentity:
    """Bind one ordered dependency output to immutable content."""

    dependency: str
    output_name: str
    content_digest: str


def _node_fingerprint(
    node: _CompiledNode,
    *,
    parameters: Mapping[str, object],
    upstream: Sequence[_UpstreamArtifactIdentity],
    outputs: Sequence[_OutputContractIdentity],
    backend: _DataFrameBackend,
    semantic_policy: Mapping[str, object] | None = None,
) -> str | None:
    """Return one Merkle-style durable compatibility fingerprint.

    :param node: Compiled decorated boundary.
    :param parameters: Fully resolved validated boundary parameters.
    :param upstream: Ordered immutable upstream output identities.
    :param outputs: Ordered output codec and schema contracts.
    :param backend: Selected presentation/custom-compute backend.
    :param semantic_policy: Value-affecting policy only, never executor controls.
    :return: Stable fingerprint, or ``None`` for an unversioned boundary.
    """
    declaration = node.declaration
    if not declaration.durable:
        return None
    backend_identity: str | None = None
    if declaration.supported_backends != _PORTABLE_BACKENDS:
        backend_identity = backend
    return _digest(
        {
            "engine_ir": 1,
            "kind": node.kind,
            "operation_id": declaration.recipe_id,
            "operation_revision": declaration.revision,
            "parameters": parameters,
            "semantic_policy": semantic_policy or {},
            "upstream": [
                {
                    "output": artifact.output_name,
                    "digest": artifact.content_digest,
                }
                for artifact in upstream
            ],
            "outputs": [
                {
                    "name": output.name,
                    "id": output.output_id,
                    "revision": output.revision,
                    "schema": output.schema_digest,
                    "codec": output.codec_id,
                    "codec_version": output.codec_version,
                }
                for output in outputs
            ],
            "backend": backend_identity,
        }
    )


def _checkpoint_scope(
    node: _CompiledNode,
    *,
    parent_run_id: str | None,
    source_behavior: _SourceBehavior,
    checkpoint_eligible: bool = True,
) -> _CheckpointScope:
    """Select reuse scope without allowing checkpoints to freeze API freshness."""
    if not node.declaration.durable or not checkpoint_eligible:
        return "none"
    if node.kind == "source":
        if parent_run_id is not None and source_behavior == "preserve_snapshot":
            return "parent"
        return "none"
    if not node.declaration.deterministic:
        return "parent" if parent_run_id is not None else "none"
    return "parent_then_global" if parent_run_id is not None else "global"


__all__: tuple[str, ...] = ()
