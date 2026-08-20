"""Test explicit backend-neutral nested logical-record operations."""

from __future__ import annotations

import pytest
from cfb_data.analytics import explode_list, flatten_struct, nested_value
from cfb_data.analytics.errors import CFBDTransformError


def test_nested_value_uses_tokens_without_dot_parsing() -> None:
    value = {"a.b": {"items": [{"score": 7}]}}

    assert (
        nested_value(
            value,
            path=("a.b", "items", 0, "score"),
            nulls="error",
        )
        == 7
    )


def test_nested_value_requires_explicit_null_policy() -> None:
    value = {"context": None}

    assert (
        nested_value(
            value,
            path=("context", "score"),
            nulls="return_null",
        )
        is None
    )
    with pytest.raises(CFBDTransformError, match="encountered null"):
        nested_value(value, path=("context", "score"), nulls="error")


def test_struct_flatten_requires_exact_schema_and_preserves_order() -> None:
    records: list[dict[str, object]] = [
        {"id": 1, "clock": {"minutes": 12, "seconds": 34}},
        {"id": 2, "clock": None},
    ]

    result = flatten_struct(
        records,
        field="clock",
        fields=("minutes", "seconds"),
        prefix="clock_",
        retain_struct=False,
        null_struct="null_fields",
    )

    assert result.records == (
        {"id": 1, "clock_minutes": 12, "clock_seconds": 34},
        {"id": 2, "clock_minutes": None, "clock_seconds": None},
    )
    assert result.diagnostics.input_rows == 2
    assert result.diagnostics.output_rows == 2
    assert records[0] == {"id": 1, "clock": {"minutes": 12, "seconds": 34}}


def test_struct_flatten_fails_on_schema_drift_and_collisions() -> None:
    with pytest.raises(CFBDTransformError, match="explicit flatten schema"):
        flatten_struct(
            [{"clock": {"minutes": 1, "seconds": 2, "tenths": 3}}],
            field="clock",
            fields=("minutes", "seconds"),
            prefix="",
            retain_struct=False,
            null_struct="error",
        )
    with pytest.raises(CFBDTransformError, match="collide"):
        flatten_struct(
            [{"minutes": 9, "clock": {"minutes": 1}}],
            field="clock",
            fields=("minutes",),
            prefix="",
            retain_struct=False,
            null_struct="error",
        )


def test_inner_explosion_records_every_exclusion() -> None:
    records: list[dict[str, object]] = [
        {"id": 1, "items": ["a", None, "b"]},
        {"id": 2, "items": []},
        {"id": 3, "items": None},
    ]

    result = explode_list(
        records,
        field="items",
        mode="inner",
        null_list="drop",
        empty_list="drop",
        null_element="drop",
        ordinal_field="source_ordinal",
        ordinal_start=0,
    )

    assert result.records == (
        {"id": 1, "items": "a", "source_ordinal": 0},
        {"id": 1, "items": "b", "source_ordinal": 2},
    )
    assert result.diagnostics.excluded_source_rows == 2
    assert result.diagnostics.excluded_elements == 1


def test_outer_explosion_preserves_null_and_empty_source_rows() -> None:
    result = explode_list(
        [
            {"id": 1, "items": None},
            {"id": 2, "items": []},
            {"id": 3, "items": [None]},
        ],
        field="items",
        mode="outer",
        null_list="emit_null",
        empty_list="emit_null",
        null_element="keep",
        ordinal_field="ordinal",
        ordinal_start=1,
    )

    assert result.records == (
        {"id": 1, "items": None, "ordinal": None},
        {"id": 2, "items": None, "ordinal": None},
        {"id": 3, "items": None, "ordinal": 1},
    )
    assert result.diagnostics.excluded_source_rows == 0
    assert result.diagnostics.excluded_elements == 0


def test_inner_explosion_rejects_placeholder_policy() -> None:
    with pytest.raises(CFBDTransformError):
        explode_list(
            [{"items": []}],
            field="items",
            mode="inner",
            null_list="emit_null",
            empty_list="drop",
            null_element="keep",
            ordinal_field=None,
            ordinal_start=0,
        )


def test_outer_explosion_rejects_row_dropping_policy() -> None:
    with pytest.raises(CFBDTransformError):
        explode_list(
            [{"items": []}],
            field="items",
            mode="outer",
            null_list="drop",
            empty_list="emit_null",
            null_element="keep",
            ordinal_field=None,
            ordinal_start=0,
        )
    with pytest.raises(CFBDTransformError):
        explode_list(
            [{"items": [None]}],
            field="items",
            mode="outer",
            null_list="emit_null",
            empty_list="emit_null",
            null_element="drop",
            ordinal_field=None,
            ordinal_start=0,
        )


def test_explosion_fails_on_ordinal_collision_and_null_element_error() -> None:
    with pytest.raises(CFBDTransformError, match="collides"):
        explode_list(
            [{"items": [1], "ordinal": 9}],
            field="items",
            mode="inner",
            null_list="error",
            empty_list="error",
            null_element="error",
            ordinal_field="ordinal",
            ordinal_start=0,
        )
    with pytest.raises(CFBDTransformError, match="Null list element"):
        explode_list(
            [{"items": [None]}],
            field="items",
            mode="inner",
            null_list="error",
            empty_list="error",
            null_element="error",
            ordinal_field=None,
            ordinal_start=0,
        )
