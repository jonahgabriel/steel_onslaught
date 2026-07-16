"""Reusable deep-immutability adapters for validated JSON object fields."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import AfterValidator, PlainSerializer

type JSONScalar = str | int | float | bool | None
type FrozenJSONValue = JSONScalar | tuple[FrozenJSONValue, ...] | Mapping[str, FrozenJSONValue]
type MutableJSONValue = JSONScalar | list[MutableJSONValue] | dict[str, MutableJSONValue]


def _freeze_json_value(value: object) -> FrozenJSONValue:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJSONValue] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError(f"JSON object keys must be strings, got {type(key).__name__}")
            frozen[key] = _freeze_json_value(nested)
        return MappingProxyType(frozen)
    if isinstance(value, list | tuple):
        return tuple(_freeze_json_value(item) for item in value)
    raise ValueError(f"payload value is not JSON-compatible: {type(value).__name__}")


def freeze_json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy and recursively freeze one validated JSON object."""
    frozen = _freeze_json_value(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - annotation guarantees mapping
        raise TypeError("expected a JSON object")
    return frozen


def _thaw_json_value(value: FrozenJSONValue) -> MutableJSONValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    return value


def thaw_json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a plain JSON-serializable copy without exposing mutable runtime state."""
    return {key: _thaw_json_value(nested) for key, nested in freeze_json_mapping(value).items()}


def freeze_mapping[T](value: Mapping[str, T]) -> Mapping[str, T]:
    """Copy and freeze a shallow mapping whose value type Pydantic validates."""
    return MappingProxyType(dict(value))


def thaw_mapping[T](value: Mapping[str, T]) -> dict[str, T]:
    """Return a serialization copy of a typed frozen mapping."""
    return dict(value)


type FrozenJSONMapping = Annotated[
    Mapping[str, Any],
    AfterValidator(freeze_json_mapping),
    PlainSerializer(thaw_json_mapping, return_type=dict[str, Any]),
]
type FrozenMapping[T] = Annotated[
    Mapping[str, T],
    AfterValidator(freeze_mapping),
    PlainSerializer(thaw_mapping, return_type=dict[str, Any]),
]


__all__ = [
    "FrozenJSONMapping",
    "FrozenMapping",
    "freeze_json_mapping",
    "freeze_mapping",
    "thaw_json_mapping",
    "thaw_mapping",
]
