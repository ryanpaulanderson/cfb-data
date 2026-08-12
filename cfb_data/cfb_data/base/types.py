"""Define and validate values crossing API serialization boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
JSONResponse: TypeAlias = JSONObject | list[JSONObject]
QueryValue: TypeAlias = str | int | float | bool
QueryParameters: TypeAlias = dict[str, QueryValue]


def json_value(value: object) -> JSONValue:
    """Validate and return a recursively JSON-compatible value.

    :param value: Untrusted value from a JSON decoder or serializer.
    :return: A value containing only JSON-compatible primitives and containers.
    :raises TypeError: If the value is not JSON-compatible or has non-string keys.
    """
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        result: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            result[key] = json_value(item)
        return result
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def json_response(value: object) -> JSONResponse:
    """Validate and return the supported top-level API response shape.

    :param value: Untrusted value returned by the HTTP JSON decoder.
    :return: A JSON object or a list of JSON objects.
    :raises TypeError: If the value is not a supported API response.
    """
    parsed = json_value(value)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        objects: list[JSONObject] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise TypeError("API response lists must contain only JSON objects")
            objects.append(item)
        return objects
    raise TypeError("API response must be a JSON object or a list of JSON objects")


def json_object(value: object) -> JSONObject:
    """Validate and return a JSON object.

    :param value: Untrusted value expected to contain a JSON object.
    :return: A recursively validated JSON object.
    :raises TypeError: If the value is not a JSON object.
    """
    parsed = json_value(value)
    if isinstance(parsed, dict):
        return parsed
    raise TypeError("Expected a JSON object")


def json_object_list(value: object) -> list[JSONObject]:
    """Validate and return a list of JSON objects.

    :param value: Untrusted value expected to contain JSON objects.
    :return: A recursively validated list of JSON objects.
    :raises TypeError: If the value is not a list of JSON objects.
    """
    parsed = json_response(value)
    if isinstance(parsed, list):
        return parsed
    raise TypeError("Expected a list of JSON objects")


def query_parameters(value: object) -> QueryParameters:
    """Validate and return URL query parameters.

    :param value: Serialized request-model data.
    :return: Query parameters containing scalar URL values.
    :raises TypeError: If a key or value cannot be represented in a query string.
    """
    if not isinstance(value, Mapping):
        raise TypeError("Query parameters must be a mapping")

    result: QueryParameters = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("Query parameter keys must be strings")
        if not isinstance(item, str | int | float | bool):
            raise TypeError(f"Unsupported query parameter type for {key!r}")
        result[key] = item
    return result
