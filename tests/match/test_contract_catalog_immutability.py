"""Match contract catalog snapshots cannot be mutated after composition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from steel_onslaught.match.fold import MatchContractCatalog
from tests.runtime import runtime_dependencies


def _assign(mapping: Mapping[Any, Any], key: object, value: object) -> None:
    mapping[key] = value  # type: ignore[index]


def _assert_snapshot[K, V](exposed: Mapping[K, V], original: dict[K, V]) -> None:
    key = next(iter(original))
    value = original[key]
    original.clear()
    assert exposed[key] is value
    with pytest.raises(TypeError):
        _assign(exposed, key, value)


@pytest.mark.unit
def test_catalog_defensively_copies_and_freezes_every_exposed_index() -> None:
    source = runtime_dependencies().catalog
    arenas = dict(source.arenas)
    chassis = dict(source.chassis)
    boilers = dict(source.boilers)
    sensors = dict(source.sensors)
    weapons = dict(source.weapons)
    gizmos = dict(source.gizmos)
    transitions = dict(source.transitions)
    catalog = MatchContractCatalog(
        arenas=arenas,
        chassis=chassis,
        boilers=boilers,
        sensors=sensors,
        weapons=weapons,
        gizmos=gizmos,
        transitions=transitions,
    )

    _assert_snapshot(catalog.arenas, arenas)
    _assert_snapshot(catalog.chassis, chassis)
    _assert_snapshot(catalog.boilers, boilers)
    _assert_snapshot(catalog.sensors, sensors)
    _assert_snapshot(catalog.weapons, weapons)
    _assert_snapshot(catalog.gizmos, gizmos)
    _assert_snapshot(catalog.transitions, transitions)


@pytest.mark.unit
def test_catalog_values_and_derived_safety_index_are_immutable() -> None:
    source = runtime_dependencies().catalog
    gizmos = dict(source.gizmos)
    catalog = MatchContractCatalog(
        arenas=source.arenas,
        chassis=source.chassis,
        boilers=source.boilers,
        sensors=source.sensors,
        weapons=source.weapons,
        gizmos=gizmos,
        transitions=source.transitions,
    )
    safety_ids = catalog.safety_gizmo_ids
    gizmos.clear()

    assert catalog.safety_gizmo_ids == safety_ids
    assert safety_ids
    chassis = next(iter(catalog.chassis.values()))
    with pytest.raises(ValidationError):
        chassis.display_name = "forged"


@pytest.mark.unit
@pytest.mark.parametrize(
    "attribute",
    [
        "chassis",
        "arenas",
        "boilers",
        "sensors",
        "weapons",
        "gizmos",
        "transitions",
        "safety_gizmo_ids",
    ],
)
def test_catalog_attributes_cannot_be_reassigned(attribute: str) -> None:
    catalog = runtime_dependencies().catalog

    with pytest.raises(AttributeError):
        setattr(catalog, attribute, {})
