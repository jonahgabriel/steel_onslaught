"""Fail-fast canonical-state admission — OMN-15490.

Two halves of one defect, each pinned here against the artifact that actually
runs (the real fold, the real ``InProcessEventBus``, the real ``SQLiteLedger``,
the real ``MatchRunner`` movement resolver) — no surrogates.

Half A — validator bypass on state transitions
    ``ModelSOMechRuntimeState`` / ``ModelSOMatchState`` are frozen and carry
    ``model_validator(mode="after")`` invariants, but the reducers evolved them
    with ``model_copy(update=...)``, which runs NO validators.  An upstream bug
    producing an invariant-violating value (e.g. a ``DAMAGE_APPLIED`` whose
    ``hp_after`` exceeds ``hp_max``) was silently admitted into canonical state
    and propagated to scoring/leaderboard.  RED-before: the fold accepted it and
    ``fold.state`` reported ``hp > hp_max``.

Half B — durable admission preceded fold admission
    ``composition`` subscribed ``ledger.append`` BEFORE the runner subscribed
    ``fold.handle``, the bus ran every subscriber before raising, and
    ``SQLiteLedger.append`` commits immediately.  A ``ReducerError`` during fold
    admission therefore happened AFTER the event was durably committed, and the
    ledger is append-only at the database layer (UPDATE/DELETE triggers) with no
    retract in the protocol — permanent contamination.  RED-before: the rejected
    event was readable from the ledger.

Half B (AC3) — pre-publish parity for MOVEMENT_RESOLVED
    ``_resolve_weapon_fire`` validates before publishing; ``_resolve_move`` did
    not, so a bad destination reached the ledger before the fold rejected it.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.admission_scoped import AdmissionScopedLedger
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.fold import MatchStateFold
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.reducers.movement import chebyshev
from tests.runtime import match_runner, runtime_dependencies
from tests.sqlite_ledger import open_sqlite_ledger

_MATCH_ID = "match.test.omn15490"
_CORRELATION = UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _fold(bus: InProcessEventBus | None = None) -> MatchStateFold:
    runtime = runtime_dependencies()
    return MatchStateFold(
        _MATCH_ID,
        _CORRELATION,
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )


def _mech_payload(
    mech_id: str,
    player_id: str,
    *,
    position: ModelSOPosition,
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mech_runtime_state",
        "mech_id": mech_id,
        "player_id": player_id,
        "side": "red" if player_id == "player.a" else "blue",
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": position.model_dump(mode="json"),
        "facing": 45,
        "speed": 4,
        "hp": 100,
        "hp_max": 100,
        "armor_value": 10,
        "armor_max": 10,
        "alive": True,
        "pilot_alive": True,
        "current_mode": "recon",
        "mode_lock_until": 0,
        "transition_ticks_remaining": 0,
        "transition_to_mode": None,
        "sensor_dropout_ticks_remaining": 0,
        "mode_switch_disabled_until": 0,
        "weapon_cooldowns": {},
        "evasion": 0.0,
        "accuracy_penalty_next_fire": 0.0,
        "jamming_intensity": 0.0,
        "under_sensor_lock": False,
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
        "redline_consecutive_ticks": 0,
        "overloaded": False,
        "overloaded_consecutive_ticks": 0,
    }


def _match_started_env(arena: ModelSOArenaSpec) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id="01JOMN15490MATCHSTARTED001",
        match_id=_MATCH_ID,
        tick=0,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="*", player_id="*"),
        event_type=SOEventType.MATCH_STARTED,
        payload={
            "seed": 1,
            "max_ticks": 10,
            "mechs": [
                _mech_payload("mech.a.01", "player.a", position=arena.spawn_a),
                _mech_payload("mech.b.01", "player.b", position=arena.spawn_b),
            ],
            "arena": arena.to_snapshot().model_dump(mode="json"),
        },
        envelope=ModelEnvelope(
            correlation_id=_CORRELATION,
            entity_id=_MATCH_ID,
            emitted_at=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )


def _damage_env(
    *, hp_after: int, event_id: str = "01JOMN15490DAMAGEAPPLIED01"
) -> ModelSOEventEnvelope:
    """A DAMAGE_APPLIED naming an ``hp_after`` the fold will write verbatim.

    ``hp_after`` is upstream-supplied: the payload model only constrains it to
    ``>= 0``, so an upstream arithmetic bug can name a value above ``hp_max``.
    """
    return ModelSOEventEnvelope(
        event_id=event_id,
        match_id=_MATCH_ID,
        tick=1,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        event_type=SOEventType.DAMAGE_APPLIED,
        payload={
            "target_id": "mech.a.01",
            "damage": 0,
            "cause": "weapon_hit",
            "hp_after": hp_after,
        },
        envelope=ModelEnvelope(
            correlation_id=_CORRELATION,
            entity_id=_MATCH_ID,
            emitted_at=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )


# ---------------------------------------------------------------------------
# Half A / AC2 — canonical-state transitions re-run model validators
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hp_above_hp_max_is_rejected_by_full_construction_but_not_by_model_copy() -> None:
    """Control: EXISTS-BUT-WRONG, not missing.

    The invariant is declared and full construction enforces it; only the
    ``model_copy`` transition path skipped it.  Pinning both polarities keeps a
    future refactor from "fixing" this by deleting the validator, and documents
    exactly why ``evolve`` (re-validate) is the correct shape.
    """
    runtime = runtime_dependencies()
    fold = _fold()
    fold.apply(_match_started_env(runtime.arena))
    mech = fold.state.mech_states["mech.a.01"]

    # Full construction: enforced.
    with pytest.raises(ValidationError, match="must not exceed hp_max"):
        type(mech).model_validate({**dict(mech), "hp": 999})

    # model_copy: silently admits it — the bypass this ticket closes.
    bypassed = mech.model_copy(update={"hp": 999})
    assert bypassed.hp == 999 > bypassed.hp_max

    # evolve: the fail-fast replacement wired through every reducer.
    with pytest.raises(ValidationError, match="must not exceed hp_max"):
        mech.evolve(update={"hp": 999})


@pytest.mark.unit
def test_canonical_state_models_use_evolve_not_model_copy() -> None:
    """Structural ratchet: no reducer/fold path may reintroduce the bypass.

    ``model_copy(update=...)`` on canonical state is the defect itself, so the
    modules that own canonical-state transitions must not contain it at all.
    """
    import steel_onslaught.match.fold as fold_module
    import steel_onslaught.reducers.boiler as boiler_module
    import steel_onslaught.reducers.failure as failure_module
    import steel_onslaught.reducers.lifecycle as lifecycle_module
    import steel_onslaught.reducers.mode as mode_module
    import steel_onslaught.reducers.movement as movement_module

    offenders: dict[str, int] = {}
    for module in (
        fold_module,
        boiler_module,
        failure_module,
        lifecycle_module,
        mode_module,
        movement_module,
    ):
        source_path = inspect.getsourcefile(module)
        assert source_path is not None
        count = Path(source_path).read_text().count(".model_copy(")
        if count:
            offenders[module.__name__] = count
    assert offenders == {}, (
        "canonical-state transitions must use evolve() so validators re-run; "
        f"model_copy found in {offenders}"
    )


def _first_call_line(source: str, callee: str) -> int | None:
    """Line offset of the first call to *callee*, by AST — comments cannot fake it."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else ".".join(
                reversed(
                    [
                        part.attr if isinstance(part, ast.Attribute) else getattr(part, "id", "")
                        for part in _attribute_chain(func)
                    ]
                )
            )
            if isinstance(func, ast.Attribute)
            else ""
        )
        if name.endswith(callee):
            return node.lineno
    return None


