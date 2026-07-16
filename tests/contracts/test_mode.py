"""Tests for mode contract model + transition rules (Task 12)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.mode import (
    ModeId,
    ModelSOModeSpec,
    ModelSOModeSwitchIntentPayload,
    ModelSOModeTransition,
    ModelSOModeTransitionCompletedPayload,
    ModelSOModeTransitionCosts,
    ModelSOModeTransitionStartedPayload,
)

CONTRACTS_DATA = Path(__file__).parent.parent.parent / "contracts_data" / "modes"


# ---------------------------------------------------------------------------
# Helper: load a spec YAML
# ---------------------------------------------------------------------------


def _load_mode(filename: str) -> ModelSOModeSpec:
    with open(CONTRACTS_DATA / filename) as f:
        return ModelSOModeSpec.model_validate(yaml.safe_load(f))


def _load_all_transitions() -> list[ModelSOModeTransition]:
    """Load all 6 transition YAMLs (one per ordered cross-mode pair)."""
    transitions_dir = CONTRACTS_DATA / "transitions"
    results: list[ModelSOModeTransition] = []
    for yaml_path in sorted(transitions_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            results.append(ModelSOModeTransition.model_validate(yaml.safe_load(f)))
    return results


# ---------------------------------------------------------------------------
# Mode spec tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_three_mode_specs_validate() -> None:
    recon = _load_mode("recon.yaml")
    assault = _load_mode("assault.yaml")
    evasion = _load_mode("evasion.yaml")

    assert recon.id == "mode.recon"
    assert assault.id == "mode.assault"
    assert evasion.id == "mode.evasion"


@pytest.mark.unit
def test_recon_has_active_systems() -> None:
    recon = _load_mode("recon.yaml")
    assert len(recon.active_systems) > 0
    # sensors should be active in recon
    assert "sensor" in recon.active_systems


@pytest.mark.unit
def test_assault_has_weapon_in_active_systems() -> None:
    assault = _load_mode("assault.yaml")
    assert "weapon" in assault.active_systems


@pytest.mark.unit
def test_evasion_has_mobility_in_active_systems() -> None:
    evasion = _load_mode("evasion.yaml")
    assert "mobility" in evasion.active_systems


@pytest.mark.unit
def test_mode_passive_modifiers_are_dict() -> None:
    for fname in ("recon.yaml", "assault.yaml", "evasion.yaml"):
        spec = _load_mode(fname)
        assert isinstance(spec.passive_modifiers, dict)


@pytest.mark.unit
def test_mode_default_priorities_are_list() -> None:
    for fname in ("recon.yaml", "assault.yaml", "evasion.yaml"):
        spec = _load_mode(fname)
        assert isinstance(spec.default_priorities, list)
        assert len(spec.default_priorities) > 0


# ---------------------------------------------------------------------------
# Mode transition tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_nine_transitions_exist() -> None:
    """Verify all 6 cross-mode ordered pairs are covered.

    The plan says "all 9 ordered pairs", but with 3 modes there are 3x2=6
    valid non-self-loop directed pairs.  We enforce all 6.
    """
    modes = list(ModeId)
    expected_pairs = {(f, t) for f in modes for t in modes if f != t}
    transitions = _load_all_transitions()
    found_pairs = {(t.from_mode, t.to_mode) for t in transitions}
    assert expected_pairs == found_pairs, (
        f"Expected transitions {expected_pairs}, found {found_pairs}"
    )


@pytest.mark.unit
def test_transitions_costs_are_positive() -> None:
    for transition in _load_all_transitions():
        assert transition.costs.pressure >= 0
        assert transition.costs.heat >= 0
        assert transition.costs.transition_ticks >= 1


@pytest.mark.unit
def test_transition_restrictions_cannot_switch_heat_above_is_below_rupture() -> None:
    """cannot_switch_if_heat_above must be < rupture_threshold (100) per plan invariant."""
    for transition in _load_all_transitions():
        if transition.restrictions.cannot_switch_if_heat_above is not None:
            val = transition.restrictions.cannot_switch_if_heat_above
            assert val < 100, (
                f"Transition {transition.from_mode}->{transition.to_mode}: "
                f"cannot_switch_if_heat_above={val} must be < rupture_threshold (100)"
            )


@pytest.mark.unit
def test_transition_vulnerability_fields_non_negative() -> None:
    for transition in _load_all_transitions():
        assert transition.vulnerability.evasion_penalty_during_transition >= 0.0
        assert transition.vulnerability.sensor_dropout_ticks >= 0


# ---------------------------------------------------------------------------
# Model-level validation invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mode_spec_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.weapon",  # wrong kind
                "id": "mode.recon",
                "display_name": "Recon",
                "active_systems": ["sensor"],
                "passive_modifiers": {},
                "default_priorities": ["observe"],
            }
        )


@pytest.mark.unit
def test_mode_spec_rejects_bad_id_format() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode",
                "id": "modeXrecon",  # must match mode.<name>
                "display_name": "Recon",
                "active_systems": ["sensor"],
                "passive_modifiers": {},
                "default_priorities": ["observe"],
            }
        )


@pytest.mark.unit
def test_mode_spec_rejects_well_formed_but_unknown_mode_id() -> None:
    with pytest.raises(ValidationError, match="closed combat modes"):
        ModelSOModeSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode",
                "id": "mode.siege",
                "display_name": "Siege",
                "active_systems": ["weapon"],
                "passive_modifiers": {},
                "default_priorities": ["fire"],
            }
        )


@pytest.mark.unit
def test_mode_spec_rejects_empty_active_systems() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode",
                "id": "mode.recon",
                "display_name": "Recon",
                "active_systems": [],  # must be non-empty
                "passive_modifiers": {},
                "default_priorities": ["observe"],
            }
        )


@pytest.mark.unit
def test_mode_spec_rejects_empty_default_priorities() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeSpec.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode",
                "id": "mode.recon",
                "display_name": "Recon",
                "active_systems": ["sensor"],
                "passive_modifiers": {},
                "default_priorities": [],  # must be non-empty
            }
        )


@pytest.mark.unit
def test_transition_rejects_cannot_switch_if_heat_above_at_rupture() -> None:
    """Plan invariant: cannot_switch_if_heat_above >= rupture_threshold is rejected."""
    with pytest.raises(ValidationError):
        ModelSOModeTransition.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode_transition",
                "from_mode": "recon",
                "to_mode": "assault",
                "costs": {"pressure": 5, "heat": 2, "transition_ticks": 2},
                "restrictions": {
                    "minimum_lock_ticks_after_switch": 3,
                    "cannot_switch_if_heat_above": 100,  # == rupture_threshold -> rejected
                    "cannot_switch_if_boiler_disabled": True,
                },
                "vulnerability": {
                    "evasion_penalty_during_transition": 0.3,
                    "sensor_dropout_ticks": 1,
                },
            }
        )


@pytest.mark.unit
def test_transition_rejects_self_transition() -> None:
    """from_mode == to_mode is invalid (no self-loops)."""
    with pytest.raises(ValidationError):
        ModelSOModeTransition.model_validate(
            {
                "schema_version": "0.1.0",
                "kind": "steel_onslaught.mode_transition",
                "from_mode": "recon",
                "to_mode": "recon",  # self-loop
                "costs": {"pressure": 0, "heat": 0, "transition_ticks": 1},
                "restrictions": {
                    "minimum_lock_ticks_after_switch": 0,
                    "cannot_switch_if_heat_above": None,
                    "cannot_switch_if_boiler_disabled": False,
                },
                "vulnerability": {
                    "evasion_penalty_during_transition": 0.0,
                    "sensor_dropout_ticks": 0,
                },
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("field", ["from_mode", "to_mode"])
def test_transition_rejects_unknown_mode_endpoint(field: str) -> None:
    raw = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.mode_transition",
        "from_mode": "recon",
        "to_mode": "assault",
        "costs": {"pressure": 0, "heat": 0, "transition_ticks": 1},
        "restrictions": {
            "minimum_lock_ticks_after_switch": 0,
            "cannot_switch_if_heat_above": None,
            "cannot_switch_if_boiler_disabled": False,
        },
        "vulnerability": {
            "evasion_penalty_during_transition": 0.0,
            "sensor_dropout_ticks": 0,
        },
    }
    raw[field] = "siege"

    with pytest.raises(ValidationError):
        ModelSOModeTransition.model_validate(raw)


@pytest.mark.unit
def test_mode_switch_intent_payload_is_closed() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeSwitchIntentPayload.model_validate({"target_mode": "siege"})
    with pytest.raises(ValidationError):
        ModelSOModeSwitchIntentPayload.model_validate(
            {"target_mode": "assault", "fallback_mode": "recon"}
        )


@pytest.mark.unit
def test_mode_transition_started_payload_is_closed() -> None:
    valid = {
        "from_mode": "recon",
        "to_mode": "assault",
        "costs": {"pressure": 1, "heat": 2, "transition_ticks": 3},
        "sensor_dropout_ticks": 1,
        "evasion_penalty": 0.2,
    }
    with pytest.raises(ValidationError):
        ModelSOModeTransitionStartedPayload.model_validate({**valid, "to_mode": "siege"})
    with pytest.raises(ValidationError):
        ModelSOModeTransitionStartedPayload.model_validate({**valid, "legacy": True})


@pytest.mark.unit
def test_mode_transition_completed_payload_is_closed() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeTransitionCompletedPayload.model_validate(
            {
                "from_mode": "recon",
                "new_mode": "siege",
                "mode_lock_until": 4,
            }
        )


@pytest.mark.unit
def test_transition_costs_transition_ticks_at_least_one() -> None:
    with pytest.raises(ValidationError):
        ModelSOModeTransitionCosts.model_validate(
            {"pressure": 0, "heat": 0, "transition_ticks": 0}  # must be >= 1
        )


@pytest.mark.unit
def test_mode_round_trip_json() -> None:
    """ModelSOModeSpec must survive JSON round-trip losslessly."""
    recon = _load_mode("recon.yaml")
    blob = recon.model_dump_json()
    parsed = ModelSOModeSpec.model_validate_json(blob)
    assert parsed == recon


@pytest.mark.unit
def test_transition_round_trip_json() -> None:
    transitions = _load_all_transitions()
    for t in transitions:
        blob = t.model_dump_json()
        parsed = ModelSOModeTransition.model_validate_json(blob)
        assert parsed == t
