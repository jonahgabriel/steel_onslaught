"""Closed arena contract and strict current-live snapshot proof."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.arena import (
    ModelSOArenaSpec,
    ModelSOCurrentLiveArenaSnapshot,
)
from steel_onslaught.match.composition import load_match_contract_catalog


@pytest.mark.unit
def test_shipped_arena_catalog_is_typed_and_snapshot_is_canonical() -> None:
    catalog = load_match_contract_catalog(Path("contracts_data"))

    assert set(catalog.arenas) == {"foundry", "open_field"}
    foundry = catalog.arenas["foundry"]
    snapshot = foundry.to_snapshot()
    assert snapshot.arena_id == "foundry"
    assert snapshot.size == 40
    assert snapshot.obstacles
    assert [(cell.x, cell.y) for cell in snapshot.obstacles] == sorted(foundry.obstacle_cells)
    assert snapshot.obstacle_cells == foundry.obstacle_cells


@pytest.mark.unit
@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"spawn_b": {"x": 0, "y": 0}}, "spawn points must be distinct"),
        ({"spawn_a": {"x": 8, "y": 0}}, "outside"),
        ({"obstacles": [{"x": 0, "y": 0}]}, "occupies an obstacle"),
        (
            {"obstacles": [{"x": 1, "y": 1}, {"x": 1, "y": 1}]},
            "duplicate explicit obstacles",
        ),
        ({"rects": [{"x0": 4, "y0": 4, "x1": 3, "y1": 5}]}, "x0 <= x1"),
    ],
)
def test_arena_spec_rejects_invalid_layout(
    update: dict[str, object],
    message: str,
) -> None:
    raw: dict[str, object] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.arena",
        "arena_id": "test_arena",
        "display_name": "Test arena",
        "size": 8,
        "spawn_a": {"x": 0, "y": 0},
        "spawn_b": {"x": 7, "y": 7},
        "obstacles": [],
        "rects": [],
    }
    with pytest.raises(ValidationError, match=message):
        ModelSOArenaSpec.model_validate({**raw, **update})


@pytest.mark.unit
def test_current_live_snapshot_is_closed_and_requires_every_field() -> None:
    raw = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.arena_snapshot",
        "arena_id": "open_field",
        "size": 40,
        "spawn_a": {"x": 5, "y": 5},
        "spawn_b": {"x": 35, "y": 35},
        "obstacles": [],
    }
    snapshot = ModelSOCurrentLiveArenaSnapshot.model_validate(raw)
    assert snapshot.model_fields_set == frozenset(ModelSOCurrentLiveArenaSnapshot.model_fields)
    for field in ModelSOCurrentLiveArenaSnapshot.model_fields:
        missing = dict(raw)
        del missing[field]
        with pytest.raises(ValidationError, match=field):
            ModelSOCurrentLiveArenaSnapshot.model_validate(missing)
    with pytest.raises(ValidationError, match="unexpected"):
        ModelSOCurrentLiveArenaSnapshot.model_validate({**raw, "unexpected": True})