def _attribute_chain(node: ast.expr) -> list[ast.expr]:
    chain: list[ast.expr] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        chain.append(current)
        current = current.value
    chain.append(current)
    return chain


@pytest.mark.unit
def test_movement_and_weapon_fire_both_validate_before_publish() -> None:
    """Structural parity ratchet for AC3 — neither resolver may lose its check.

    Checked by AST call position, not substring position, so a docstring or
    comment mentioning the event name cannot make it pass or fail spuriously.
    """
    from steel_onslaught.match.runner import MatchRunner

    fire_src = inspect.getsource(MatchRunner._resolve_weapon_fire)
    assert _first_call_line(fire_src, "validate_weapon_fire_intent") is not None, (
        "the weapon-fire path is the parity reference and must validate pre-publish"
    )

    move_src = inspect.getsource(MatchRunner._resolve_move)
    validate_line = _first_call_line(move_src, "validate_movement_resolved")
    publish_line = _first_call_line(move_src, "publish")
    assert validate_line is not None, "_resolve_move must validate admissibility"
    assert publish_line is not None, "_resolve_move must publish MOVEMENT_RESOLVED"
    assert validate_line < publish_line, (
        f"the admissibility check (line {validate_line}) must run BEFORE the publish "
        f"call (line {publish_line})"
    )


