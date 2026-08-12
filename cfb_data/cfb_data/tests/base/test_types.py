"""Tests for external serialization boundary types."""

import pytest
from cfb_data.base.types import json_response, query_parameters


def test_json_response_validates_nested_values() -> None:
    """Return recursively validated JSON objects."""
    value = [{"game": {"id": 42}, "scores": [7, 14, None]}]

    assert json_response(value) == value


@pytest.mark.parametrize("value", [[1], {1: "invalid"}, {"value": object()}])
def test_json_response_rejects_unsupported_values(value: object) -> None:
    """Reject unsupported JSON shapes and values."""
    with pytest.raises(TypeError):
        json_response(value)


def test_query_parameters_accept_scalars() -> None:
    """Return scalar query parameters."""
    value = {"year": 2026, "team": "Georgia", "postseason": False}

    assert query_parameters(value) == value


def test_query_parameters_reject_nested_values() -> None:
    """Reject values that cannot be represented as scalar query parameters."""
    with pytest.raises(TypeError, match="Unsupported query parameter type"):
        query_parameters({"team": ["Georgia"]})
