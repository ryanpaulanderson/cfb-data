"""Normalize provider values used by compact identity models."""

from enum import StrEnum


def positive_identity_id(value: object) -> int | None:
    """Return a positive non-boolean provider identity or ``None``.

    :param value: Validated provider value that may be an unresolved placeholder.
    :return: Positive identity value, or ``None`` for non-identity placeholders.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def game_identity_status(*, status: object, completed: object) -> str | None:
    """Return the explicitly established compact game status.

    :param status: Provider status value when the response exposes one.
    :param completed: Provider completion flag when available.
    :return: Explicit status, ``"completed"`` when proven, or otherwise ``None``.
    """
    if isinstance(status, StrEnum):
        return str(status)
    if isinstance(status, str) and status:
        return status
    return "completed" if completed is True else None
