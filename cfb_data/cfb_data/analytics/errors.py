"""Define safe failures raised by modular analytics recipes."""

from __future__ import annotations

from cfb_data.errors import CFBDError


class CFBDAnalyticsError(CFBDError):
    """Report a failure owned by the analytics layer."""


class CFBDRecipeConfigurationError(CFBDAnalyticsError, ValueError):
    """Report an invalid recipe declaration."""


class CFBDRecipeUsageError(CFBDAnalyticsError, RuntimeError):
    """Report a recipe call made outside its supported context."""


class CFBDRecipeParameterError(CFBDAnalyticsError, ValueError):
    """Report analytical parameters that violate a recipe signature."""


class CFBDRecipeDiscoveryError(CFBDAnalyticsError):
    """Report a provider discovery or stable-identity conflict."""


class CFBDRecipeCompilationError(CFBDAnalyticsError):
    """Report a recipe graph that cannot be compiled safely."""


class CFBDArtifactError(CFBDAnalyticsError):
    """Report a validated analytics-artifact failure."""


class CFBDArtifactCodecError(CFBDArtifactError):
    """Report content that a configured artifact codec cannot encode."""

    codec_id: str
    category: str

    def __init__(self, *, codec_id: str, category: str) -> None:
        """Initialize a safe codec failure."""
        self.codec_id = codec_id
        self.category = category
        super().__init__(f"Artifact codec {codec_id} rejected content ({category})")


class CFBDArtifactCorruptionError(CFBDArtifactError):
    """Report a durable artifact that fails closed validation."""

    content_digest: str | None
    category: str

    def __init__(self, *, content_digest: str | None, category: str) -> None:
        """Initialize a safe corruption failure."""
        self.content_digest = content_digest
        self.category = category
        object_id = content_digest or "unknown"
        super().__init__(f"Artifact {object_id} is invalid ({category})")


class CFBDRunError(CFBDAnalyticsError):
    """Report a safely identified analytics execution failure."""

    run_id: str
    node_id: str
    category: str

    def __init__(self, *, run_id: str, node_id: str, category: str) -> None:
        """Initialize a redacted run failure.

        :param run_id: Safe analytics run identifier.
        :param node_id: Stable compiled node identifier.
        :param category: Bounded failure category.
        """
        self.run_id = run_id
        self.node_id = node_id
        self.category = category
        super().__init__(f"Analytics run {run_id} failed at {node_id} ({category})")


__all__ = [
    "CFBDAnalyticsError",
    "CFBDArtifactCodecError",
    "CFBDArtifactCorruptionError",
    "CFBDArtifactError",
    "CFBDRecipeCompilationError",
    "CFBDRecipeConfigurationError",
    "CFBDRecipeDiscoveryError",
    "CFBDRecipeParameterError",
    "CFBDRecipeUsageError",
    "CFBDRunError",
]
