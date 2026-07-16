"""Per-tick initiative ordering — a deterministic combat mechanic, not a coin-flip.

Initiative determines the order in which mechs' intents resolve each tick.
It is a real game state derived from chassis agility and boiler condition,
so it varies meaningfully across mechs and across ticks:

  - Lighter chassis act before heavier ones (agility).
  - A boiler running hot (at/above redline) slows a mech (penalty).
  - An overloaded boiler severely slows a mech (the cascade has bitten).
  - A boiler with ample pressure (responsive reserves) speeds a mech (bonus).

This replaces a fixed insertion-order resolution (which gave a systematic
first-actor disadvantage in same-tick kill exchanges — see the learning-loop
bias fix) with a state-driven one. It is fully deterministic: identical match
state produces identical initiative ordering, and ties are broken by a seeded
``MatchRng`` sub-seed so equal-initiative mechs don't get a fixed ordering.

Pure: the scoring function has no side effects and no I/O. The runner applies
its ordering to the intent-resolution loop.
"""

from __future__ import annotations

from steel_onslaught.match.rng import MatchRng
from steel_onslaught.match.state import ModelSOMechRuntimeState

# Base initiative by chassis class: lighter = higher = acts first.
_BASE_INITIATIVE: dict[str, int] = {
    "light": 30,
    "medium": 20,
    "heavy": 10,
}

# Boiler-condition modifiers (applied to the base initiative).
_PRESSURE_BONUS_THRESHOLD = 0.80  # >= 80% of pressure_maximum → bonus
_PRESSURE_BONUS = 5
_REDLINE_PENALTY = 8  # heat at/above redline threshold → sluggish
_OVERLOAD_PENALTY = 15  # boiler overloaded → severely slowed


def initiative_score(mech: ModelSOMechRuntimeState) -> int:
    """Compute one mech's initiative score for the current tick.

    Higher score = acts earlier. Derived purely from chassis class + boiler
    state, so it reflects the mech's current combat condition.

    Args:
        mech: The mech's runtime state (chassis class, boiler pressure/heat/status).

    Returns:
        An integer initiative score. Deterministic for identical mech state.
    """
    score = _BASE_INITIATIVE.get(mech.chassis_class, 0)

    boiler = mech.boiler
    # Pressure responsiveness: ample reserves let the mech act crisply.
    if (
        boiler.pressure_maximum > 0
        and boiler.pressure_current >= _PRESSURE_BONUS_THRESHOLD * boiler.pressure_maximum
    ):
        score += _PRESSURE_BONUS
    # Heat strain: a redline-hot boiler fights sluggishly.
    if boiler.status_redline:
        score -= _REDLINE_PENALTY
    # Overload: the failure cascade has bitten — the mech is severely slowed.
    if mech.overloaded:
        score -= _OVERLOAD_PENALTY

    return score


def order_by_initiative(
    mechs: list[ModelSOMechRuntimeState],
    *,
    rng: MatchRng,
    tick: int,
) -> list[ModelSOMechRuntimeState]:
    """Order mechs by initiative (highest first); break ties with a seeded RNG.

    The tiebreak uses a per-tick ``MatchRng`` sub-seed (kind="initiative") so
    equal-initiative mechs resolve in a deterministic-but-not-fixed order —
    neither side gets a systematic advantage from a tie.

    Args:
        mechs: The living mechs to order.
        rng:   The match's seeded RNG (for deterministic tiebreaks).
        tick:  The current tick (feeds the tiebreak sub-seed).

    Returns:
        A new list ordered highest-initiative-first. Stable for identical state.
    """
    tiebreak_rng = rng.for_event(tick=tick, mech_id="*", kind="initiative")

    # Decorate-sort-undecorate: pair each mech with (score, random tiebreak key)
    # so sort is deterministic and ties break by the seeded RNG.
    decorated = [(initiative_score(mech), tiebreak_rng.random(), mech) for mech in mechs]
    # Sort by score descending; the random tiebreak key orders equal scores.
    decorated.sort(key=lambda triple: (-triple[0], triple[1]))
    return [mech for _, _, mech in decorated]
