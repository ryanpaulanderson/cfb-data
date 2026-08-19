"""Discover immutable snapshots of directly imported and installed recipes."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import pkgutil
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from types import MappingProxyType, ModuleType

from ._declarations import RecipeKind, _RecipeDeclaration
from ._registration import (
    _begin_stage,
    _end_stage,
    _ordinary_candidates,
    _registration_lock,
)
from .config import AnalyticsConfig, RecipeProviderTrust
from .errors import CFBDRecipeDiscoveryError

type _RecipeKey = tuple[RecipeKind, str, int]


@dataclass(frozen=True, slots=True)
class RecipeSnapshot:
    """Freeze exact recipe resolution for one plan or YAML compilation."""

    _recipes: Mapping[_RecipeKey, object]
    fingerprint: str

    @property
    def count(self) -> int:
        """Return the number of exact stable recipe boundaries."""
        return len(self._recipes)

    def _resolve(self, *, kind: RecipeKind, recipe_id: str, revision: int) -> object:
        try:
            return self._recipes[(kind, recipe_id, revision)]
        except KeyError as exc:
            raise CFBDRecipeDiscoveryError(
                f"No discovered {kind} recipe matches {recipe_id}@{revision}"
            ) from exc


def discover_recipes(config: AnalyticsConfig | None = None) -> RecipeSnapshot:
    """Return one transactional immutable snapshot of trusted recipes.

    :param config: Lazy analytics and exact provider-trust configuration.
    :return: Frozen exact recipe-resolution snapshot.
    :raises CFBDRecipeDiscoveryError: If a provider or recipe conflicts.
    """
    selected = config or AnalyticsConfig()
    with _registration_lock():
        candidates = list(_ordinary_candidates())
        if selected.discover_installed:
            for entry_point in _selected_entry_points(selected):
                candidates.extend(_discover_provider(entry_point))
        resolved = _resolve_candidates(candidates)
    return RecipeSnapshot(MappingProxyType(resolved), _snapshot_fingerprint(resolved))


def _selected_entry_points(config: AnalyticsConfig) -> tuple[EntryPoint, ...]:
    available = entry_points(group="cfb_data.recipes")
    selected: list[EntryPoint] = []
    for candidate in available:
        identity = _entry_point_identity(candidate)
        is_official = (
            identity.distribution == "cfb-data"
            and identity.entry_point == "official"
            and identity.target == "cfb_data_recipes"
        )
        if is_official or any(
            _matches(identity, allowed) for allowed in config.trusted_providers
        ):
            selected.append(candidate)
    selected.sort(key=_entry_point_sort_key)
    return tuple(selected)


def _discover_provider(entry_point: EntryPoint) -> tuple[object, ...]:
    package_root = entry_point.value.split(":", maxsplit=1)[0]
    stage, token = _begin_stage(package_root)
    committed = False
    try:
        root = entry_point.load()
        if not isinstance(root, ModuleType) or root.__name__ != package_root:
            raise CFBDRecipeDiscoveryError(
                "Recipe provider entry points must load one package root"
            )
        locations = tuple(getattr(root, "__path__", ()))
        if len(locations) != 1:
            raise CFBDRecipeDiscoveryError(
                "Recipe providers must be ordinary single-location packages"
            )
        names = sorted(
            module.name
            for module in pkgutil.walk_packages(locations, prefix=f"{package_root}.")
        )
        if len(names) > 1_000:
            raise CFBDRecipeDiscoveryError(
                "Recipe provider exceeds the 1,000-module discovery limit"
            )
        modules = [root]
        for name in names:
            modules.append(importlib.import_module(name))
        for module in modules:
            _restage_module(module, stage.candidates)
        candidates = tuple(_deduplicate_objects(stage.candidates))
        _resolve_candidates(candidates)
        committed = True
        return candidates
    except CFBDRecipeDiscoveryError:
        raise
    except BaseException as exc:
        raise CFBDRecipeDiscoveryError(
            f"Recipe provider {entry_point.name!r} failed transactional discovery"
        ) from exc
    finally:
        _end_stage(token, package_root=package_root, committed=committed)


def _restage_module(module: ModuleType, destination: list[object]) -> None:
    for candidate in vars(module).values():
        declaration = getattr(candidate, "_declaration", None)
        if (
            isinstance(declaration, _RecipeDeclaration)
            and candidate.__module__ == module.__name__
        ):
            destination.append(candidate)


def _resolve_candidates(
    candidates: list[object] | tuple[object, ...],
) -> dict[_RecipeKey, object]:
    resolved: dict[_RecipeKey, object] = {}
    diagnostics: dict[_RecipeKey, tuple[str, str, str]] = {}
    for candidate in candidates:
        declaration = getattr(candidate, "_declaration", None)
        if not isinstance(declaration, _RecipeDeclaration) or not declaration.durable:
            continue
        if declaration.recipe_id is None or declaration.revision is None:
            raise AssertionError("Durable declarations must have complete identity")
        key = (declaration.kind, declaration.recipe_id, declaration.revision)
        diagnostic = _diagnostic_identity(candidate, declaration)
        previous = resolved.get(key)
        if previous is None:
            resolved[key] = candidate
            diagnostics[key] = diagnostic
            continue
        if previous is candidate or diagnostics[key] == diagnostic:
            continue
        raise CFBDRecipeDiscoveryError(
            f"Conflicting recipe declaration for {key[0]} {key[1]}@{key[2]}"
        )
    return dict(sorted(resolved.items()))


def _diagnostic_identity(
    candidate: object, declaration: _RecipeDeclaration
) -> tuple[str, str, str]:
    module = getattr(candidate, "__module__", "")
    qualified = getattr(candidate, "__qualname__", "")
    wrapped = getattr(candidate, "__wrapped__", candidate)
    if not callable(wrapped) or not callable(candidate):
        raise CFBDRecipeDiscoveryError("Registered recipe candidate is not callable")
    try:
        source = inspect.getsource(wrapped)
    except (OSError, TypeError):
        source = repr(inspect.signature(candidate))
    declaration_text = repr(declaration)
    digest = hashlib.sha256(f"{declaration_text}\0{source}".encode()).hexdigest()
    return module, qualified, digest


def _snapshot_fingerprint(recipes: Mapping[_RecipeKey, object]) -> str:
    payload = "\n".join(
        f"{kind}:{recipe_id}:{revision}:{_recipe_diagnostic_digest(recipe)}"
        for (kind, recipe_id, revision), recipe in recipes.items()
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _recipe_diagnostic_digest(recipe: object) -> str:
    declaration = getattr(recipe, "_declaration", None)
    if not isinstance(declaration, _RecipeDeclaration):
        raise CFBDRecipeDiscoveryError("Snapshot contains an invalid recipe candidate")
    return _diagnostic_identity(recipe, declaration)[2]


def _entry_point_identity(entry_point: EntryPoint) -> RecipeProviderTrust:
    distribution = entry_point.dist
    if distribution is None:
        raise CFBDRecipeDiscoveryError("Recipe entry point has no owning distribution")
    return RecipeProviderTrust(
        distribution=_normalize_distribution(distribution.name),
        entry_point=entry_point.name,
        target=entry_point.value,
        version=distribution.version,
    )


def _matches(actual: RecipeProviderTrust, allowed: RecipeProviderTrust) -> bool:
    return (
        actual.distribution == _normalize_distribution(allowed.distribution)
        and actual.entry_point == allowed.entry_point
        and actual.target == allowed.target
        and (allowed.version is None or actual.version == allowed.version)
    )


def _entry_point_sort_key(entry_point: EntryPoint) -> tuple[str, str, str]:
    identity = _entry_point_identity(entry_point)
    return identity.distribution, identity.entry_point, identity.target


def _normalize_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _deduplicate_objects(candidates: list[object]) -> Iterator[object]:
    seen: set[int] = set()
    for candidate in candidates:
        identity = id(candidate)
        if identity not in seen:
            seen.add(identity)
            yield candidate


__all__ = ["RecipeSnapshot", "discover_recipes"]
