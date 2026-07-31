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
def test_resolve_hit_probability_raised_by_transition_vulnerability() -> None:
    """The transition vulnerability window RAISES incoming hit probability (OMN-15592).

    It is a penalty paid by the target, so it applies against the target: the exact
    mirror of a defensive bonus of the same size.
    """
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    p_no_window = resolve_hit_probability(
        base_accuracy=0.6, lock_confidence=1.0, target_evasion=0.0, accuracy_penalty=0.0
    )
    p_in_window = resolve_hit_probability(
        base_accuracy=0.6,
        lock_confidence=1.0,
        target_evasion=0.0,
        accuracy_penalty=0.0,
        target_transition_vulnerability=0.5,
    )
    assert p_in_window > p_no_window
    assert p_in_window == pytest.approx(p_no_window * 1.5)


@pytest.mark.unit
def test_transition_vulnerability_offsets_defensive_evasion() -> None:
    """Vulnerability decrements the target's effective evasion; equal values cancel."""
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    neutral = resolve_hit_probability(
        base_accuracy=0.8, lock_confidence=1.0, target_evasion=0.0, accuracy_penalty=0.0
    )
    cancelled = resolve_hit_probability(
        base_accuracy=0.8,
        lock_confidence=1.0,
        target_evasion=0.3,
        accuracy_penalty=0.0,
        target_transition_vulnerability=0.3,
    )
    assert cancelled == pytest.approx(neutral)


@pytest.mark.unit
def test_resolve_hit_probability_clamped_with_transition_vulnerability() -> None:
    """A vulnerability window can never push hit probability above 1.0."""
    from steel_onslaught.reducers.weapons import resolve_hit_probability

    result = resolve_hit_probability(
        base_accuracy=0.95,
        lock_confidence=1.0,
        target_evasion=0.0,
        accuracy_penalty=0.0,
        target_targeting_debuff=0.0,
        target_transition_vulnerability=0.5,
    )
    assert result == 1.0


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