@pytest.mark.unit
def test_fold_rejects_invariant_violating_hp_from_damage_applied() -> None:
    """RED-before: the fold silently admitted hp > hp_max into canonical state.

    ``MatchStateFold._on_damage_applied`` wrote the upstream ``hp_after``
    through ``model_copy(update=...)``, which skips ``_hp_within_max``.  On the
    pre-fix tree this call returned normally and ``fold.state`` reported
    ``hp == 999`` against ``hp_max == 100`` — corrupt canonical state, no error.
    """
    runtime = runtime_dependencies()
    fold = _fold()
    fold.apply(_match_started_env(runtime.arena))
    assert fold.state.mech_states["mech.a.01"].hp == 100

    with pytest.raises((ValidationError, ReducerError)) as excinfo:
        fold.apply(_damage_env(hp_after=999))
    assert "hp_max" in str(excinfo.value)

    # And the corruption never became visible canonical state.
    assert fold.state.mech_states["mech.a.01"].hp <= fold.state.mech_states["mech.a.01"].hp_max


@pytest.mark.unit
def test_fold_still_admits_valid_damage() -> None:
    """GREEN guard: re-validation must not reject a legitimate transition."""
    runtime = runtime_dependencies()
    fold = _fold()
    fold.apply(_match_started_env(runtime.arena))
    fold.apply(_damage_env(hp_after=42))
    assert fold.state.mech_states["mech.a.01"].hp == 42


# ---------------------------------------------------------------------------
# Half B / AC1 — a fold-rejected event must not be durably admitted
# ---------------------------------------------------------------------------


def _speed_exceeded_move_env(arena: ModelSOArenaSpec) -> ModelSOEventEnvelope:
    """A MOVEMENT_RESOLVED the fold has ALWAYS rejected (``speed_exceeded``).

    Deliberately independent of the half-A fix: this event was rejected by
    ``ReducerMovement`` before OMN-15490 too, so the durable-admission test
    below isolates the ordering defect rather than riding on the new validator.
    """
    origin = arena.spawn_a
    return ModelSOEventEnvelope(
        event_id="01JOMN15490BADMOVE00000001",
        match_id=_MATCH_ID,
        tick=0,
        sequence_in_tick=0,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id="mech.a.01", player_id="player.a"),
        event_type=SOEventType.MOVEMENT_RESOLVED,
        payload={
            "from": {"x": origin.x, "y": origin.y},
            "to": {"x": origin.x, "y": origin.y + 30},
            "ticks_consumed": 1,
            "pressure_consumed": 30,  # base_speed 4 -> max 4 cells
        },
        envelope=ModelEnvelope(
            correlation_id=_CORRELATION,
            entity_id=_MATCH_ID,
            emitted_at=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )


@pytest.mark.integration
def test_fold_rejected_event_is_not_durably_admitted(tmp_path: Path) -> None:
    """RED-before: the SQLite ledger permanently kept an event the fold rejected.

    Wires the real composition shape — the ledger and the fold on the real
    ``InProcessEventBus``, writing to a real ``SQLiteLedger``.  The fold raises
    ``speed_exceeded``; because the bus runs every subscriber before raising and
    ``append`` autocommits, the pre-fix tree had already written the row, and
    the append-only triggers make that irreversible (asserted below).
    """
    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490.sqlite3")
    bus = InProcessEventBus()
    # Exact composition wiring: the admission-scoped facade subscribed first
    # (read-your-writes) and enlisted for verdicts; the fold is the authority.
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    fold = _fold(bus=bus)
    bus.subscribe_admission(fold.handle)

    bus.publish(_match_started_env(runtime.arena))
    admitted = [e.event_id for e in ledger.read_all(_MATCH_ID)]
    assert admitted == ["01JOMN15490MATCHSTARTED001"], "a valid event must be durably admitted"

    bad = _speed_exceeded_move_env(runtime.arena)
    with pytest.raises(ExceptionGroup) as excinfo:
        bus.publish(bad)
    assert "speed_exceeded" in str(excinfo.value.exceptions[0])

    after = [e.event_id for e in ledger.read_all(_MATCH_ID)]
    assert bad.event_id not in after, (
        f"a fold-rejected event must not reach durable storage: ledger contains {after!r}"
    )
    assert after == admitted, "no other event may be lost by the refusal"


@pytest.mark.integration
def test_staged_events_are_readable_before_they_are_durable(tmp_path: Path) -> None:
    """Read-your-writes is preserved — the reason the ledger stays subscriber #0.

    The scoring reducer's replay-validity check and the learning after-match
    handler both project from the ledger DURING dispatch of an event that is
    still in flight.  If staging hid it, the after-match projection would derive
    ``event_counts`` from an incomplete stream and record wrong evidence
    silently (it raises only on a missing MATCH_SCORED).  So a subscriber that
    reads mid-dispatch must see the staged event, while another connection must
    not see it until it is admitted.
    """
    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490-readthrough.sqlite3")
    scoped = AdmissionScopedLedger(ledger)
    bus = InProcessEventBus()
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    fold = _fold(bus=bus)
    bus.subscribe_admission(fold.handle)

    observed: list[tuple[int, int]] = []

    def _reader(event: ModelSOEventEnvelope) -> None:
        # Runs after the staging subscriber, mid-dispatch.
        observed.append(
            (
                len(list(scoped.read_all(_MATCH_ID))),
                len(list(ledger.read_all(_MATCH_ID))),
            )
        )

    bus.subscribe(_reader)
    bus.publish(_match_started_env(runtime.arena))

    through_facade, straight_to_storage = observed[0]
    assert through_facade == 1, "a later subscriber must read its own write"
    assert straight_to_storage == 0, "the write must not be durable before admission"
    assert scoped.pending_events == ()
    assert len(list(ledger.read_all(_MATCH_ID))) == 1, "admitted -> flushed through"


@pytest.mark.integration
def test_admitted_events_reach_storage_in_publish_order(tmp_path: Path) -> None:
    """Staging must not reorder durable rows relative to the pre-fix behaviour.

    A parent is staged before the intents it publishes and is admitted only
    after their subtrees finish, so the admitted-prefix flush writes parent
    before child — the order the previous ledger-first registration produced.
    """
    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490-order.sqlite3")
    scoped = AdmissionScopedLedger(ledger)
    bus = InProcessEventBus()
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    fold = _fold(bus=bus)
    bus.subscribe_admission(fold.handle)

    child = _damage_env(hp_after=40, event_id="01JOMN15490CHILD0000000001")

    def _publish_child_once(event: ModelSOEventEnvelope) -> None:
        if event.event_type is SOEventType.MATCH_STARTED:
            bus.publish(child)

    bus.subscribe(_publish_child_once)
    bus.publish(_match_started_env(runtime.arena))

    # Raw storage order (not the canonical ORDER BY) is what this pins.
    rows = [
        row[0]
        for row in ledger._conn.execute(  # raw insertion order IS the claim here
            "SELECT event_id FROM events ORDER BY _rowid_ ASC"
        )
    ]
    assert rows == ["01JOMN15490MATCHSTARTED001", "01JOMN15490CHILD0000000001"], (
        "the parent must be written before the event it caused"
    )


