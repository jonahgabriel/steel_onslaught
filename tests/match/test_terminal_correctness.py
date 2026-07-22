"""Terminal-state correctness proofs.

Every case here is a way a match previously ended WRONG, or did not end at all:

  - ``match-runner-fold-01``: sudden-death pressure resolved one mech at a time
    in ``mech_id`` order and broke on the first kill, so the alphabetically
    first mech died before its opponent absorbed the identical lethal pulse.
  - ``reducers-02``: a survivor transition to ZERO emitted no terminal at all,
    leaving the match RUNNING with an empty arena.
  - the runaway failsafe: unbounded matches are a design decision, so a match
    that stops converging must be diagnosable rather than silent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.runner import RUNAWAY_TICK_LIMIT
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.pilots.schemas import ModelSOPosition
from tests.runtime import match_runner, runtime_dependencies

_RED_PASSIVE = Path("contracts_data/loadouts/proof_red_defensive_passive.yaml")
_BLUE_PASSIVE = Path("contracts_data/loadouts/proof_blue_defensive_passive.yaml")

_MATCH_ID = "match.test.terminal-correctness"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")
_CORRELATION = UUID("11111111-1111-1111-1111-111111111111")


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    payload: dict[str, Any] | None = None,
    seq: int = 0,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=_MATCH_ID,
        tick=tick,
        sequence_in_tick=seq,
        event_type=event_type,
        producer_node="node.test",
        subject=subject,
        payload=payload or {},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=_MATCH_ID,
            emitted_at=datetime.now(UTC),
        ),
    )


def _mech_dict(
    mech_id: str,
    player_id: str,
    *,
    position: tuple[int, int],
    hp: int = 100,
    heat: int = 0,
    vent_rate: int = 5,
) -> dict[str, Any]:
    """Complete current-live mech snapshot for the MATCH_STARTED payload."""
    return {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mech_runtime_state",
        "mech_id": mech_id,
        "player_id": player_id,
        "side": "red" if player_id == "player.red" else "blue",
        "loadout_id": "loadout.a",
        "pilot_id": "pilot.aggressive",
        "chassis_id": "chassis.medium.hunter_mk1",
        "chassis_class": "medium",
        "sensor_ids": [],
        "gizmo_ids": [],
        "base_speed": 4,
        "position": {"x": position[0], "y": position[1]},
        "facing": 45,
        "speed": 4,
        "hp": hp,
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
            "heat_current": heat,
            "heat_redline_threshold": 80,
            "heat_capacity": 100,
            "heat_rupture_threshold": 100,
            "heat_vent_rate": vent_rate,
            "status_redline": heat >= 80,
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


def _arena_with_spawns(
    arena_id: str, red: tuple[int, int], blue: tuple[int, int]
) -> ModelSOArenaSpec:
    """Arena whose spawns equal the roster positions the fold requires."""
    base = runtime_dependencies().arena
    return ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id=arena_id,
        display_name=f"Injected {arena_id}",
        size=base.size,
        spawn_a=ModelSOPosition(x=red[0], y=red[1]),
        spawn_b=ModelSOPosition(x=blue[0], y=blue[1]),
        obstacles=(),
        rects=(),
        sudden_death_start_tick=base.sudden_death_start_tick,
        sudden_death_damage_base=base.sudden_death_damage_base,
    )


def _fold_with_two_mechs(
    bus: InProcessEventBus,
    *,
    red: dict[str, Any],
    blue: dict[str, Any],
) -> MatchStateFold:
    runtime = runtime_dependencies()
    arena = _arena_with_spawns(
        "injected_terminal_field",
        (red["position"]["x"], red["position"]["y"]),
        (blue["position"]["x"], blue["position"]["y"]),
    )
    catalog = MatchContractCatalog(
        arenas={**runtime.catalog.arenas, arena.arena_id: arena},
        chassis=runtime.catalog.chassis,
        boilers=runtime.catalog.boilers,
        sensors=runtime.catalog.sensors,
        weapons=runtime.catalog.weapons,
        gizmos=runtime.catalog.gizmos,
        transitions=runtime.catalog.transitions,
    )
    fold = MatchStateFold(
        _MATCH_ID,
        _CORRELATION,
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=catalog,
    )
    bus.subscribe(fold.handle)
    bus.publish(
        _env(
            SOEventType.MATCH_STARTED,
            tick=0,
            payload={
                "seed": 1,
                "max_ticks": 200,
                "mechs": [red, blue],
                "arena": arena.to_snapshot().model_dump(mode="json"),
            },
        )
    )
    assert fold.state.status is SOMatchStatus.RUNNING
    assert len(fold.state.surviving_player_ids()) == 2
    return fold


# ---------------------------------------------------------------------------
# match-runner-fold-01 — sudden-death side bias
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("seed", [17, 99, 1234])
def test_symmetric_sudden_death_is_a_draw_at_every_seed(seed: int) -> None:
    """Symmetric loadouts must never hand the win to a side.

    Before the fix, ``_apply_sudden_death`` iterated ``sorted(living_mechs,
    key=mech_id)``, published DAMAGE + DESTROYED for each mech inline, and
    broke on the first kill.  ``mech.a.01`` therefore died before ``mech.b.01``
    absorbed the same lethal pulse: EVERY symmetric uncapped match ended
    ``winner=player.b`` with the winner at FULL hp.  The pulse is now
    simultaneous, so identical mechs die together.
    """
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id=f"match.sudden-death.symmetric.{seed}",
        seed=seed,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=None,
    )

    live = runner.run()

    assert live.status is SOMatchStatus.ENDED
    assert live.end_reason is SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION
    assert live.winner_id is None
    # The decisive proof of the old bias: the "winner" used to be at full hp.
    assert {mech.hp for mech in live.mech_states.values()} == {0}


@pytest.mark.integration
def test_sudden_death_damages_every_mech_before_destroying_any() -> None:
    """The lethal pulse is applied simultaneously, not mech-by-mech.

    The ledger order is the proof: on the lethal tick BOTH ``damage_applied``
    rows precede BOTH ``mech_destroyed`` rows.  Interleaving them is what let
    the first destruction end the match before the second mech was damaged.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.sudden-death.ordering",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=None,
    )

    live = runner.run()

    lethal_tick = [
        event
        for event in captured
        if event.tick == live.tick
        and event.event_type in {SOEventType.DAMAGE_APPLIED, SOEventType.MECH_DESTROYED}
    ]
    kinds = [event.event_type for event in lethal_tick]
    assert kinds == [
        SOEventType.DAMAGE_APPLIED,
        SOEventType.DAMAGE_APPLIED,
        SOEventType.MECH_DESTROYED,
        SOEventType.MECH_DESTROYED,
    ]
    # Every mech took the same pressure from the same pre-pulse snapshot.
    damage = {
        event.payload["target_id"]: event.payload["damage"]
        for event in lethal_tick
        if event.event_type is SOEventType.DAMAGE_APPLIED
    }
    assert len(set(damage.values())) == 1


