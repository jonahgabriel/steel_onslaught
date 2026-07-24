"""Closed arena contract and strict current-live snapshot proof."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.arena import (
    ModelSOArenaSpec,
    ModelSOCurrentLiveArenaSnapshot,
    arena_contract_hash,
)
from steel_onslaught.match.composition import load_match_contract_catalog
from steel_onslaught.match.geometry import line_of_sight_clear


@pytest.mark.unit
def test_shipped_arena_catalog_is_typed_and_snapshot_is_canonical() -> None:
    catalog = load_match_contract_catalog(Path("contracts_data"))

    assert set(catalog.arenas) == {
        "foundry",
        "foundry_60",
        "foundry_60_asym_v1",
        "foundry_60_asym_v2",
        "open_field",
    }
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
def test_foundry_60_contract_bytes_are_untouched_by_phase_4() -> None:
    """Old replays stay valid: the historical arena file is byte-frozen.

    Phase 4 ships a NEW versioned arena (``foundry_60_asym_v1``); editing
    ``foundry_60`` would silently invalidate every recorded ledger that
    embeds its snapshot.  Pin the file digest so any edit is a loud decision.
    """

    digest = hashlib.sha256(Path("contracts_data/arenas/foundry_60.yaml").read_bytes()).hexdigest()
    assert digest == "34a069f922ff7dfa7b4ee87e7e8d39a73309cfb8687ae46240cf0548a1834eab"


@pytest.mark.unit
def test_foundry_60_asym_v1_layout_is_deliberate() -> None:
    """The Phase 4 arena's layout intent, pinned as geometry facts.

    §3.6: cover corridors favor approach on one axis, sightlines on another,
    co-designed with the objective cells.  The old arena's 336 symmetric
    scatter cells helped nobody (88% of shots blocked); this one is sparse
    and deliberate, so each property below is an authored decision.
    """

    arena = load_match_contract_catalog(Path("contracts_data")).arenas["foundry_60_asym_v1"]
    cells = arena.obstacle_cells
    assert arena.size == 60
    assert (arena.spawn_a.x, arena.spawn_a.y) == (4, 30)
    assert (arena.spawn_b.x, arena.spawn_b.y) == (52, 30)

    # Objective-victory contract: three ladder objectives + finish line.
    assert arena.vp_threshold == 15
    objectives = {o.objective_id: o for o in arena.objectives}
    assert set(objectives) == {
        "objective.west_yard",
        "objective.north_works",
        "objective.east_gate",
    }
    assert all(o.vp_per_round == 1 for o in arena.objectives)

    # Deliberate sparsity — lanes must be real, unlike foundry_60's 8-12%.
    density = len(cells) / (arena.size * arena.size)
    assert 0.015 <= density <= 0.05

    # Explicitly ASYMMETRIC: the 180-degree rotation symmetry foundry_60
    # pins must NOT hold here.
    assert not all((59 - x, 59 - y) in cells for x, y in cells)

    # Sightline axis: the mid-lane rows (y=28..32, x=8..48) are obstacle-free,
    # so the sniper genuinely defends the west objective at range.
    assert not any((x, y) in cells for x in range(8, 49) for y in range(28, 33))
    west = objectives["objective.west_yard"].cell
    assert line_of_sight_clear(arena.spawn_b, west, cells)

    # Approach axis: the north band (x=8..35, y=17..25) carries a broken
    # cover chain of small clusters — a covered corridor, not a wall.
    band = {c for c in cells if 8 <= c[0] <= 35 and 17 <= c[1] <= 25}
    seen: set[tuple[int, int]] = set()
    clusters: list[int] = []
    for start in band:
        if start in seen:
            continue
        stack, count = [start], 0
        seen.add(start)
        while stack:
            x, y = stack.pop()
            count += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if neighbor in band and neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
        clusters.append(count)
    assert len(clusters) >= 5
    assert max(clusters) <= 4

    # Cover and objectives are ONE layout problem: every objective is
    # contestable up close (cover within Chebyshev 3) and standable.
    for objective in arena.objectives:
        cell = (objective.cell.x, objective.cell.y)
        assert cell not in cells
        assert any(max(abs(cx - cell[0]), abs(cy - cell[1])) <= 3 for cx, cy in cells), (
            objective.objective_id
        )

    # Spawn pockets stay clear (radius > 4), like the historical arena.
    for spawn in (arena.spawn_a, arena.spawn_b):
        assert all(max(abs(spawn.x - x), abs(spawn.y - y)) > 4 for x, y in cells)

    # The snapshot round-trips and the contract hash is stable/recomputable.
    snapshot = arena.to_snapshot()
    assert (
        ModelSOCurrentLiveArenaSnapshot.model_validate(snapshot.model_dump(mode="json")) == snapshot
    )
    assert arena_contract_hash(snapshot) == arena_contract_hash(arena.to_snapshot())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("update", "message"),
    [
        (
            {"objectives": [], "vp_threshold": 15},
            "objectives and vp_threshold together",
        ),
        (
            {
                "objectives": [
                    {
                        "objective_id": "objective.dup",
                        "cell": {"x": 2, "y": 2},
                        "vp_per_round": 1,
                    },
                    {
                        "objective_id": "objective.dup",
                        "cell": {"x": 3, "y": 3},
                        "vp_per_round": 1,
                    },
                ],
                "vp_threshold": 5,
            },
            "duplicate objective ids",
        ),
        (
            {
                "objectives": [
                    {
                        "objective_id": "objective.on_spawn",
                        "cell": {"x": 0, "y": 0},
                        "vp_per_round": 1,
                    }
                ],
                "vp_threshold": 5,
            },
            "occupies a spawn point",
        ),
        (
            {
                "obstacles": [{"x": 3, "y": 3}],
                "objectives": [
                    {
                        "objective_id": "objective.on_wall",
                        "cell": {"x": 3, "y": 3},
                        "vp_per_round": 1,
                    }
                ],
                "vp_threshold": 5,
            },
            "occupies an obstacle",
        ),
    ],
)
def test_arena_spec_rejects_invalid_objectives(
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


# Objective-victory fields (Phase 4) are the ONLY compat-optional snapshot
# fields: pre-Phase-4 MATCH_STARTED payloads carry neither, and both default
# (()/None) so historical ledgers parse to the objective-free arena they were
# recorded on.  This census is exact — a new optional field must be added here
# deliberately, never inherited silently.
_COMPAT_OPTIONAL_SNAPSHOT_FIELDS = frozenset({"objectives", "vp_threshold"})


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
        "objectives": [
            {"objective_id": "objective.center", "cell": {"x": 20, "y": 20}, "vp_per_round": 1}
        ],
        "vp_threshold": 15,
    }
    snapshot = ModelSOCurrentLiveArenaSnapshot.model_validate(raw)
    assert snapshot.model_fields_set == frozenset(ModelSOCurrentLiveArenaSnapshot.model_fields)
    required = (
        frozenset(ModelSOCurrentLiveArenaSnapshot.model_fields) - _COMPAT_OPTIONAL_SNAPSHOT_FIELDS
    )
    for field in required:
        missing = dict(raw)
        del missing[field]
        with pytest.raises(ValidationError, match=field):
            ModelSOCurrentLiveArenaSnapshot.model_validate(missing)
    # The exact optional census: nothing beyond the Phase 4 pair may default.
    actually_optional = frozenset(
        name
        for name, field in ModelSOCurrentLiveArenaSnapshot.model_fields.items()
        if not field.is_required()
    )
    assert actually_optional == _COMPAT_OPTIONAL_SNAPSHOT_FIELDS
    # Both compat fields absent together parses to the objective-free arena.
    legacy = {
        key: value for key, value in raw.items() if key not in _COMPAT_OPTIONAL_SNAPSHOT_FIELDS
    }
    legacy_snapshot = ModelSOCurrentLiveArenaSnapshot.model_validate(legacy)
    assert legacy_snapshot.objectives == ()
    assert legacy_snapshot.vp_threshold is None
    # Half-configured objective views fail closed.
    with pytest.raises(ValidationError, match="together"):
        ModelSOCurrentLiveArenaSnapshot.model_validate({**raw, "vp_threshold": None})
    with pytest.raises(ValidationError, match="unexpected"):
        ModelSOCurrentLiveArenaSnapshot.model_validate({**raw, "unexpected": True})
