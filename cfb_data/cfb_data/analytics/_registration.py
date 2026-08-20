"""Stage automatic recipe registration and transactional provider imports."""

from __future__ import annotations

import sys
import weakref
from contextvars import ContextVar, Token
from dataclasses import dataclass
from threading import RLock

_LOCK = RLock()
_STAGING: ContextVar[_RegistrationStage | None] = ContextVar(
    "cfb_data_recipe_registration_stage", default=None
)


@dataclass(frozen=True, slots=True)
class _CandidateReference:
    """Retain one weak candidate and whether a module must own its name."""

    reference: weakref.ReferenceType[object]
    require_module_binding: bool


_CANDIDATES: list[_CandidateReference] = []
_QUARANTINED_ROOTS: set[str] = set()


@dataclass(slots=True)
class _RegistrationStage:
    """Collect candidates imported beneath one claimed provider root."""

    package_root: str
    candidates: list[object]


def _publish_candidate(recipe: object, *, require_module_binding: bool = True) -> None:
    """Stage or record a decorated object without creating a lookup catalog."""
    module = getattr(recipe, "__module__", "")
    with _LOCK:
        stage = _STAGING.get()
        if stage is not None and _is_within(module, stage.package_root):
            stage.candidates.append(recipe)
            return
        if any(_is_within(module, root) for root in _QUARANTINED_ROOTS):
            return
        _CANDIDATES.append(
            _CandidateReference(
                reference=weakref.ref(recipe),
                require_module_binding=require_module_binding,
            )
        )


def _ordinary_candidates() -> tuple[object, ...]:
    """Return stable objects still bound by fully initialized modules."""
    with _LOCK:
        live: list[object] = []
        retained: list[_CandidateReference] = []
        for registered in _CANDIDATES:
            candidate = registered.reference()
            if candidate is None:
                continue
            retained.append(registered)
            module_name = getattr(candidate, "__module__", "")
            if any(_is_within(module_name, root) for root in _QUARANTINED_ROOTS):
                continue
            module = sys.modules.get(module_name)
            if registered.require_module_binding and (
                module is None or not _is_bound(candidate, module)
            ):
                continue
            live.append(candidate)
        _CANDIDATES[:] = retained
        return tuple(live)


def _begin_stage(
    package_root: str,
) -> tuple[_RegistrationStage, Token[_RegistrationStage | None]]:
    """Begin one provider stage while the caller owns the registration lock."""
    stage = _RegistrationStage(package_root=package_root, candidates=[])
    token = _STAGING.set(stage)
    _QUARANTINED_ROOTS.add(package_root)
    return stage, token


def _end_stage(
    token: Token[_RegistrationStage | None], *, package_root: str, committed: bool
) -> None:
    """Close one provider stage and retain quarantine unless it committed."""
    _STAGING.reset(token)
    if committed:
        _QUARANTINED_ROOTS.discard(package_root)


def _registration_lock() -> RLock:
    """Return the process-wide lock shared by registration and discovery."""
    return _LOCK


def _is_bound(candidate: object, module: object) -> bool:
    qualified_name = getattr(candidate, "__qualname__", "")
    if not qualified_name or "<locals>" in qualified_name:
        return False
    current = module
    for component in qualified_name.split("."):
        current = getattr(current, component, None)
        if current is None:
            return False
    return current is candidate


def _is_within(module: str, package_root: str) -> bool:
    return module == package_root or module.startswith(f"{package_root}.")
