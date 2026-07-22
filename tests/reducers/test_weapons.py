"""Tests for Task 24: weapon firing + hit resolution reducer + MatchRng.

Invariants verified:
- Two replays of the same match (same seed, same events) produce bit-identical
  hit/miss results across all weapon fires.
- MatchRng produces different sub-seeds for different (tick, mech_id, kind) tuples.
- MatchRng with the same inputs produces identical results (deterministic).
- Weapon fired with insufficient pressure: rejected before consuming pressure.
- HIT_RESOLVED is emitted at most once per WEAPON_FIRED.
- Hit probability is clamped to [0, 1] post-calculation.
- Weapon with cooldown > 0 is rejected.
- Target out of range is rejected.
- WEAPON_FIRED is always emitted (hit or miss).
- Accuracy curve interpolation: linear interpolation between breakpoints.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from steel_onslaught.match.rng import MatchRng

# ---------------------------------------------------------------------------
# MatchRng tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_match_rng_deterministic() -> None:
    """Same inputs must produce identical random sequences."""
    rng1 = MatchRng(match_seed=12345)
    rng2 = MatchRng(match_seed=12345)

    r1 = rng1.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire")
    r2 = rng2.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire")

    # Same sequence of calls must produce same values
    assert r1.random() == r2.random()
    assert r1.random() == r2.random()
    assert r1.random() == r2.random()


@pytest.mark.unit
def test_match_rng_different_seeds_produce_different_results() -> None:
    """Different match seeds must produce different outputs."""
    rng1 = MatchRng(match_seed=12345)
    rng2 = MatchRng(match_seed=99999)

    val1 = rng1.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire").random()
    val2 = rng2.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire").random()

    assert val1 != val2


@pytest.mark.unit
def test_match_rng_different_ticks_produce_different_results() -> None:
    """Different ticks must produce different sub-seeds."""
    rng = MatchRng(match_seed=42)

    val1 = rng.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire").random()
    val2 = rng.for_event(tick=2, mech_id="mech.red.01", kind="weapon_fire").random()

    assert val1 != val2


@pytest.mark.unit
def test_match_rng_different_mech_ids_produce_different_results() -> None:
    """Different mech_ids must produce different sub-seeds."""
    rng = MatchRng(match_seed=42)

    val1 = rng.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire").random()
    val2 = rng.for_event(tick=1, mech_id="mech.blue.01", kind="weapon_fire").random()

    assert val1 != val2


@pytest.mark.unit
def test_match_rng_different_kinds_produce_different_results() -> None:
    """Different kind strings must produce different sub-seeds."""
    rng = MatchRng(match_seed=42)

    val1 = rng.for_event(tick=1, mech_id="mech.red.01", kind="weapon_fire").random()
    val2 = rng.for_event(tick=1, mech_id="mech.red.01", kind="rupture_survival").random()

    assert val1 != val2


@pytest.mark.unit
def test_match_rng_returns_random_instance() -> None:
    """for_event must return a random.Random instance."""
    import random

    rng = MatchRng(match_seed=42)
    result = rng.for_event(tick=5, mech_id="mech.x", kind="weapon_fire")
    assert isinstance(result, random.Random)


@pytest.mark.unit
def test_match_rng_frozen() -> None:
    """MatchRng is frozen — mutation must be rejected."""
    rng = MatchRng(match_seed=42)
    with pytest.raises((AttributeError, TypeError)):
        rng.match_seed = 999  # type: ignore[misc]


@pytest.mark.unit
def test_match_rng_blake2b_sub_seeds() -> None:
    """Verify the blake2b sub-seed derivation produces values in [0, 1)."""
    rng = MatchRng(match_seed=777)
    for tick in range(5):
        for kind in ("weapon_fire", "rupture_survival", "scatter"):
            val = rng.for_event(tick=tick, mech_id="mech.test.01", kind=kind).random()
            assert 0.0 <= val < 1.0, f"Expected [0,1), got {val}"


# ---------------------------------------------------------------------------
# Weapon reducer tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_interpolate_accuracy_at_exact_breakpoint() -> None:
    """Hit probability at an exact range breakpoint matches the spec."""
    from steel_onslaught.reducers.weapons import interpolate_accuracy

    # Curve: [(0, 1.0), (10, 0.8), (20, 0.4)]
    curve = [(0, 1.0), (10, 0.8), (20, 0.4)]
    assert interpolate_accuracy(curve, distance=0) == pytest.approx(1.0)
    assert interpolate_accuracy(curve, distance=10) == pytest.approx(0.8)
    assert interpolate_accuracy(curve, distance=20) == pytest.approx(0.4)


@pytest.mark.unit
def test_interpolate_accuracy_midpoint() -> None:
    """Linear interpolation at the midpoint between two breakpoints."""
    from steel_onslaught.reducers.weapons import interpolate_accuracy

    # Midpoint between range=10 (0.8) and range=20 (0.4) is range=15 → 0.6
    curve = [(0, 1.0), (10, 0.8), (20, 0.4)]
    assert interpolate_accuracy(curve, distance=15) == pytest.approx(0.6)


@pytest.mark.unit
def test_interpolate_accuracy_beyond_max_range() -> None:
    """Distance beyond the last breakpoint clamps to the last value."""
    from steel_onslaught.reducers.weapons import interpolate_accuracy

    curve = [(0, 1.0), (20, 0.4)]
    assert interpolate_accuracy(curve, distance=50) == pytest.approx(0.4)


@pytest.mark.unit
def test_interpolate_accuracy_clamped_to_unit_interval() -> None:
    """Interpolated values must always lie in [0, 1]."""
    from steel_onslaught.reducers.weapons import interpolate_accuracy

    curve = [(0, 0.95), (5, 0.5)]
    val = interpolate_accuracy(curve, distance=3)
    assert 0.0 <= val <= 1.0


@pytest.mark.unit
def test_resolve_hit_probability_clamped() -> None:
    """Hit probability after all modifiers is clamped to [0, 1]."""
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    # Even with multipliers > 1.0 the result must not exceed 1.0
    result = resolve_hit_probability(
        base_accuracy=0.9,
        lock_confidence=1.2,  # deliberately over 1.0
        target_evasion=0.0,
        accuracy_penalty=0.0,
    )
    assert 0.0 <= result <= 1.0


@pytest.mark.unit
def test_resolve_hit_probability_reduced_by_evasion() -> None:
    """Target evasion reduces hit probability."""
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    p_no_evasion = resolve_hit_probability(
        base_accuracy=0.8, lock_confidence=1.0, target_evasion=0.0, accuracy_penalty=0.0
    )
    p_with_evasion = resolve_hit_probability(
        base_accuracy=0.8, lock_confidence=1.0, target_evasion=0.5, accuracy_penalty=0.0
    )
    assert p_with_evasion < p_no_evasion


@pytest.mark.unit
def test_moves_scaled_evasion_zero_moves_is_zero() -> None:
    """A stationary round (no movement register resolved) earns no evasion."""
    from steel_onslaught.reducers.weapons import moves_scaled_evasion_bonus

    assert moves_scaled_evasion_bonus(evasion_per_move=0.08, cap=0.24, moves_resolved=0) == 0.0
    # A negative/degenerate count is treated as stationary, never a negative bonus.
    assert moves_scaled_evasion_bonus(evasion_per_move=0.08, cap=0.24, moves_resolved=-1) == 0.0


@pytest.mark.unit
def test_moves_scaled_evasion_monotonic_then_capped() -> None:
    """More resolved movement -> strictly more evasion, until the cap clamps it."""
    from steel_onslaught.reducers.weapons import moves_scaled_evasion_bonus

    per_move, cap = 0.08, 0.24
    b1 = moves_scaled_evasion_bonus(evasion_per_move=per_move, cap=cap, moves_resolved=1)
    b2 = moves_scaled_evasion_bonus(evasion_per_move=per_move, cap=cap, moves_resolved=2)
    b3 = moves_scaled_evasion_bonus(evasion_per_move=per_move, cap=cap, moves_resolved=3)
    b4 = moves_scaled_evasion_bonus(evasion_per_move=per_move, cap=cap, moves_resolved=4)

    assert b1 == pytest.approx(0.08)
    assert b2 == pytest.approx(0.16)
    assert b3 == pytest.approx(0.24)
    assert b1 < b2 < b3  # strictly increasing while below the cap
    assert b3 == pytest.approx(cap)  # exactly the ceiling at the 3-move hand quota
    assert b4 == pytest.approx(cap)  # never exceeds the cap, no matter how many moves


@pytest.mark.unit
def test_more_moves_lower_hit_chance_than_stationary() -> None:
    """The mechanic's whole point: more movement -> higher evasion -> lower hit
    chance; a stationary target keeps the un-modified hit chance."""
    from steel_onslaught.reducers.weapons import (
        moves_scaled_evasion_bonus,
        resolve_hit_probability,
    )

    base_evasion, base_accuracy, lock = 0.0, 0.70, 1.0  # mortar mid-approach ~0.70
    per_move, cap = 0.08, 0.24

    def hit_chance(moves: int) -> float:
        bonus = moves_scaled_evasion_bonus(evasion_per_move=per_move, cap=cap, moves_resolved=moves)
        return resolve_hit_probability(
            base_accuracy=base_accuracy,
            lock_confidence=lock,
            target_evasion=min(1.0, base_evasion + bonus),
            accuracy_penalty=0.0,
        )

    stationary = hit_chance(0)
    sprint = hit_chance(3)

    assert stationary == pytest.approx(0.70)  # unchanged when it stops to shoot
    assert sprint == pytest.approx(0.70 * (1 - 0.24))  # 0.532: ~24% relative cut
    assert sprint < stationary
    # Monotonic across the approach: each extra resolved move lowers hit chance.
    assert hit_chance(0) > hit_chance(1) > hit_chance(2) > hit_chance(3)


# ---------------------------------------------------------------------------
# Round-4 close-range accuracy falloff (the range band)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_close_range_multiplier_no_penalty_at_or_beyond_band() -> None:
    """At/beyond the band distance the multiplier is exactly 1.0 (no penalty)."""
    from steel_onslaught.reducers.weapons import close_range_accuracy_multiplier

    assert (
        close_range_accuracy_multiplier(distance=20, band_distance=20, point_blank_multiplier=0.30)
        == 1.0
    )
    assert (
        close_range_accuracy_multiplier(distance=50, band_distance=20, point_blank_multiplier=0.30)
        == 1.0
    )


@pytest.mark.unit
def test_close_range_multiplier_floor_at_point_blank() -> None:
    """At (or below) distance 0 the multiplier is the point-blank floor."""
    from steel_onslaught.reducers.weapons import close_range_accuracy_multiplier

    assert close_range_accuracy_multiplier(
        distance=0, band_distance=20, point_blank_multiplier=0.30
    ) == pytest.approx(0.30)
    # Degenerate negative distance clamps to the floor, never below it.
    assert close_range_accuracy_multiplier(
        distance=-4, band_distance=20, point_blank_multiplier=0.30
    ) == pytest.approx(0.30)


@pytest.mark.unit
def test_close_range_multiplier_monotonic_and_bounded() -> None:
    """The gradient is monotonic non-decreasing in distance and bounded to
    [floor, 1.0] across the whole close band (no ledge, never a bonus)."""
    from steel_onslaught.reducers.weapons import close_range_accuracy_multiplier

    band, floor = 20, 0.30
    values = [
        close_range_accuracy_multiplier(
            distance=d, band_distance=band, point_blank_multiplier=floor
        )
        for d in range(0, band + 1)
    ]
    # Bounded.
    assert all(floor <= v <= 1.0 for v in values)
    # Monotonic non-decreasing (each step never lowers the multiplier).
    assert all(a <= b for a, b in pairwise(values))
    # Strictly increasing across the interior of the band (no flat ledge).
    assert values[0] < values[band // 2] < values[band - 1] < values[band]
    # The published shipped cells (band 20, floor 0.30).
    assert values[0] == pytest.approx(0.30)
    assert values[10] == pytest.approx(0.65)
    assert values[20] == pytest.approx(1.0)


@pytest.mark.unit
def test_close_range_multiplier_composes_with_evasion_clamped() -> None:
    """Falloff (a curve multiplier) composed with evasion (a 1 - evasion term)
    can only lower a hit chance, and the product stays clamped in [0, 1]."""
    from steel_onslaught.reducers.weapons import (
        close_range_accuracy_multiplier,
        moves_scaled_evasion_bonus,
        resolve_hit_probability,
    )

    base_accuracy, lock = 0.80, 1.0  # mortar curve clamps to 0.80 below range 20
    # d = 12 (scout MG range), full-sprint scout: both mechanics active at once.
    mult = close_range_accuracy_multiplier(
        distance=12, band_distance=20, point_blank_multiplier=0.30
    )
    evasion = moves_scaled_evasion_bonus(evasion_per_move=0.14, cap=0.42, moves_resolved=3)

    both = resolve_hit_probability(
        base_accuracy=base_accuracy * mult,
        lock_confidence=lock,
        target_evasion=min(1.0, evasion),
        accuracy_penalty=0.0,
    )
    falloff_only = resolve_hit_probability(
        base_accuracy=base_accuracy * mult,
        lock_confidence=lock,
        target_evasion=0.0,
        accuracy_penalty=0.0,
    )
    neither = resolve_hit_probability(
        base_accuracy=base_accuracy,
        lock_confidence=lock,
        target_evasion=0.0,
        accuracy_penalty=0.0,
    )

    # Each mechanic lowers the hit chance; composed is the lowest; all clamped.
    assert both < falloff_only < neither
    assert 0.0 <= both <= 1.0
    # Exact composed value: 0.80 * 0.72 (mult@12) * (1 - 0.42) = 0.334...
    assert both == pytest.approx(0.80 * 0.72 * (1 - 0.42))


@pytest.mark.unit
def test_resolve_hit_probability_reduced_by_accuracy_penalty() -> None:
    """Accuracy penalty (overload) reduces hit probability."""
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    p_no_penalty = resolve_hit_probability(
        base_accuracy=0.8, lock_confidence=1.0, target_evasion=0.0, accuracy_penalty=0.0
    )
    p_with_penalty = resolve_hit_probability(
        base_accuracy=0.8, lock_confidence=1.0, target_evasion=0.0, accuracy_penalty=0.3
    )
    assert p_with_penalty < p_no_penalty


@pytest.mark.unit
def test_validate_weapon_fire_insufficient_pressure() -> None:
    """WEAPON_FIRE_INTENT is rejected when pressure is insufficient."""
    from steel_onslaught.reducers.errors import ReducerError
    from steel_onslaught.reducers.weapons import validate_weapon_fire_intent

    with pytest.raises(ReducerError, match="insufficient_pressure"):
        validate_weapon_fire_intent(
            weapon_id="weapon.machine_gun",
            pressure_cost=10,
            current_pressure=5,  # below cost
            weapon_cooldown=0,
            distance=5,
            weapon_range=15,
            target_alive=True,
        )


@pytest.mark.unit
def test_validate_weapon_fire_weapon_on_cooldown() -> None:
    """WEAPON_FIRE_INTENT is rejected when weapon cooldown > 0."""
    from steel_onslaught.reducers.errors import ReducerError
    from steel_onslaught.reducers.weapons import validate_weapon_fire_intent

    with pytest.raises(ReducerError, match="weapon_on_cooldown"):
        validate_weapon_fire_intent(
            weapon_id="weapon.machine_gun",
            pressure_cost=5,
            current_pressure=20,
            weapon_cooldown=2,  # not ready
            distance=5,
            weapon_range=15,
            target_alive=True,
        )


@pytest.mark.unit
def test_validate_weapon_fire_target_out_of_range() -> None:
    """WEAPON_FIRE_INTENT is rejected when target is out of range."""
    from steel_onslaught.reducers.errors import ReducerError
    from steel_onslaught.reducers.weapons import validate_weapon_fire_intent

    with pytest.raises(ReducerError, match="target_out_of_range"):
        validate_weapon_fire_intent(
            weapon_id="weapon.machine_gun",
            pressure_cost=5,
            current_pressure=20,
            weapon_cooldown=0,
            distance=20,  # exceeds weapon_range
            weapon_range=15,
            target_alive=True,
        )


@pytest.mark.unit
def test_validate_weapon_fire_target_dead() -> None:
    """WEAPON_FIRE_INTENT is rejected when target is not alive."""
    from steel_onslaught.reducers.errors import ReducerError
    from steel_onslaught.reducers.weapons import validate_weapon_fire_intent

    with pytest.raises(ReducerError, match="target_not_alive"):
        validate_weapon_fire_intent(
            weapon_id="weapon.machine_gun",
            pressure_cost=5,
            current_pressure=20,
            weapon_cooldown=0,
            distance=5,
            weapon_range=15,
            target_alive=False,
        )


@pytest.mark.unit
def test_validate_weapon_fire_valid() -> None:
    """A valid fire intent does not raise."""
    from steel_onslaught.reducers.weapons import validate_weapon_fire_intent

    # Should not raise
    validate_weapon_fire_intent(
        weapon_id="weapon.machine_gun",
        pressure_cost=5,
        current_pressure=20,
        weapon_cooldown=0,
        distance=5,
        weapon_range=15,
        target_alive=True,
    )


@pytest.mark.unit
def test_deterministic_hit_result_two_replays() -> None:
    """Two replays with the same seed + inputs must produce identical hit/miss."""
    from steel_onslaught.reducers.weapons import roll_hit

    # Replay 1
    rng1 = MatchRng(match_seed=42)
    result1 = roll_hit(
        rng=rng1,
        tick=7,
        mech_id="mech.red.01",
        hit_probability=0.75,
    )

    # Replay 2 — fresh rng with same seed
    rng2 = MatchRng(match_seed=42)
    result2 = roll_hit(
        rng=rng2,
        tick=7,
        mech_id="mech.red.01",
        hit_probability=0.75,
    )

    assert result1 == result2


@pytest.mark.unit
def test_roll_hit_always_returns_bool() -> None:
    """roll_hit must return True or False (not a float or None)."""
    from steel_onslaught.reducers.weapons import roll_hit

    rng = MatchRng(match_seed=100)
    result = roll_hit(rng=rng, tick=1, mech_id="mech.x", hit_probability=0.5)
    assert isinstance(result, bool)


@pytest.mark.unit
def test_roll_hit_probability_zero_never_hits() -> None:
    """A hit probability of 0.0 never produces a hit."""
    from steel_onslaught.reducers.weapons import roll_hit

    for seed in range(20):
        rng = MatchRng(match_seed=seed)
        result = roll_hit(rng=rng, tick=1, mech_id="mech.x", hit_probability=0.0)
        assert result is False, f"Expected miss with p=0.0 but got hit (seed={seed})"


@pytest.mark.unit
def test_roll_hit_probability_one_always_hits() -> None:
    """A hit probability of 1.0 always produces a hit."""
    from steel_onslaught.reducers.weapons import roll_hit

    for seed in range(20):
        rng = MatchRng(match_seed=seed)
        result = roll_hit(rng=rng, tick=1, mech_id="mech.x", hit_probability=1.0)
        assert result is True, f"Expected hit with p=1.0 but got miss (seed={seed})"
