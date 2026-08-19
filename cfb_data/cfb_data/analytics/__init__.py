"""Author modular, composable, and durably executable analytics recipes."""

from ._recipes import (
    DatasetRecipe,
    SourceRecipe,
    StepRecipe,
    WorkflowRecipe,
    dataset,
    source,
    step,
    workflow,
)
from .config import AnalyticsConfig, RecipeProviderTrust
from .discovery import RecipeSnapshot, discover_recipes
from .errors import (
    CFBDAnalyticsError,
    CFBDRecipeCompilationError,
    CFBDRecipeConfigurationError,
    CFBDRecipeDiscoveryError,
    CFBDRecipeParameterError,
    CFBDRecipeUsageError,
    CFBDRunError,
)
from .operations import require_one, value
from .types import RecipeRef, SourceContext, ValueRef, WorkflowOutputs

__all__ = [
    "AnalyticsConfig",
    "CFBDAnalyticsError",
    "CFBDRecipeCompilationError",
    "CFBDRecipeConfigurationError",
    "CFBDRecipeDiscoveryError",
    "CFBDRecipeParameterError",
    "CFBDRecipeUsageError",
    "CFBDRunError",
    "DatasetRecipe",
    "RecipeRef",
    "RecipeProviderTrust",
    "RecipeSnapshot",
    "SourceContext",
    "SourceRecipe",
    "StepRecipe",
    "ValueRef",
    "WorkflowOutputs",
    "WorkflowRecipe",
    "dataset",
    "discover_recipes",
    "source",
    "step",
    "workflow",
    "require_one",
    "value",
]
