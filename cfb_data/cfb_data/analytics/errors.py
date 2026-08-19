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
    "CFBDRecipeCompilationError",
    "CFBDRecipeConfigurationError",
    "CFBDRecipeDiscoveryError",
    "CFBDRecipeParameterError",
    "CFBDRecipeUsageError",
    "CFBDRunError",
]
