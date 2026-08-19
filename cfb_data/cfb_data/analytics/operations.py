"""Provide explicit backend-neutral cleaning and nesting operations."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Protocol, cast

from cfb_data.errors import CFBDAnalyticsError


class ExplodeMode(StrEnum):
    """Control whether null and empty lists preserve an outer row."""

    inner = "inner"
    outer = "outer"


class JoinCardinality(StrEnum):
    """Declare expected relational join cardinality."""

    one_to_one = "one_to_one"
    one_to_many = "one_to_many"
    many_to_one = "many_to_one"
    many_to_many = "many_to_many"


class UnmatchedPolicy(StrEnum):
    """Control unmatched input rows in an explicit join."""

    error = "error"
    keep = "keep"
    drop = "drop"


def nested_value(record: Mapping[str, object], path: Sequence[str]) -> object:
    """Return a value reached by explicit structured path tokens.

    :param record: Source mapping.
    :param path: Non-empty ordered mapping keys.
    :return: Nested value, including ``None``.
    :raises CFBDAnalyticsError: If a path segment is absent or non-mapping.
    """
    if not path:
        raise CFBDAnalyticsError("Nested paths must contain at least one token")
    value: object = record
    for token in path:
        if not isinstance(value, Mapping) or token not in value:
            raise CFBDAnalyticsError("Nested path does not exist")
        value = value[token]
    return value


def flatten_struct(
    record: Mapping[str, object],
    *,
    path: Sequence[str],
    prefix: str = "",
) -> dict[str, object]:
    """Flatten one nested mapping while failing on column collisions.

    :param record: Source record.
    :param path: Structured path to the mapping to flatten.
    :param prefix: Optional prefix added to flattened field names.
    :return: New record with the source struct replaced by scalar fields.
    :raises CFBDAnalyticsError: If the value is not a mapping or collides.
    """
    nested = nested_value(record, path)
    if nested is None:
        nested_mapping: Mapping[str, object] = {}
    elif isinstance(nested, Mapping):
        nested_mapping = nested
    else:
        raise CFBDAnalyticsError("Only mapping values can be flattened")
    output = dict(record)
    if len(path) == 1:
        output.pop(path[0], None)
    for key, value in nested_mapping.items():
        if not isinstance(key, str):
            raise CFBDAnalyticsError("Flattened mapping keys must be strings")
        target = f"{prefix}{key}"
        if target in output:
            raise CFBDAnalyticsError("Flattening would overwrite a column")
        output[target] = value
    return output


def explode_list(
    records: Iterable[Mapping[str, object]],
    *,
    path: Sequence[str],
    output_field: str,
    ordinal_field: str,
    mode: ExplodeMode,
) -> list[dict[str, object]]:
    """Explode exactly one list with explicit null and empty behavior.

    :param records: Source records in deterministic order.
    :param path: Structured path to one list or nullable list.
    :param output_field: Field receiving each list element.
    :param ordinal_field: Field receiving a zero-based element ordinal.
    :param mode: Drop or preserve null/empty list rows.
    :return: Exploded rows preserving source and element order.
    :raises CFBDAnalyticsError: If a source value is not a list or collides.
    """
    output: list[dict[str, object]] = []
    for record in records:
        if output_field in record or ordinal_field in record:
            raise CFBDAnalyticsError("Explode output fields collide with input")
        value = nested_value(record, path)
        if value is None or value == []:
            if mode is ExplodeMode.outer:
                row = dict(record)
                row[output_field] = None
                row[ordinal_field] = None
                output.append(row)
            continue
        if not isinstance(value, list):
            raise CFBDAnalyticsError("Explode input must be a list or null")
        for ordinal, item in enumerate(value):
            row = dict(record)
            row[output_field] = item
            row[ordinal_field] = ordinal
            output.append(row)
    return output


def join_records(
    left: Sequence[Mapping[str, object]],
    right: Sequence[Mapping[str, object]],
    *,
    keys: Sequence[str],
    cardinality: JoinCardinality,
    unmatched: UnmatchedPolicy = UnmatchedPolicy.error,
    right_prefix: str = "right_",
) -> list[dict[str, object]]:
    """Join records with explicit cardinality, collision, and unmatched policy."""
    if not keys:
        raise CFBDAnalyticsError("Joins require explicit keys")
    left_counts = _key_counts(left, keys)
    right_counts = _key_counts(right, keys)
    if cardinality in {JoinCardinality.one_to_one, JoinCardinality.one_to_many}:
        _require_unique(left_counts, "left")
    if cardinality in {JoinCardinality.one_to_one, JoinCardinality.many_to_one}:
        _require_unique(right_counts, "right")
    right_index: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
    for row in right:
        right_index.setdefault(_record_key(row, keys), []).append(row)

    result: list[dict[str, object]] = []
    matched_right: set[tuple[object, ...]] = set()
    for left_row in left:
        key = _record_key(left_row, keys)
        matches = right_index.get(key, [])
        if not matches:
            if unmatched is UnmatchedPolicy.error:
                raise CFBDAnalyticsError("Join has unmatched left rows")
            if unmatched is UnmatchedPolicy.keep:
                result.append(dict(left_row))
            continue
        matched_right.add(key)
        for right_row in matches:
            merged = dict(left_row)
            for name, value in right_row.items():
                if name in keys:
                    continue
                target = name if name not in merged else f"{right_prefix}{name}"
                if target in merged:
                    raise CFBDAnalyticsError("Join column collision is ambiguous")
                merged[target] = value
            result.append(merged)
    if unmatched is UnmatchedPolicy.error and set(right_index).difference(
        matched_right
    ):
        raise CFBDAnalyticsError("Join has unmatched right rows")
    return result


def deduplicate_records(
    records: Sequence[Mapping[str, object]],
    *,
    keys: Sequence[str],
    winner_order: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Reject duplicates or select an explicit deterministic winner.

    :param records: Source rows.
    :param keys: Candidate key fields.
    :param winner_order: Sort fields selecting the final row, or ``None`` to fail.
    :return: Unique rows in first-key appearance order.
    """
    grouped: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
    order: list[tuple[object, ...]] = []
    for row in records:
        key = _record_key(row, keys)
        if key not in grouped:
            order.append(key)
        grouped.setdefault(key, []).append(row)
    output: list[dict[str, object]] = []
    for key in order:
        candidates = grouped[key]
        if len(candidates) == 1:
            output.append(dict(candidates[0]))
            continue
        if winner_order is None:
            raise CFBDAnalyticsError("Duplicate candidate keys require a winner policy")
        selected = sorted(
            candidates,
            key=lambda row: tuple(_sortable(row.get(name)) for name in winner_order),
        )[-1]
        output.append(dict(selected))
    return output


