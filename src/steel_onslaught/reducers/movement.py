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
  - siege mode: -1 (floored at 1)
  - all others: 0
Max cells per move: ``effective_speed * ticks_consumed``.
Pressure cost: 1 per cell of Chebyshev distance (exactly equal to the distance).

Invariant enforcement (raises ReducerError)
-------------------------------------------
- ``match_id_mismatch``: event.match_id != reducer's match_id.
- ``mech_not_found``: subject mech_id absent from match state.
- ``invalid_facing``: facing < 0 or >= 360.
- ``position_mismatch``: payload "from" != mech's current position.
- ``speed_exceeded``: Chebyshev distance > effective_speed * ticks_consumed.
- ``pressure_cost_mismatch``: payload pressure_consumed != Chebyshev distance.
- ``insufficient_pressure``: boiler pressure_current < pressure_consumed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.reducers.errors import ReducerError

# ---------------------------------------------------------------------------
# Mode speed modifiers
# ---------------------------------------------------------------------------

_MODE_SPEED_DELTA: dict[str, int] = {
    "evasion": 1,
    "siege": -1,
}
_MIN_EFFECTIVE_SPEED = 1


def _effective_speed(mech: ModelSOMechRuntimeState) -> int:
    delta = _MODE_SPEED_DELTA.get(mech.current_mode, 0)
    return max(_MIN_EFFECTIVE_SPEED, mech.base_speed + delta)


def _chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    return max(abs(b.x - a.x), abs(b.y - a.y))


# ---------------------------------------------------------------------------
# Typed payload models (internal — not exported as public API)
# ---------------------------------------------------------------------------


class _SpawnPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    position: ModelSOPosition
    facing: int = Field(ge=0)


class _MovementPayload(BaseModel):
    from_pos: ModelSOPosition = Field(alias="from")
    to_pos: ModelSOPosition = Field(alias="to")
    ticks_consumed: int = Field(gt=0)
    pressure_consumed: int = Field(ge=0)

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _ticks_positive(self) -> _MovementPayload:
        if self.ticks_consumed < 1:
            raise ValueError("ticks_consumed must be >= 1")
        return self


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerMovement:
    """Folds MECH_SPAWNED and MOVEMENT_RESOLVED events into ``ModelSOMatchState``.

    Construct one per match. The reducer is stateless between applies — the
    current ``ModelSOMatchState`` is passed in at construction and updated on
    each ``apply`` call.
    """

    def __init__(self, match_id: str, state: ModelSOMatchState) -> None:
        self._match_id = match_id
        self._state = state

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

        payload = _SpawnPayload.model_validate(event.payload)
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

        payload = _MovementPayload.model_validate(event.payload)
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

        # 2. Pressure cost must equal Chebyshev distance (1 per cell).
        distance = _chebyshev(from_pos, to_pos)
        if pressure_consumed != distance:
            raise ReducerError(
                f"pressure_cost_mismatch: Chebyshev distance is {distance}, "
                f"but pressure_consumed={pressure_consumed}"
            )

        # 3. Speed limit: distance <= effective_speed * ticks_consumed.
        speed = _effective_speed(mech)
        max_cells = speed * ticks_consumed
        if distance > max_cells:
            raise ReducerError(
                f"speed_exceeded: mech {mech_id!r} has effective_speed={speed}, "
                f"ticks_consumed={ticks_consumed} (max {max_cells} cells), "
                f"but move covers {distance} cells"
            )

        # 4. Pressure availability.
        if mech.boiler.pressure_current < pressure_consumed:
            raise ReducerError(
                f"insufficient_pressure: mech {mech_id!r} has "
                f"pressure_current={mech.boiler.pressure_current}, "
                f"but move costs {pressure_consumed}"
            )

        # 5. Apply: update position + deduct pressure.
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
