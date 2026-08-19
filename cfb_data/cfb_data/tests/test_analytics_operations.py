"""Test explicit backend-neutral cleaning and nesting semantics."""

import pytest
from cfb_data.analytics.operations import (
    ExplodeMode,
    JoinCardinality,
    UnmatchedPolicy,
    explode_list,
    flatten_struct,
    join_records,
    nested_value,
)

from cfb_data import CFBDAnalyticsError


def test_nested_operations_preserve_outer_and_ordinal_semantics() -> None:
    """Distinguish null lists, empty lists, and nested null elements."""
    record = {"id": 1, "payload": {"items": [None, {"value": 2}]}}
    assert nested_value(record, ("payload", "items")) == [None, {"value": 2}]
    assert flatten_struct(
        {"id": 1, "payload": {"name": "x"}}, path=("payload",), prefix="p_"
    ) == {"id": 1, "p_name": "x"}
    exploded = explode_list(
        [record, {"id": 2, "payload": {"items": []}}],
        path=("payload", "items"),
        output_field="item",
        ordinal_field="ordinal",
        mode=ExplodeMode.outer,
    )
    assert exploded == [
        {
            "id": 1,
            "payload": {"items": [None, {"value": 2}]},
            "item": None,
            "ordinal": 0,
        },
        {
            "id": 1,
            "payload": {"items": [None, {"value": 2}]},
            "item": {"value": 2},
            "ordinal": 1,
        },
        {
            "id": 2,
            "payload": {"items": []},
            "item": None,
            "ordinal": None,
        },
    ]


def test_join_requires_declared_cardinality_and_unmatched_policy() -> None:
    """Reject hidden many-to-many and row-dropping behavior."""
    with pytest.raises(CFBDAnalyticsError, match="uniqueness"):
        join_records(
            [{"id": 1}, {"id": 1}],
            [{"id": 1, "value": "x"}],
            keys=("id",),
            cardinality=JoinCardinality.one_to_one,
            unmatched=UnmatchedPolicy.error,
        )
    with pytest.raises(CFBDAnalyticsError, match="unmatched"):
        join_records(
            [{"id": 1}],
            [{"id": 2}],
            keys=("id",),
            cardinality=JoinCardinality.one_to_one,
            unmatched=UnmatchedPolicy.error,
        )
