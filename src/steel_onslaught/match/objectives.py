"""Pure objective-control determination — Phase 4 (objectives + VP victory).

One deterministic rule, shared by the canonical fold (VP scoring) and the
pilot observation builder (what the LLMs see), so "who controls this cell"
can never diverge between scoring and perception:

  - a living mech CONTESTS an objective when its folded position is within
    ``OBJECTIVE_CONTROL_RADIUS`` (Chebyshev) of the objective cell;
  - exactly one player contesting -> that player CONTROLS the objective;
  - both players contesting -> CONTESTED, nobody scores;
  - nobody contesting -> UNCLAIMED, nobody scores.

The radius is 1 (the cell plus its king-move ring) because two mechs can
never share a cell: an exact-cell rule would make mutual contest physically
impossible and hand every objective to whoever arrives first.
"""

from __future__ import annotations

from typing import Literal

from steel_onslaught.match.state import ModelSOMatchState, ModelSOMechRuntimeState
from steel_onslaught.pilots.schemas import ModelSOPosition

OBJECTIVE_CONTROL_RADIUS = 1
"""Chebyshev distance within which a living mech contests an objective."""

SOObjectiveControlView = Literal["own", "enemy", "contested", "unclaimed"]


def _chebyshev(a: ModelSOPosition, b: ModelSOPosition) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def contesting_mechs(
    cell: ModelSOPosition,
    state: ModelSOMatchState,
) -> tuple[ModelSOMechRuntimeState, ...]:
    """Living mechs within the control radius, in deterministic mech_id order."""

    return tuple(
        sorted(
            (
                mech
                for mech in state.living_mechs()
                if _chebyshev(mech.position, cell) <= OBJECTIVE_CONTROL_RADIUS
            ),
            key=lambda mech: mech.mech_id,
        )
    )


def objective_controller(
    cell: ModelSOPosition,
    state: ModelSOMatchState,
) -> ModelSOMechRuntimeState | None:
    """Return the sole controlling mech, or ``None`` when contested/unclaimed.

    Control requires exactly ONE player among the contesting mechs.  When a
    single player fields several contesting mechs the nearest (then lowest
    ``mech_id``) represents the control — deterministic under the duel roster
    and under any future multi-mech roster.
    """

    contesting = contesting_mechs(cell, state)
    if not contesting:
        return None
    players = {mech.player_id for mech in contesting}
    if len(players) != 1:
        return None
    return min(contesting, key=lambda mech: (_chebyshev(mech.position, cell), mech.mech_id))


def classify_control(
    cell: ModelSOPosition,
    state: ModelSOMatchState,
    *,
    viewer_player_id: str,
) -> SOObjectiveControlView:
    """The viewer-relative control label rendered into pilot observations."""

    contesting = contesting_mechs(cell, state)
    if not contesting:
        return "unclaimed"
    players = {mech.player_id for mech in contesting}
    if len(players) != 1:
        return "contested"
    return "own" if next(iter(players)) == viewer_player_id else "enemy"


__all__ = [
    "OBJECTIVE_CONTROL_RADIUS",
    "SOObjectiveControlView",
    "classify_control",
    "contesting_mechs",
    "objective_controller",
]
