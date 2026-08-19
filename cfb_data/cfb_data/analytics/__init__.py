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
from .observability import (
    AnalyticsEvent,
    AnalyticsEventType,
    AnalyticsObserver,
    AnalyticsOutcome,
    AnalyticsStats,
    AnalyticsStatsSnapshot,
)
from .operations import require_one, value
from .planning import ExecutionPolicy, RecipeInspection, RecipePlan, RecipePlanNode
from .types import RecipeRef, SourceContext, ValueRef, WorkflowOutputs

__all__ = [
    "AnalyticsConfig",
    "AnalyticsEvent",
    "AnalyticsEventType",
    "AnalyticsObserver",
    "AnalyticsOutcome",
    "AnalyticsStats",
    "AnalyticsStatsSnapshot",
    "CFBDAnalyticsError",
    "CFBDRecipeCompilationError",
    "CFBDRecipeConfigurationError",
    "CFBDRecipeDiscoveryError",
    "CFBDRecipeParameterError",
    "CFBDRecipeUsageError",
    "CFBDRunError",
    "DatasetRecipe",
    "ExecutionPolicy",
    "RecipeRef",
    "RecipeProviderTrust",
    "RecipeInspection",
    "RecipePlan",
    "RecipePlanNode",
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
