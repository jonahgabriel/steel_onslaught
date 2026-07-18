"""Spawn + position + movement reducer — Task 19.

Handles:
- ``MECH_SPAWNED``: places a mech at its declared spawn position and facing.
- ``MOVEMENT_RESOLVED``: validates speed limits (Chebyshev distance), pressure
  availability, and position continuity; then updates position + boiler.

Movement model
--------------
Distance metric: Chebyshev — ``max(|dx|, |dy|)``.
Speed limit: ``effective_speed = base_speed + mode_speed_modifier``.
  - evasion mode: +1
  - recon and assault modes: 0
Max cells per move: ``effective_speed * ticks_consumed``.
Pressure cost: 1 per cell of Chebyshev distance (exactly equal to the distance).

Invariant enforcement (raises ReducerError)
-------------------------------------------
- ``match_id_mismatch``: event.match_id != reducer's match_id.
- ``mech_not_found``: subject mech_id absent from match state.
- ``invalid_facing``: facing < 0 or >= 360.
- ``position_mismatch``: payload "from" != mech's current position.
- ``arena_bounds``: payload destination lies outside the injected arena.
- ``obstacle_blocked``: canonical Chebyshev traversal crosses authoritative terrain.
- ``speed_exceeded``: Chebyshev distance > effective_speed * ticks_consumed.
- ``pressure_cost_mismatch``: payload pressure_consumed != Chebyshev distance.
- ``insufficient_pressure``: boiler pressure_current < pressure_consumed.
"""

from __future__ import annotations

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMechSpawnedPayload,
    ModelSOMovementResolvedPayload,
)
from steel_onslaught.match.geometry import chebyshev_line
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError

# ---------------------------------------------------------------------------
# Mode speed modifiers
# ---------------------------------------------------------------------------

_MODE_SPEED_DELTA: dict[ModeId, int] = {
    ModeId.RECON: 0,
    ModeId.ASSAULT: 0,
    ModeId.EVASION: 1,
}
if set(_MODE_SPEED_DELTA) != set(ModeId):  # pragma: no cover - import-time invariant
    raise RuntimeError("movement speed mapping must cover every ModeId exactly once")
_MIN_EFFECTIVE_SPEED = 1


def mode_effective_speed(base_speed: int, mode: ModeId) -> int:
    """Effective speed for *base_speed* in *mode* (floored at 1)."""
    return max(_MIN_EFFECTIVE_SPEED, base_speed + _MODE_SPEED_DELTA[mode])


def effective_speed(mech: ModelSOMechRuntimeState) -> int:
    """Effective speed of *mech* given its current mode."""
    return mode_effective_speed(mech.base_speed, mech.current_mode)


def chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    """Chebyshev (king-move) distance between two grid positions."""
    return max(abs(b.x - a.x), abs(b.y - a.y))


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerMovement:
    """Folds MECH_SPAWNED and MOVEMENT_RESOLVED events into ``ModelSOMatchState``.

    Construct one per match. The reducer is stateless between applies — the
    current ``ModelSOMatchState`` is passed in at construction and updated on
    each ``apply`` call.
    """

    def __init__(
        self,
        match_id: str,
        state: ModelSOMatchState,
        *,
        arena: ModelSOCurrentLiveArenaSnapshot,
    ) -> None:
        self._match_id = match_id
        self._state = state
        self._arena = arena

    @property
    def state(self) -> ModelSOMatchState:
        return self._state

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> ModelSOMatchState:
        """Fold one event; returns the (possibly updated) match state.

        Non-movement events are passed through without modifying state so the
        replay engine can feed the full ledger through every reducer.
        """
        if event.match_id != self._match_id:
            raise ReducerError(
                f"match_id_mismatch: reducer owns {self._match_id!r}, "
                f"event carries {event.match_id!r}"
            )
        match event.event_type:
            case SOEventType.MECH_SPAWNED:
                self._apply_mech_spawned(event)
            case SOEventType.MOVEMENT_RESOLVED:
                self._apply_movement_resolved(event)
            case _:
                pass  # not a movement event — ignore
        return self._state

    # -- event handlers -------------------------------------------------------

    def _apply_mech_spawned(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        mech = self._require_mech(mech_id)

        payload = ModelSOMechSpawnedPayload.model_validate(event.payload)
        facing = payload.facing
        if facing < 0 or facing >= 360:
            raise ReducerError(f"invalid_facing: facing must be in [0, 360), got {facing}")

        updated_mech = mech.model_copy(
            update={
                "position": payload.position,
                "facing": facing,
            }
        )
        self._replace_mech(updated_mech)

    def _apply_movement_resolved(self, event: ModelSOEventEnvelope) -> None:
        mech_id = event.subject.mech_id
        mech = self._require_mech(mech_id)

        payload = ModelSOMovementResolvedPayload.model_validate(event.payload)
        from_pos = payload.from_pos
        to_pos = payload.to_pos
        ticks_consumed = payload.ticks_consumed
        pressure_consumed = payload.pressure_consumed

        # 1. "from" must match the mech's current position.
        if from_pos != mech.position:
            raise ReducerError(
                f"position_mismatch: mech {mech_id!r} is at {mech.position}, "
                f"but MOVEMENT_RESOLVED payload declares from={from_pos}"
            )

        # 2. The authoritative arena rejects shaped canonical movement at ingress.
        if not (0 <= to_pos.x < self._arena.size and 0 <= to_pos.y < self._arena.size):
            raise ReducerError(
                f"arena_bounds: mech {mech_id!r} destination "
                f"{(to_pos.x, to_pos.y)} is outside [0, {self._arena.size})"
            )
        obstacles = self._arena.obstacle_cells
        blocked_cell = next(
            (cell for cell in chebyshev_line(from_pos, to_pos) if cell in obstacles),
            None,
        )
        if blocked_cell is not None:
            raise ReducerError(
                f"obstacle_blocked: mech {mech_id!r} movement path crosses {blocked_cell}"
            )

        # 3. Pressure cost must equal Chebyshev distance (1 per cell).
        distance = chebyshev(from_pos, to_pos)
        if pressure_consumed != distance:
            raise ReducerError(
                f"pressure_cost_mismatch: Chebyshev distance is {distance}, "
                f"but pressure_consumed={pressure_consumed}"
            )

        # 4. Speed limit: distance <= effective_speed * ticks_consumed.
        speed = effective_speed(mech)
        max_cells = speed * ticks_consumed
        if distance > max_cells:
            raise ReducerError(
                f"speed_exceeded: mech {mech_id!r} has effective_speed={speed}, "
                f"ticks_consumed={ticks_consumed} (max {max_cells} cells), "
                f"but move covers {distance} cells"
            )

        # 5. Pressure availability.
        if mech.boiler.pressure_current < pressure_consumed:
            raise ReducerError(
                f"insufficient_pressure: mech {mech_id!r} has "
                f"pressure_current={mech.boiler.pressure_current}, "
                f"but move costs {pressure_consumed}"
            )

        # 6. Apply: update position + deduct pressure.
        new_boiler = mech.boiler.model_copy(
            update={
                "pressure_current": mech.boiler.pressure_current - pressure_consumed,
            }
        )
        updated_mech = mech.model_copy(
            update={
                "position": to_pos,
                "boiler": new_boiler,
            }
        )
        self._replace_mech(updated_mech)

    # -- helpers --------------------------------------------------------------

    def _require_mech(self, mech_id: str) -> ModelSOMechRuntimeState:
        mech = self._state.mech_states.get(mech_id)
        if mech is None:
            raise ReducerError(f"mech_not_found: no mech {mech_id!r} in match {self._match_id!r}")
        return mech

    def _replace_mech(self, mech: ModelSOMechRuntimeState) -> None:
        new_mechs = dict(self._state.mech_states)
        new_mechs[mech.mech_id] = mech
        self._state = self._state.model_copy(update={"mech_states": new_mechs})
