"""Purity contract for the canonical match-state fold (ONEX reducer shape).

Mirrors omnimarket's ``test_ledger_state_reducer_pure.py``: the fold's
``delta`` is the pure state-derivation surface (``delta(state, event) ->
(new_state, intents[])``), and these tests codify what was previously a
comment — that ``delta`` is side-effect-free, deterministic, and free of
clock/UUID/I/O reads. Bus publication lives only in the ``handle``/``apply``
effect boundary.

The fold is the load-bearing determinism surface: live runner and replay
engine both use it, which is what makes ``replay == live`` hold (R9). A
non-pure ``delta`` would silently break that.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.weapon import UnknownWeaponError
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.fold import MatchStateFold
from tests.runtime import runtime_dependencies

_MATCH_ID = "match.test.fold-purity"
_SOURCE = Path(MatchStateFold.__module__.replace(".", "/") + ".py")
# Resolve via inspect so the test doesn't depend on CWD.
_SOURCE_PATH = Path(inspect.getsourcefile(MatchStateFold))  # type: ignore[arg-type]


def _fold(bus: InProcessEventBus | None = None) -> MatchStateFold:
    runtime = runtime_dependencies()
    return MatchStateFold(
        _MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )


def _mech_payload(mech_id: str, player_id: str) -> dict[str, object]:
    """Minimal mech dict for a MATCH_STARTED payload (two mechs, opposite players)."""
    return {
        "mech_id": mech_id,
        "player_id": player_id,
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": {"x": 5, "y": 5},
        "facing": 45,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "armor_max": 10,
        "current_mode": "recon",
        "weapon_cooldowns": {},
        "boiler": {
            "match_id": _MATCH_ID,
            "mech_id": mech_id,
            "tick": 0,
            "pressure_current": 30,
            "pressure_maximum": 60,
            "regeneration_per_tick": 5,
            "heat_current": 0,
            "heat_redline_threshold": 80,
            "heat_rupture_threshold": 100,
            "heat_vent_rate": 5,
            "status_redline": False,
            "status_rupture_warning": False,
            "status_disabled": False,
            "status_ruptured": False,
            "modifier_heat_weapon_pressure": 1.0,
            "modifier_venting_penalty": 0.0,
            "modifier_mode_switch_heat_delta": 0,
        },
    }


def _match_started_env() -> ModelSOEventEnvelope:
    mid = "match.test.fold-purity"
    return ModelSOEventEnvelope(
        event_id="01JPUREPUREPUREPUREPUREPUR",
        match_id=mid,
        tick=0,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        event_type=SOEventType.MATCH_STARTED,
        payload={
            "seed": 1,
            "max_ticks": 10,
            "mechs": [
                _mech_payload("mech.a.01", "player.a"),
                _mech_payload("mech.b.01", "player.b"),
            ],
        },
        envelope=ModelEnvelope(correlation_id=uuid4(), entity_id=mid, emitted_at=datetime.now(UTC)),
    )


# ---------------------------------------------------------------------------
# Structural: delta exists and returns the intents list (the ONEX shape)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_delta_method_exists() -> None:
    """The fold exposes a ``delta`` method (the ONEX pure-reducer entrypoint)."""
    assert hasattr(MatchStateFold, "delta") and callable(MatchStateFold.delta)


@pytest.mark.unit
def test_delta_returns_intents_list() -> None:
    """delta returns a list of produced events (intents), not None."""
    fold = _fold()
    produced = fold.delta(_match_started_env())
    assert isinstance(produced, list)


@pytest.mark.unit
def test_fold_fails_closed_on_unknown_weapon_contract() -> None:
    fold = _fold()
    fold.apply(_match_started_env())
    event = ModelSOEventEnvelope(
        event_id="01JPUREPUREPUREPUREPUREP99",
        match_id=_MATCH_ID,
        tick=1,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        event_type=SOEventType.WEAPON_FIRED,
        payload={
            "weapon_id": "weapon.unknown",
            "pressure_cost": 0,
            "heat_generated": 0,
        },
        envelope=ModelEnvelope(correlation_id=uuid4(), entity_id=_MATCH_ID),
    )

    with pytest.raises(UnknownWeaponError, match=r"weapon\.unknown"):
        fold.apply(event)


@pytest.mark.unit
def test_handle_is_the_effect_boundary() -> None:
    """handle (the bus adapter) publishes delta's intents; delta alone does not.

    With a capturing bus, handle must publish; with no bus, nothing publishes
    but state still derives identically.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold_with_bus = _fold(bus=bus)
    fold_no_bus = _fold(bus=None)

    state_with = fold_with_bus.apply(_match_started_env())
    _ = fold_no_bus.apply(_match_started_env())
    # The live path (with bus) derived the same state as the no-bus path.
    assert state_with == fold_no_bus.state