@pytest.mark.unit
def test_a_single_pressure_kill_still_declares_victory() -> None:
    """The simultaneity fix must not turn ordinary decisive kills into draws."""
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = _fold_with_two_mechs(
        bus,
        red=_mech_dict("mech.red.01", "player.red", position=(5, 5), hp=10),
        blue=_mech_dict("mech.blue.01", "player.blue", position=(35, 35), hp=100),
    )

    bus.publish(
        _env(
            SOEventType.DAMAGE_APPLIED,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload={
                "target_id": "mech.red.01",
                "damage": 10,
                "cause": "sudden_death",
                "hp_after": 0,
                "source_mech_id": None,
            },
        )
    )
    bus.publish(
        _env(
            SOEventType.MECH_DESTROYED,
            tick=1,
            subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
            payload={"cause": "sudden_death", "source_mech_id": None},
        )
    )

    victory = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victory) == 1
    assert victory[0].payload["winner_player_id"] == "player.blue"
    assert fold.state.end_reason is SOMatchEndReason.LAST_MECH_STANDING


@pytest.mark.unit
def test_lone_survivor_at_zero_hp_defers_to_the_mutual_destruction_draw() -> None:
    """A survivor whose own destruction is in flight is not a winner.

    The fold sees a simultaneous kill as two ORDERED events, so the survivor
    count walks ``2 -> 1 -> 0``.  Declaring on the intermediate ``==1`` state
    would crown a mech that is already at zero hp with its ``MECH_DESTROYED``
    still queued.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = _fold_with_two_mechs(
        bus,
        red=_mech_dict("mech.red.01", "player.red", position=(5, 5), hp=10),
        blue=_mech_dict("mech.blue.01", "player.blue", position=(35, 35), hp=10),
    )

    for mech_id, player_id in (
        ("mech.red.01", "player.red"),
        ("mech.blue.01", "player.blue"),
    ):
        bus.publish(
            _env(
                SOEventType.DAMAGE_APPLIED,
                tick=1,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
                payload={
                    "target_id": mech_id,
                    "damage": 10,
                    "cause": "sudden_death",
                    "hp_after": 0,
                    "source_mech_id": None,
                },
            )
        )
    for mech_id, player_id in (
        ("mech.red.01", "player.red"),
        ("mech.blue.01", "player.blue"),
    ):
        bus.publish(
            _env(
                SOEventType.MECH_DESTROYED,
                tick=1,
                subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
                payload={"cause": "sudden_death", "source_mech_id": None},
            )
        )

    assert not [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    ended = [e for e in captured if e.event_type is SOEventType.MATCH_ENDED]
    assert len(ended) == 1
    assert ended[0].payload["reason"] == SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION.value
    assert ended[0].payload["winner_id"] is None
    assert fold.state.status is SOMatchStatus.ENDED
    assert fold.state.winner_id is None


# ---------------------------------------------------------------------------
# reducers-02 — mutual KO emits no terminal
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rupture_that_kills_the_last_opponent_emits_a_terminal() -> None:
    """A 2 -> 0 rupture pass must produce a terminal, not a running empty arena.

    ``_rupture`` destroys the rupturing mech unconditionally AND deals area
    damage inside the same cascade pass, so ``_maybe_declare_terminal``
    observed ``survivors_before=2, survivors_after=0``.  That transition used
    to emit NOTHING: the status stayed RUNNING with zero survivors and the
    runner published empty MATCH_TICKs until an external guard aborted it.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = _fold_with_two_mechs(
        bus,
        # Heat sits exactly on the 100-point rupture threshold with venting
        # disabled, so the cascade ruptures red on the first tick; blue is
        # inside the 3-cell blast radius and below the 15-point area damage.
        red=_mech_dict("mech.red.01", "player.red", position=(5, 5), hp=100, heat=100, vent_rate=0),
        blue=_mech_dict("mech.blue.01", "player.blue", position=(6, 5), hp=10),
    )

    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))

    assert [e.event_type for e in captured].count(SOEventType.BOILER_RUPTURED) == 1
    destroyed = {e.subject.mech_id for e in captured if e.event_type is SOEventType.MECH_DESTROYED}
    assert destroyed == {"mech.red.01", "mech.blue.01"}
    ended = [e for e in captured if e.event_type is SOEventType.MATCH_ENDED]
    assert len(ended) == 1, "a zero-survivor cascade must emit exactly one terminal"
    assert ended[0].payload["reason"] == SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION.value
    assert not [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert fold.state.status is SOMatchStatus.ENDED
    assert fold.state.winner_id is None
    assert not fold.state.surviving_player_ids()


@pytest.mark.integration
def test_rupture_leaving_one_survivor_still_declares_victory() -> None:
    """The zero-survivor branch must not swallow the ordinary rupture victory."""
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = _fold_with_two_mechs(
        bus,
        red=_mech_dict("mech.red.01", "player.red", position=(5, 5), hp=100, heat=100, vent_rate=0),
        blue=_mech_dict("mech.blue.01", "player.blue", position=(35, 35), hp=100),
    )

    bus.publish(_env(SOEventType.MATCH_TICK, tick=1))

    victory = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(victory) == 1
    assert victory[0].payload["winner_player_id"] == "player.blue"
    assert fold.state.end_reason is SOMatchEndReason.LAST_MECH_STANDING


# ---------------------------------------------------------------------------
# Runaway failsafe (operator decision 2: matches are unbounded)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_non_converging_match_hits_the_runaway_failsafe_with_its_own_reason() -> None:
    """A match that stops converging terminates diagnosably, never as a draw.

    The arena here defers its sudden-death pressure past the failsafe, so
    nothing can ever end the match.  The terminal must therefore name
    ``aborted_runaway`` — a reason no gameplay path can produce — rather than
    silently masquerading as ``draw_max_ticks``.
    """
    base = runtime_dependencies().arena
    stalled = ModelSOArenaSpec(
        schema_version="0.1.0",
        kind="steel_onslaught.arena",
        arena_id="runaway_field",
        display_name="Runaway failsafe arena",
        size=base.size,
        spawn_a=ModelSOPosition(x=base.spawn_a.x, y=base.spawn_a.y),
        spawn_b=ModelSOPosition(x=base.spawn_b.x, y=base.spawn_b.y),
        obstacles=(),
        rects=(),
        sudden_death_start_tick=RUNAWAY_TICK_LIMIT * 10,
        sudden_death_damage_base=8,
    )
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.runaway.failsafe",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=None,
        arena_override=stalled,
    )

    live = runner.run()

    assert live.status is SOMatchStatus.ENDED
    assert live.tick == RUNAWAY_TICK_LIMIT
    assert live.end_reason is SOMatchEndReason.ABORTED_RUNAWAY
    assert live.winner_id is None
    # The failsafe is a guard, not a cap: both mechs are untouched.
    assert {mech.hp for mech in live.mech_states.values()} == {
        mech.hp_max for mech in live.mech_states.values()
    }


