"""Weapon firing + hit resolution reducer — Task 24.

Flow:
    1. Pilot emits ``WEAPON_FIRE_INTENT(weapon_id, target_id)``.
    2. ``validate_weapon_fire_intent`` checks: weapon ready (cooldown=0),
       pressure >= cost, target in range, target alive.
    3. ``interpolate_accuracy`` samples the weapon's accuracy curve at the
       current distance (linear interpolation between breakpoints).
    4. ``resolve_hit_probability`` combines base accuracy with lock confidence
       and target evasion, then clamps to [0, 1].
    5. ``roll_hit`` consumes a sub-seed from ``MatchRng`` and returns True/False.
    6. ``WEAPON_FIRED`` is always emitted (hit or miss).
    7. If hit: ``HIT_RESOLVED`` is emitted with raw damage.

All stochastic resolution goes through ``MatchRng.for_event`` so that two
replays with the same seed and event sequence produce bit-identical outcomes.
"""

from __future__ import annotations

from steel_onslaught.match.rng import MatchRng
from steel_onslaught.reducers.errors import ReducerError


def interpolate_accuracy(
    curve: list[tuple[int, float]],
    distance: int,
) -> float:
    """Linearly interpolate the accuracy curve at ``distance``.

    Args:
        curve:    List of ``(range_bin, hit_probability)`` tuples, sorted by
                  range_bin ascending (required by callers).
        distance: Chebyshev distance to the target in grid cells.

    Returns:
        Hit probability in [0, 1].  Values below the first breakpoint use
        the first probability; values beyond the last breakpoint clamp to the
        last probability.
    """
    if not curve:
        return 0.0

    # Sort defensively — callers should already pass sorted curves.
    sorted_curve = sorted(curve, key=lambda p: p[0])

    # Clamp to the first breakpoint.
    if distance <= sorted_curve[0][0]:
        return float(sorted_curve[0][1])

    # Clamp to the last breakpoint.
    if distance >= sorted_curve[-1][0]:
        return float(sorted_curve[-1][1])

    # Find the surrounding segment and interpolate.
    for i in range(len(sorted_curve) - 1):
        r0, p0 = sorted_curve[i]
        r1, p1 = sorted_curve[i + 1]
        if r0 <= distance <= r1:
            t = (distance - r0) / (r1 - r0)
            return float(p0 + t * (p1 - p0))

    # Unreachable, but satisfies the type checker.
    return float(sorted_curve[-1][1])


def resolve_hit_probability(
    base_accuracy: float,
    lock_confidence: float,
    target_evasion: float,
    accuracy_penalty: float,
    target_targeting_debuff: float = 0.0,
) -> float:
    """Combine accuracy modifiers and clamp the result to [0, 1].

    Args:
        base_accuracy:    Accuracy from the weapon's curve at current distance.
        lock_confidence:  Sensor lock confidence in [0, 1].
        target_evasion:   Target evasion value in [0, 1]; subtracts from result.
        accuracy_penalty: Multiplicative penalty from overload etc. in [0, 1];
                          applied as ``1 - accuracy_penalty`` multiplier.
        target_targeting_debuff:
                          Chaff aura on the target in [0, 1] (Phase 2), applied
                          as a ``1 - target_targeting_debuff`` multiplier — it
                          composes multiplicatively exactly like ``target_evasion``.
                          Default ``0.0`` leaves the existing curve unchanged.

    Returns:
        Final hit probability clamped to [0, 1].
    """
    raw = (
        base_accuracy
        * lock_confidence
        * (1.0 - accuracy_penalty)
        * (1.0 - target_evasion)
        * (1.0 - target_targeting_debuff)
    )
    return max(0.0, min(1.0, raw))


def validate_weapon_fire_intent(
    *,
    weapon_id: str,
    pressure_cost: int,
    current_pressure: int,
    weapon_cooldown: int,
    distance: int,
    weapon_range: int,
    target_alive: bool,
) -> None:
    """Validate a ``WEAPON_FIRE_INTENT`` before consuming any resources.

    Raises:
        ReducerError: with a stable snake_case code prefix on any violation:
            - ``insufficient_pressure`` — not enough pressure for the weapon.
            - ``weapon_on_cooldown`` — weapon cooldown has not expired.
            - ``target_out_of_range`` — target exceeds weapon range.
            - ``target_not_alive`` — target mech is dead.
    """
    if current_pressure < pressure_cost:
        raise ReducerError(
            f"insufficient_pressure: weapon {weapon_id!r} costs {pressure_cost} pressure "
            f"but current pressure is {current_pressure}"
        )
    if weapon_cooldown > 0:
        raise ReducerError(
            f"weapon_on_cooldown: weapon {weapon_id!r} has {weapon_cooldown} ticks remaining"
        )
    if distance > weapon_range:
        raise ReducerError(
            f"target_out_of_range: distance {distance} exceeds weapon range {weapon_range} "
            f"for weapon {weapon_id!r}"
        )
    if not target_alive:
        raise ReducerError(f"target_not_alive: cannot fire {weapon_id!r} at a destroyed target")


def roll_hit(
    *,
    rng: MatchRng,
    tick: int,
    mech_id: str,
    hit_probability: float,
) -> bool:
    """Roll for hit using a deterministic sub-seed from ``MatchRng``.

    Args:
        rng:             The match-scoped ``MatchRng`` instance.
        tick:            Current match tick.
        mech_id:         Firing mech's identifier.
        hit_probability: Resolved hit probability in [0, 1].

    Returns:
        ``True`` if the shot connects, ``False`` on a miss.
    """
    sub_rng = rng.for_event(tick=tick, mech_id=mech_id, kind="weapon_fire")
    return sub_rng.random() < hit_probability
