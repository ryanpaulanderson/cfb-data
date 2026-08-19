"""Configure lazy analytics persistence and trusted recipe discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observability import AnalyticsObserver


@dataclass(frozen=True, slots=True)
class RecipeProviderTrust:
    """Identify one exact installed recipe-provider entry point."""

    distribution: str
    entry_point: str
    target: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    """Configure analytics without opening files or providers.

    :param root: Explicit durable analytics root, or ``None`` for platform data.
    :param discover_installed: Whether discovery may import trusted entry points.
    :param trusted_providers: Exact additional provider identities to allow.
    """

    root: Path | None = None
    discover_installed: bool = True
    trusted_providers: tuple[RecipeProviderTrust, ...] = ()
    observer: AnalyticsObserver | None = None


__all__ = ["AnalyticsConfig", "RecipeProviderTrust"]