@pytest.mark.integration
def test_explicit_cap_above_the_failsafe_is_honoured_not_preempted() -> None:
    """An explicit ``max_ticks`` above the failsafe must still reach its cap.

    The failsafe exists to diagnose a NON-converging *unbounded* match.  A
    caller who deliberately asks for more ticks than the guard has not hit a
    bug: ``--max-ticks`` is ``IntRange(min=1)`` with no upper bound, so a
    2000-tick match is a legitimate request.  Preempting it at tick 1000 with
    ``aborted_runaway`` would report an engine defect for a correct run and
    silently truncate the match a caller paid for.
    """
    cap = RUNAWAY_TICK_LIMIT + 1000
    bus = InProcessEventBus()
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.runaway.explicit-cap",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=cap,
    )

    live = runner.run()

    assert live.status is SOMatchStatus.ENDED
    assert live.tick == cap
    assert live.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert live.winner_id is None


@pytest.mark.integration
def test_no_mech_destroyed_row_follows_the_mutual_destruction_terminal() -> None:
    """Nothing may be published after the terminal on the simultaneous pulse.

    The pulse resolves every destruction in one loop, so the terminal fires
    from inside that loop.  In a duel it always coincides with the LAST
    destruction (see ``_apply_sudden_death``), but that is a property of
    one-mech-per-player, not of the loop — and a trailing ``mech_destroyed``
    would be rejected outright by the browser transport as a post-terminal
    frame.  This pins the duel ordering so it cannot regress silently.
    """
    bus = InProcessEventBus()
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    runner, _runtime = match_runner(
        bus=bus,
        match_id="match.sudden-death.post-terminal",
        seed=17,
        loadout_a=load_loadout(_RED_PASSIVE),
        loadout_b=load_loadout(_BLUE_PASSIVE),
        max_ticks=None,
    )

    live = runner.run()

    assert live.end_reason is SOMatchEndReason.DRAW_MUTUAL_DESTRUCTION
    terminal_index = next(
        index for index, event in enumerate(captured) if event.event_type is SOEventType.MATCH_ENDED
    )
    after_terminal = [event.event_type for event in captured[terminal_index + 1 :]]
    assert SOEventType.MECH_DESTROYED not in after_terminal
    assert SOEventType.DAMAGE_APPLIED not in after_terminal
    # Both mechs are durably recorded destroyed, so nothing was dropped either.
    assert [event.event_type for event in captured].count(SOEventType.MECH_DESTROYED) == 2
    assert all(not mech.alive for mech in live.mech_states.values())