@pytest.mark.integration
def test_durable_contamination_would_be_irreversible(tmp_path: Path) -> None:
    """Why AC1 is prevention, not repair: the ledger has no retract path.

    Pins the premise the fix rests on — DELETE is refused at the database layer
    and the ``EventLedger`` protocol exposes no removal — so a bad row admitted
    once can never be taken back.
    """
    from steel_onslaught.ledger.protocol import EventLedger

    assert not [
        name for name in ("delete", "retract", "remove", "truncate") if hasattr(EventLedger, name)
    ], "the ledger protocol must have no retract path"

    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490-irreversible.sqlite3")
    bus = InProcessEventBus()
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    bus.publish(_match_started_env(runtime.arena))

    with pytest.raises(Exception, match="append-only"):
        ledger._conn.execute(  # asserting the storage-layer append-only guarantee
            "DELETE FROM events WHERE event_id = ?", ("01JOMN15490MATCHSTARTED001",)
        )


@pytest.mark.integration
def test_invariant_violating_state_is_not_durably_admitted(tmp_path: Path) -> None:
    """AC1 x AC2 together: the newly-enforced invariant also blocks the write."""
    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490-hp.sqlite3")
    bus = InProcessEventBus()
    # Exact composition wiring: the admission-scoped facade subscribed first
    # (read-your-writes) and enlisted for verdicts; the fold is the authority.
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    fold = _fold(bus=bus)
    bus.subscribe_admission(fold.handle)

    bus.publish(_match_started_env(runtime.arena))
    bad = _damage_env(hp_after=999)
    with pytest.raises(ExceptionGroup):
        bus.publish(bad)

    assert bad.event_id not in [e.event_id for e in ledger.read_all(_MATCH_ID)]


@pytest.mark.integration
def test_durable_admission_survives_a_full_valid_publish(tmp_path: Path) -> None:
    """GREEN guard: deferred admission still records every event of a good tick.

    Covers the re-entrant case — the fold publishes derived intents from inside
    the outer publish, so the staged batch spans a nested dispatch tree.
    """
    runtime = runtime_dependencies()
    ledger = open_sqlite_ledger(tmp_path / "omn15490-ok.sqlite3")
    bus = InProcessEventBus()
    # Exact composition wiring: the admission-scoped facade subscribed first
    # (read-your-writes) and enlisted for verdicts; the fold is the authority.
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    fold = _fold(bus=bus)
    bus.subscribe_admission(fold.handle)

    bus.publish(_match_started_env(runtime.arena))
    bus.publish(_damage_env(hp_after=42))

    recorded = [e.event_id for e in ledger.read_all(_MATCH_ID)]
    assert "01JOMN15490MATCHSTARTED001" in recorded
    assert "01JOMN15490DAMAGEAPPLIED01" in recorded
    assert fold.state.mech_states["mech.a.01"].hp == 42


