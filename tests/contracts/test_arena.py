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

    assert set(catalog.arenas) == {"foundry", "foundry_60", "open_field"}
    foundry = catalog.arenas["foundry"]
    snapshot = foundry.to_snapshot()
    assert snapshot.arena_id == "foundry"
    assert snapshot.size == 40
    assert snapshot.spawn_a.model_dump() == {"x": 3, "y": 3}
    assert snapshot.spawn_b.model_dump() == {"x": 36, "y": 36}
    assert snapshot.obstacles
    assert [(cell.x, cell.y) for cell in snapshot.obstacles] == sorted(foundry.obstacle_cells)
    assert snapshot.obstacle_cells == foundry.obstacle_cells


@pytest.mark.unit
def test_legacy_foundry_snapshot_round_trips_for_replay() -> None:
    """The 40x40 arena id remains stable for existing event ledgers."""
    legacy = load_match_contract_catalog(Path("contracts_data")).arenas["foundry"]
    snapshot = ModelSOCurrentLiveArenaSnapshot.model_validate(
        legacy.to_snapshot().model_dump(mode="json")
    )
    assert snapshot == legacy.to_snapshot()


@pytest.mark.unit
def test_foundry_60_layout_is_sparse_symmetric_and_spawn_safe() -> None:
    """The shipped Foundry data is an auditable 60x60 terrain contract.

    Rects remain obstacle cells under the current wall/blocking runtime. This
    test pins the authored data's scale and fairness without opting the engine
    into the deferred cover-penalty rules.
    """
    catalog = load_match_contract_catalog(Path("contracts_data"))
    arena = catalog.arenas["foundry_60"]
    cells = arena.obstacle_cells
    assert arena.size == 60
    assert (arena.spawn_a.x, arena.spawn_a.y) == (4, 4)
    assert (arena.spawn_b.x, arena.spawn_b.y) == (55, 55)
    assert arena.sudden_death_start_tick == 100
    assert max(abs(arena.spawn_b.x - arena.spawn_a.x), abs(arena.spawn_b.y - arena.spawn_a.y)) == 51
    assert 0.08 <= len(cells) / (arena.size * arena.size) <= 0.12
    assert all((y, x) in cells for x, y in cells)
    assert all((arena.size - 1 - x, arena.size - 1 - y) in cells for x, y in cells)
    for spawn in (arena.spawn_a, arena.spawn_b):
        assert all(max(abs(spawn.x - x), abs(spawn.y - y)) > 4 for x, y in cells)


@pytest.mark.unit
def test_foundry_60_rects_are_small_disconnected_clusters() -> None:
    """The map contains sparse 2-4-cell clusters rather than a wall corridor."""
    arena = load_match_contract_catalog(Path("contracts_data")).arenas["foundry_60"]
    cells = set(arena.obstacle_cells)
    seen: set[tuple[int, int]] = set()
    components: list[int] = []
    for start in cells:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        count = 0
        while stack:
            x, y = stack.pop()
            count += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if neighbor in cells and neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
        components.append(count)
    assert components
    assert min(components) >= 2
    assert max(components) <= 4


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
        "sudden_death_start_tick": None,
        "sudden_death_damage_base": 8,
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