def normalize_text(value: str, *, casefold: bool = False) -> str:
    """Normalize Unicode and whitespace without silently changing case."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    return normalized.casefold() if casefold else normalized


def replace_sentinels(
    value: object, *, sentinels: Sequence[object], replacement: object = None
) -> object:
    """Replace only explicitly declared sentinel values."""
    return replacement if value in sentinels else value


def require_finite(value: float | None) -> float | None:
    """Reject non-finite numeric values without treating them as missing."""
    if value is not None and not math.isfinite(value):
        raise CFBDAnalyticsError("Non-finite numeric value is not allowed")
    return value


def portable_select(frame: object, columns: Sequence[str]) -> object:
    """Select ordered columns through Narwhals stable v2.

    The third-party boundary remains typed as ``object``; callers must validate
    the returned native frame against an explicit table contract.
    """
    import narwhals.stable.v2 as nw

    converted = nw.from_native(frame, eager_only=True, pass_through=True)
    if not hasattr(converted, "select") or not hasattr(converted, "to_native"):
        raise CFBDAnalyticsError("Value is not a supported eager DataFrame")
    wrapped = cast(_NarwhalsFrame, converted)
    selected = wrapped.select(*columns)
    return selected.to_native()


class _NarwhalsFrame(Protocol):
    """Describe only the stable Narwhals methods used by this module."""

    def select(self, *columns: str) -> _NarwhalsFrame:
        """Return selected columns in declared order."""

    def to_native(self) -> object:
        """Return the backend-native eager frame."""


def _key_counts(
    records: Sequence[Mapping[str, object]], keys: Sequence[str]
) -> dict[tuple[object, ...], int]:
    counts: dict[tuple[object, ...], int] = {}
    for row in records:
        key = _record_key(row, keys)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _require_unique(counts: Mapping[tuple[object, ...], int], side: str) -> None:
    if any(count > 1 for count in counts.values()):
        raise CFBDAnalyticsError(f"Join {side} side violates declared uniqueness")


def _record_key(
    record: Mapping[str, object], keys: Sequence[str]
) -> tuple[object, ...]:
    try:
        values = tuple(record[key] for key in keys)
    except KeyError as exc:
        raise CFBDAnalyticsError("Key field is missing from a record") from exc
    if any(value is None for value in values):
        raise CFBDAnalyticsError("Null join and candidate-key values are not allowed")
    try:
        hash(values)
    except TypeError as exc:
        raise CFBDAnalyticsError("Join keys must contain hashable values") from exc
    return values


def _sortable(value: object) -> tuple[str, str]:
    return (type(value).__name__, repr(value))


__all__ = [
    "deduplicate_records",
    "explode_list",
    "ExplodeMode",
    "flatten_struct",
    "JoinCardinality",
    "join_records",
    "nested_value",
    "normalize_text",
    "portable_select",
    "replace_sentinels",
    "require_finite",
    "UnmatchedPolicy",
]