# ---------------------------------------------------------------------------
# Half B / AC3 — pre-publish validation parity for MOVEMENT_RESOLVED
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_movement_resolved_is_validated_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED-before: an invalid MOVEMENT_RESOLVED was published, then rejected.

    ``_resolve_weapon_fire`` runs ``validate_weapon_fire_intent`` BEFORE
    publishing; ``_resolve_move`` published whatever the destination resolver
    returned.  Injecting a resolver fault (the upstream bug class the guard
    exists for) must now fail at the resolver, not after the ledger commit.

    The assertions are chosen so the durable-admission fix CANNOT satisfy this
    test on its own — a discarded staged batch also leaves the ledger clean.
    What only pre-publish validation gives is:
      * a plain ``ReducerError`` out of the resolver, NOT an ``ExceptionGroup``
        raised by the bus after dispatch, and
      * no subscriber ever observing the event at all.
    """
    import steel_onslaught.match.runner as runner_module

    ledger = open_sqlite_ledger(tmp_path / "omn15490-move.sqlite3")
    bus = InProcessEventBus()
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    seen: list[ModelSOEventEnvelope] = []
    bus.subscribe(seen.append, event_types=[SOEventType.MOVEMENT_RESOLVED])
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.omn15490-move",
        seed=7,
        loadout_a=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        loadout_b=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        max_ticks=4,
        spawn_a=ModelSOPosition(x=10, y=10),
        spawn_b=ModelSOPosition(x=25, y=25),
    )

    def _corrupt_destination(**kwargs: object) -> ModelSOPosition:
        """Simulate an upstream resolver bug: teleport far beyond effective speed."""
        from_pos = kwargs["from_pos"]
        assert isinstance(from_pos, ModelSOPosition)
        return ModelSOPosition(x=from_pos.x, y=min(39, from_pos.y + 30))

    monkeypatch.setattr(runner_module, "resolve_move_destination", _corrupt_destination)

    with pytest.raises(ReducerError) as excinfo:
        runner.run()
    message = str(excinfo.value)
    assert "movement_resolution_invalid" in message, (
        "the resolver must refuse BEFORE publishing; an ExceptionGroup here means "
        f"the event was dispatched and rejected downstream instead. got: {message}"
    )
    assert "speed_exceeded" in message, "the underlying admissibility reason must be reported"

    assert seen == [], (
        "no subscriber may observe an inadmissible MOVEMENT_RESOLVED — it must never "
        f"be published; got {[e.event_id for e in seen]!r}"
    )
    published_moves = [
        e
        for e in ledger.read_all("match.test.omn15490-move")
        if e.event_type is SOEventType.MOVEMENT_RESOLVED
    ]
    assert published_moves == [], (
        "an invalid MOVEMENT_RESOLVED must never reach the ledger; found "
        f"{[(e.event_id, e.payload) for e in published_moves]!r}"
    )


@pytest.mark.integration
def test_valid_movement_still_publishes_and_persists(tmp_path: Path) -> None:
    """GREEN guard: the pre-publish check must not reject legitimate movement."""
    ledger = open_sqlite_ledger(tmp_path / "omn15490-move-ok.sqlite3")
    bus = InProcessEventBus()
    scoped = AdmissionScopedLedger(ledger)
    bus.subscribe(scoped.append)
    bus.enlist_admission_observer(scoped)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.test.omn15490-move-ok",
        seed=7,
        loadout_a=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        loadout_b=load_loadout(Path("contracts_data/loadouts/example_aggressive_light.yaml")),
        max_ticks=4,
        spawn_a=ModelSOPosition(x=10, y=10),
        spawn_b=ModelSOPosition(x=25, y=25),
    )
    runner.run()
    assert scoped.pending_events == (), (
        "no event may be stranded in the staging buffer at the end of a match — "
        "an un-flushed admitted event is silent data loss, the mirror of the "
        f"contamination this ticket closes; stranded: "
        f"{[e.event_id for e in scoped.pending_events]!r}"
    )
    moves = [
        e
        for e in ledger.read_all("match.test.omn15490-move-ok")
        if e.event_type is SOEventType.MOVEMENT_RESOLVED
    ]
    assert moves, "the aggressive pilots must have closed distance"
    for move in moves:
        payload = move.payload
        origin = ModelSOPosition.model_validate(payload["from"])
        destination = ModelSOPosition.model_validate(payload["to"])
        assert payload["pressure_consumed"] == chebyshev(origin, destination)