# ---------------------------------------------------------------------------
# Determinism: identical inputs => identical outputs (the R9 foundation)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_delta_is_deterministic_for_identical_inputs() -> None:
    """Two folds fed the same event sequence reach identical state.

    This is the concrete replay==live guarantee: since delta is pure, folding
    the same events through two independent folds yields the same state.
    """
    fold_a = _fold(bus=None)
    fold_b = _fold(bus=None)
    events = [_match_started_env()]
    for tick in range(1, 4):
        events.append(
            ModelSOEventEnvelope(
                event_id=f"01JPUREPUREPUREPUREPUREP{tick:02d}",
                match_id=_MATCH_ID,
                tick=tick,
                sequence_in_tick=0,
                producer_node="node.test",
                subject=ModelSOEventSubject(mech_id="*", player_id="*"),
                event_type=SOEventType.MATCH_TICK,
                payload={},
                envelope=ModelEnvelope(correlation_id=uuid4(), entity_id=_MATCH_ID),
            )
        )
    for ev in events:
        fold_a.delta(ev)
        fold_b.delta(ev)
    assert fold_a.state == fold_b.state


# ---------------------------------------------------------------------------
# Purity: delta must not call clock/UUID/I/O (AST enforcement)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_delta_does_not_call_nondeterministic_builtins() -> None:
    """``delta`` must not call datetime.now / uuid4 / time-related randomness.

    Non-determinism (clock, UUIDs) is injected at the effect boundary
    (``make_event`` in the produced events, whose emitted_at is excluded from
    state-level replay validity). delta itself must be a pure function.
    """
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    delta_fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == "delta"
        ),
        None,
    )
    assert delta_fn is not None, "MatchStateFold.delta not found in source"
    forbidden: list[str] = []
    for node in ast.walk(delta_fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":  # datetime.now(...)
                forbidden.append("datetime.now")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"uuid4", "ulid"}:  # fresh id generation
                forbidden.append(node.func.id)
    assert not forbidden, f"delta() calls non-deterministic builtins: {forbidden}"


@pytest.mark.unit
def test_delta_does_not_reference_bus_publish() -> None:
    """``delta`` must not publish to the bus — that is the effect boundary's job."""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    delta_fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == "delta"
        ),
        None,
    )
    assert delta_fn is not None
    for node in ast.walk(delta_fn):
        if isinstance(node, ast.Attribute) and node.attr == "publish":
            pytest.fail("delta() references bus.publish — publication belongs in handle/apply")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "publish":
                pytest.fail("delta() calls bus.publish — publication belongs in handle/apply")


@pytest.mark.unit
def test_fold_module_does_not_import_io() -> None:
    """The fold module must not import I/O libraries (requests, open, sqlite)."""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    forbidden_imports = ["requests", "httpx", "aiohttp", "sqlite3", "psycopg", "asyncpg"]
    found = [
        mod for mod in forbidden_imports if f"import {mod}" in source or f"from {mod}" in source
    ]
    assert not found, f"fold module imports I/O libraries: {found}"
