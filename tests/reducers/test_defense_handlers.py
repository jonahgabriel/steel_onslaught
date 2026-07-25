"""Tests for the defense-resolution handler pack (armor seam refactor).

Covers the seam introduced to replace the hardcoded ``compute_armor_reduction``
call in ``match/runner.py`` with an allowlisted, content-addressed handler
pack — mirroring the discipline already proven for ``cards/rules.py`` and
``cards/utility_handlers.py``.

Byte-identical-behavior invariant: ``HandlerArmorV1.handle`` must agree with
``compute_armor_reduction`` on every input, since the handler is a pure
adapter over that (independently tested) function, not a reimplementation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSODefenseHandlerPackBinding
from steel_onslaught.contracts.weapon import WeaponDamageType
from steel_onslaught.reducers.damage import compute_armor_reduction
from steel_onslaught.reducers.defense_handlers import (
    DEFAULT_DEFENSE_HANDLER_IDS,
    DefenseHandlerSelectionError,
    DefenseResolutionRegistry,
    HandlerArmorV1,
    ModelSODefenseHandlerDescriptor,
    ModelSODefenseResolutionRequest,
    ModelSODefenseResolutionResult,
    default_defense_registry,
)

# ---------------------------------------------------------------------------
# HandlerArmorV1 <-> compute_armor_reduction byte-identical behavior
# ---------------------------------------------------------------------------

_CASES: tuple[tuple[int, int, WeaponDamageType], ...] = (
    (20, 10, WeaponDamageType.STANDARD),
    (20, 100, WeaponDamageType.PRESSURE),
    (20, 100, WeaponDamageType.HEAT),
    (5, 100, WeaponDamageType.PRESSURE),
    (10, 50, WeaponDamageType.STANDARD),
    (15, 0, WeaponDamageType.PRESSURE),
    (8, 16, WeaponDamageType.STANDARD),
    (0, 20, WeaponDamageType.STANDARD),
    (10, 10, WeaponDamageType.HEAT),
)


@pytest.mark.unit
@pytest.mark.parametrize(("damage_raw", "armor_value", "weapon_damage_type"), _CASES)
def test_handler_armor_v1_matches_compute_armor_reduction(
    damage_raw: int, armor_value: int, weapon_damage_type: WeaponDamageType
) -> None:
    """The allowlisted handler must agree exactly with the underlying reducer."""
    expected = compute_armor_reduction(
        damage_raw=damage_raw,
        armor_value=armor_value,
        weapon_damage_type=weapon_damage_type,
    )
    result = HandlerArmorV1().handle(
        ModelSODefenseResolutionRequest(
            damage_raw=damage_raw,
            armor_value=armor_value,
            weapon_damage_type=weapon_damage_type,
        )
    )
    assert result.absorbed == expected.absorbed
    assert result.armor_after == expected.armor_after


@pytest.mark.unit
def test_handler_armor_v1_descriptor_identity() -> None:
    assert HandlerArmorV1.descriptor.handler_id == "defense.armor.v1"
    assert HandlerArmorV1.descriptor.handler_id in DEFAULT_DEFENSE_HANDLER_IDS


# ---------------------------------------------------------------------------
# Request/Result models — closed and frozen
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_request_model_is_frozen_and_closed() -> None:
    request = ModelSODefenseResolutionRequest(
        damage_raw=10, armor_value=5, weapon_damage_type=WeaponDamageType.STANDARD
    )
    with pytest.raises(ValidationError):
        request.damage_raw = 99
    with pytest.raises(ValidationError):
        ModelSODefenseResolutionRequest(
            damage_raw=10,
            armor_value=5,
            weapon_damage_type=WeaponDamageType.STANDARD,
            extra_field="nope",  # type: ignore[call-arg]
        )


@pytest.mark.unit
def test_result_model_is_frozen_and_closed() -> None:
    result = ModelSODefenseResolutionResult(absorbed=3, armor_after=7)
    with pytest.raises(ValidationError):
        result.absorbed = 0
    with pytest.raises(ValidationError):
        ModelSODefenseResolutionResult(absorbed=3, armor_after=7, extra_field="nope")  # type: ignore[call-arg]


@pytest.mark.unit
def test_request_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        ModelSODefenseResolutionRequest(
            damage_raw=-1, armor_value=5, weapon_damage_type=WeaponDamageType.STANDARD
        )
    with pytest.raises(ValidationError):
        ModelSODefenseResolutionRequest(
            damage_raw=10, armor_value=-1, weapon_damage_type=WeaponDamageType.STANDARD
        )


# ---------------------------------------------------------------------------
# DefenseResolutionRegistry — allowlist discipline
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_registry_pack_id_and_single_default_handler() -> None:
    registry = default_defense_registry()
    assert registry.pack_id == "defense.resolution.v1"
    assert [h.descriptor.handler_id for h in registry.handlers] == ["defense.armor.v1"]
    assert registry.active.descriptor.handler_id == "defense.armor.v1"


@pytest.mark.unit
def test_select_empty_raises() -> None:
    registry = default_defense_registry()
    with pytest.raises(DefenseHandlerSelectionError, match="must be non-empty"):
        registry.select(())


@pytest.mark.unit
def test_select_duplicate_raises() -> None:
    registry = default_defense_registry()
    with pytest.raises(DefenseHandlerSelectionError, match="duplicate"):
        registry.select(("defense.armor.v1", "defense.armor.v1"))


@pytest.mark.unit
def test_select_unknown_id_raises() -> None:
    registry = default_defense_registry()
    with pytest.raises(DefenseHandlerSelectionError, match="not registered"):
        registry.select(("defense.shield.v1",))


@pytest.mark.unit
def test_select_valid_subset_returns_narrowed_registry() -> None:
    registry = default_defense_registry()
    narrowed = registry.select(("defense.armor.v1",))
    assert narrowed.pack_id == registry.pack_id
    assert narrowed.active.descriptor.handler_id == "defense.armor.v1"


@pytest.mark.unit
def test_registry_rejects_duplicate_ids_at_construction() -> None:
    with pytest.raises(DefenseHandlerSelectionError, match="duplicate"):
        DefenseResolutionRegistry(
            pack_id="defense.resolution.v1",
            handlers=(HandlerArmorV1(), HandlerArmorV1()),
        )


class _FakeShieldHandler:
    """Minimal second handler used only to exercise multi-handler edges."""

    descriptor = ModelSODefenseHandlerDescriptor(
        handler_id="defense.shield.v1",
        version="1",
        description="Test-only fake shield handler (not shipped).",
    )

    def handle(self, payload: ModelSODefenseResolutionRequest) -> ModelSODefenseResolutionResult:
        return ModelSODefenseResolutionResult(absorbed=0, armor_after=payload.armor_value)


@pytest.mark.unit
def test_active_fails_closed_with_zero_handlers() -> None:
    registry = DefenseResolutionRegistry(pack_id="defense.resolution.v1", handlers=())
    with pytest.raises(DefenseHandlerSelectionError, match="exactly one"):
        _ = registry.active


@pytest.mark.unit
def test_active_fails_closed_with_multiple_handlers() -> None:
    registry = DefenseResolutionRegistry(
        pack_id="defense.resolution.v1",
        handlers=(HandlerArmorV1(), _FakeShieldHandler()),
    )
    with pytest.raises(DefenseHandlerSelectionError, match="exactly one"):
        _ = registry.active


# ---------------------------------------------------------------------------
# Provenance — content-addressed identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provenance_matches_active_pack() -> None:
    registry = default_defense_registry()
    provenance = registry.provenance()
    assert provenance.pack_id == registry.pack_id
    assert [h.handler_id for h in provenance.handlers] == ["defense.armor.v1"]
    assert len(provenance.content_sha256) == 64


@pytest.mark.unit
def test_provenance_content_sha256_changes_with_handler_set() -> None:
    default_provenance = default_defense_registry().provenance()
    extended = DefenseResolutionRegistry(
        pack_id="defense.resolution.v1",
        handlers=(HandlerArmorV1(), _FakeShieldHandler()),
    ).provenance()
    assert default_provenance.content_sha256 != extended.content_sha256


@pytest.mark.unit
def test_provenance_content_sha256_is_deterministic() -> None:
    first = default_defense_registry().provenance()
    second = default_defense_registry().provenance()
    assert first.content_sha256 == second.content_sha256
    assert first == second


# ---------------------------------------------------------------------------
# Overlay binding — closed, pattern-validated, unique handler_ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overlay_binding_accepts_valid_selection() -> None:
    binding = ModelSODefenseHandlerPackBinding(
        kind="defense_resolution_handlers",
        pack_id="defense.resolution.v1",
        handler_ids=("defense.armor.v1",),
    )
    assert binding.handler_ids == ("defense.armor.v1",)


@pytest.mark.unit
def test_overlay_binding_rejects_duplicate_handler_ids() -> None:
    with pytest.raises(ValidationError, match="handler_ids must be unique"):
        ModelSODefenseHandlerPackBinding(
            kind="defense_resolution_handlers",
            pack_id="defense.resolution.v1",
            handler_ids=("defense.armor.v1", "defense.armor.v1"),
        )


@pytest.mark.unit
def test_overlay_binding_rejects_empty_handler_ids() -> None:
    with pytest.raises(ValidationError):
        ModelSODefenseHandlerPackBinding(
            kind="defense_resolution_handlers",
            pack_id="defense.resolution.v1",
            handler_ids=(),
        )


@pytest.mark.unit
def test_overlay_binding_rejects_unknown_extra_field() -> None:
    with pytest.raises(ValidationError):
        ModelSODefenseHandlerPackBinding(
            kind="defense_resolution_handlers",
            pack_id="defense.resolution.v1",
            handler_ids=("defense.armor.v1",),
            unexpected="nope",  # type: ignore[call-arg]
        )
