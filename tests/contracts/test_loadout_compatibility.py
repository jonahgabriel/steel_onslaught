"""Weapon/boiler/chassis compatibility enforcement — OMN-15594.

Before this suite, all three declared compatibility fields had zero consumers:
an illegal pairing assembled and ran silently.  Proven RED at ``7fad60b`` with
the pre-existing API only — ``_require_valid_budgets`` (the sole loadout gate
that existed) accepted both a siege mortar on a light scout chassis and a
compact boiler on a heavy chassis without raising.  ``test_red_at_base_*``
below reproduces that hole against the *new* gate so the RED case stays
executable rather than a claim in a commit message.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from steel_onslaught.contracts import compatibility as compatibility_module
from steel_onslaught.contracts.boiler import ModelSOBoilerSpec
from steel_onslaught.contracts.chassis import ModelSOChassisSpec
from steel_onslaught.contracts.compatibility import (
    EnumCompatibilityViolationKind,
    LoadoutCompatibilityError,
    validate_loadout_compatibility,
)
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.weapon import ModelSOWeaponSpec
from steel_onslaught.match.composition import load_loadout, load_match_contract_catalog
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import _require_legal_loadout

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "contracts_data"

# Every packaged loadout, recursively: the per-model subdirectories
# (qwen35/, glm/, vision_*/ ...) carry as many loadouts as the top level.
_PACKAGED_LOADOUTS = sorted(p for p in (_DATA / "loadouts").rglob("*.yaml"))

# The classification every declared compatibility field must carry.  A new
# field on any *Compatibility contract model lands in neither set and fails
# ``test_every_declared_compatibility_field_is_classified`` — that is the
# recurrence guard (OMN-15594 acceptance criterion 5).
_BINDING_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ModelSOWeaponCompatibility", "compatible_chassis_classes"),
        ("ModelSOBoilerCompatibility", "compatible_chassis_classes"),
        ("ModelSOChassisCompatibility", "weapon_classes"),
    }
)
_NON_BINDING_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ModelSOChassisCompatibility", "boiler_classes"),
        ("ModelSOChassisCompatibility", "mobility_classes"),
    }
)


@pytest.fixture(scope="module")
def catalog() -> MatchContractCatalog:
    return load_match_contract_catalog(_DATA)


def _load_yaml_spec(subdir: str, fname: str, model: type[BaseModel]) -> BaseModel:
    raw = (_DATA / subdir / fname).read_text(encoding="utf-8")
    return model.model_validate(yaml.safe_load(raw))


def _rebound(loadout: ModelSOLoadout, **overrides: object) -> ModelSOLoadout:
    """Re-validate a packaged loadout with fields replaced (never mutate in place)."""
    return ModelSOLoadout.model_validate({**loadout.model_dump(), **overrides})


@pytest.fixture(scope="module")
def light_loadout() -> ModelSOLoadout:
    """A packaged, currently-legal light-chassis loadout used as the mutation base."""
    return load_loadout(_DATA / "loadouts" / "example_aggressive_light.yaml")


# --------------------------------------------------------------------------
# RED cases — one per declared compatibility direction (acceptance criteria 2, 3)
# --------------------------------------------------------------------------


def test_red_at_base_weapon_rejects_incompatible_chassis_class(
    light_loadout: ModelSOLoadout,
) -> None:
    """weapon.compatibility.compatible_chassis_classes (weapon.py:54) is enforced.

    ``weapon.siege.artillery_mortar`` declares ``compatible_chassis_classes:
    [heavy]``; the loadout fields it on ``chassis.light.scout_mk1``.
    """
    chassis = _load_yaml_spec("chassis", "light_scout_mk1.yaml", ModelSOChassisSpec)
    boiler = _load_yaml_spec("boilers", "compact_v1.yaml", ModelSOBoilerSpec)
    mortar = _load_yaml_spec("weapons", "artillery_mortar.yaml", ModelSOWeaponSpec)
    assert isinstance(chassis, ModelSOChassisSpec)
    assert isinstance(boiler, ModelSOBoilerSpec)
    assert isinstance(mortar, ModelSOWeaponSpec)

    illegal = _rebound(
        light_loadout,
        id="loadout.test.illegal_weapon_chassis",
        modules={**light_loadout.modules.model_dump(), "weapons": (mortar.id,)},
    )
    violations = validate_loadout_compatibility(illegal, chassis, boiler, [mortar])

    kinds = [violation.kind for violation in violations]
    assert EnumCompatibilityViolationKind.WEAPON_CHASSIS_CLASS in kinds
    weapon_violation = next(
        v for v in violations if v.kind is EnumCompatibilityViolationKind.WEAPON_CHASSIS_CLASS
    )
    assert weapon_violation.declaring_id == mortar.id
    assert weapon_violation.offending_id == chassis.id
    assert weapon_violation.actual == "light"
    assert "heavy" in weapon_violation.declared


def test_red_at_base_chassis_rejects_unsupported_weapon_class(
    light_loadout: ModelSOLoadout,
) -> None:
    """chassis.compatibility.weapon_classes (chassis.py:37) is enforced.

    Isolated from the weapon->chassis direction: the synthetic chassis is
    ``light`` and the mortar *does* accept it, but the chassis does not mount
    ``siege``-class weapons.  Exactly one violation may fire.
    """
    packaged = _load_yaml_spec("chassis", "light_scout_mk1.yaml", ModelSOChassisSpec)
    assert isinstance(packaged, ModelSOChassisSpec)
    packaged_mortar = _load_yaml_spec("weapons", "artillery_mortar.yaml", ModelSOWeaponSpec)
    assert isinstance(packaged_mortar, ModelSOWeaponSpec)

    # Mortar that accepts light chassis — removes the weapon->chassis failure.
    mortar = ModelSOWeaponSpec.model_validate(
        {
            **packaged_mortar.model_dump(),
            "compatibility": {"compatible_chassis_classes": ("light",)},
        }
    )
    boiler = _load_yaml_spec("boilers", "compact_v1.yaml", ModelSOBoilerSpec)
    assert isinstance(boiler, ModelSOBoilerSpec)

    illegal = _rebound(
        light_loadout,
        id="loadout.test.illegal_chassis_weapon_class",
        modules={**light_loadout.modules.model_dump(), "weapons": (mortar.id,)},
    )
    violations = validate_loadout_compatibility(illegal, packaged, boiler, [mortar])

    assert [v.kind for v in violations] == [EnumCompatibilityViolationKind.CHASSIS_WEAPON_CLASS]
    assert violations[0].declaring_id == packaged.id
    assert violations[0].offending_id == mortar.id
    assert violations[0].actual == "siege"
    assert "siege" not in violations[0].declared


def test_red_at_base_boiler_rejects_incompatible_chassis_class(
    light_loadout: ModelSOLoadout,
) -> None:
    """boiler.compatibility.compatible_chassis_classes (boiler.py:21) is enforced.

    ``boiler.compact.v1`` declares ``[light, medium]``; the loadout fields it
    on ``chassis.heavy.ironclad_mk1``.  No weapons are fielded, so the boiler
    direction is the only one that can fire.
    """
    chassis = _load_yaml_spec("chassis", "heavy_ironclad_mk1.yaml", ModelSOChassisSpec)
    boiler = _load_yaml_spec("boilers", "compact_v1.yaml", ModelSOBoilerSpec)
    assert isinstance(chassis, ModelSOChassisSpec)
    assert isinstance(boiler, ModelSOBoilerSpec)

    illegal = _rebound(
        light_loadout,
        id="loadout.test.illegal_boiler_chassis",
        chassis_id=chassis.id,
        boiler_id=boiler.id,
        modules={**light_loadout.modules.model_dump(), "weapons": ()},
    )
    violations = validate_loadout_compatibility(illegal, chassis, boiler, [])

    assert [v.kind for v in violations] == [EnumCompatibilityViolationKind.BOILER_CHASSIS_CLASS]
    assert violations[0].declaring_id == boiler.id
    assert violations[0].offending_id == chassis.id
    assert violations[0].actual == "heavy"


def test_all_violations_are_reported_not_just_the_first(
    light_loadout: ModelSOLoadout,
) -> None:
    """Multi-violation, never first-fail — mirrors validate_loadout_budgets."""
    chassis = _load_yaml_spec("chassis", "light_scout_mk1.yaml", ModelSOChassisSpec)
    boiler = _load_yaml_spec("boilers", "industrial_bessemer_90.yaml", ModelSOBoilerSpec)
    mortar = _load_yaml_spec("weapons", "artillery_mortar.yaml", ModelSOWeaponSpec)
    assert isinstance(chassis, ModelSOChassisSpec)
    assert isinstance(boiler, ModelSOBoilerSpec)
    assert isinstance(mortar, ModelSOWeaponSpec)

    illegal = _rebound(
        light_loadout,
        id="loadout.test.illegal_everything",
        boiler_id=boiler.id,
        modules={**light_loadout.modules.model_dump(), "weapons": (mortar.id,)},
    )
    violations = validate_loadout_compatibility(illegal, chassis, boiler, [mortar])

    assert [v.kind for v in violations] == [
        EnumCompatibilityViolationKind.WEAPON_CHASSIS_CLASS,
        EnumCompatibilityViolationKind.CHASSIS_WEAPON_CLASS,
        EnumCompatibilityViolationKind.BOILER_CHASSIS_CLASS,
    ]


# --------------------------------------------------------------------------
# Fail-closed at match assembly (acceptance criterion 2)
# --------------------------------------------------------------------------


def test_assembly_gate_rejects_illegal_pairing_with_typed_error(
    catalog: MatchContractCatalog, light_loadout: ModelSOLoadout
) -> None:
    """The assembly gate raises LoadoutCompatibilityError, not a generic ValueError.

    This is the exact loadout that assembled silently at ``7fad60b``.
    """
    illegal = _rebound(
        light_loadout,
        id="loadout.test.assembly_illegal",
        modules={
            **light_loadout.modules.model_dump(),
            "weapons": ("weapon.siege.artillery_mortar",),
        },
    )

    with pytest.raises(LoadoutCompatibilityError) as excinfo:
        _require_legal_loadout(illegal, catalog)

    error = excinfo.value
    assert error.loadout_id == illegal.id
    assert {v.kind for v in error.violations} == {
        EnumCompatibilityViolationKind.WEAPON_CHASSIS_CLASS,
        EnumCompatibilityViolationKind.CHASSIS_WEAPON_CLASS,
    }
    assert "weapon.siege.artillery_mortar" in str(error)


def test_assembly_gate_still_enforces_budgets(catalog: MatchContractCatalog) -> None:
    """Folding compatibility into the gate did not drop the budget half."""
    over_slots = ModelSOLoadout.model_validate(
        {
            "id": "loadout.test.slot_overrun",
            "chassis_id": "chassis.light.scout_mk1",
            "boiler_id": "boiler.compact.v1",
            "pilot_id": "pilot.template.aggressive",
            "modules": {
                # All light-class, all legal on a light chassis: only the slot
                # budget can reject this.
                "weapons": (
                    "weapon.light.machine_gun",
                    "weapon.light.machine_gun_dmg3",
                    "weapon.light.machine_gun_dmg8",
                    "weapon.light.shrapnel_thrower",
                    "weapon.light.shrapnel_thrower_dmg3",
                    "weapon.light.shrapnel_thrower_dmg8",
                ),
            },
            "budgets": {
                "points_used": 0,
                "points_max": 100,
                "mass_used": 0,
                "mass_max": 1,
                "slots_used": 0,
                "slots_max": 1,
                "expected_heat_peak": 0,
                "expected_signature": 0,
            },
        }
    )

    with pytest.raises(ValueError, match="violates budgets") as excinfo:
        _require_legal_loadout(over_slots, catalog)
    assert not isinstance(excinfo.value, LoadoutCompatibilityError)


# --------------------------------------------------------------------------
# No false positives (acceptance criterion 4)
# --------------------------------------------------------------------------


def test_legal_pairing_produces_no_violations(catalog: MatchContractCatalog) -> None:
    """The check is not blanket-rejecting: a known-legal loadout passes clean."""
    legal = load_loadout(_DATA / "loadouts" / "example_aggressive_light.yaml")
    assert (
        validate_loadout_compatibility(
            legal,
            catalog.chassis[legal.chassis_id],
            catalog.boilers[legal.boiler_id],
            [catalog.weapons[wid] for wid in legal.modules.weapons],
        )
        == []
    )
    _require_legal_loadout(legal, catalog)


def test_packaged_loadout_corpus_is_non_empty() -> None:
    """Guards the parametrization below from silently covering zero files."""
    assert len(_PACKAGED_LOADOUTS) >= 53


@pytest.mark.parametrize(
    "loadout_path", _PACKAGED_LOADOUTS, ids=lambda p: str(p.relative_to(_DATA / "loadouts"))
)
def test_every_packaged_loadout_is_compatible(
    catalog: MatchContractCatalog, loadout_path: Path
) -> None:
    """Every shipped loadout stays legal under enforcement (no packaged default breaks).

    Surveyed clean before enforcement was written (53/53, zero violations); this
    test is what keeps it that way.
    """
    loadout = load_loadout(loadout_path)
    violations = validate_loadout_compatibility(
        loadout,
        catalog.chassis[loadout.chassis_id],
        catalog.boilers[loadout.boiler_id],
        [catalog.weapons[wid] for wid in loadout.modules.weapons],
    )
    assert violations == [], [v.describe() for v in violations]


# --------------------------------------------------------------------------
# Recurrence guard (acceptance criterion 5)
# --------------------------------------------------------------------------


def _compatibility_models() -> dict[str, type[BaseModel]]:
    """Every contract model whose name ends in 'Compatibility', discovered live.

    Discovered rather than listed so a compatibility block added to a *new*
    contract module is caught too.
    """
    import importlib
    import pkgutil

    import steel_onslaught.contracts as contracts_pkg

    found: dict[str, type[BaseModel]] = {}
    for module_info in pkgutil.iter_modules(contracts_pkg.__path__):
        module = importlib.import_module(f"{contracts_pkg.__name__}.{module_info.name}")
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and name.endswith("Compatibility")
            ):
                found[name] = obj
    return found


def test_every_declared_compatibility_field_is_classified() -> None:
    """No compatibility field may exist without being binding or marked non-binding.

    This is the recurrence guard: the defect was a field declared with nobody
    reading it.  A new field on any ``*Compatibility`` model fails here until
    it is either enforced or explicitly documented as non-binding.
    """
    declared = {
        (model_name, field_name)
        for model_name, model in _compatibility_models().items()
        for field_name in model.model_fields
    }
    classified = _BINDING_FIELDS | _NON_BINDING_FIELDS

    assert declared - classified == set(), (
        "unclassified compatibility field(s): enforce them in "
        "steel_onslaught.contracts.compatibility or mark them NON-BINDING at the "
        "declaration site, then add them to this test's classification sets"
    )
    assert classified - declared == set(), "classification names a field that no longer exists"


def test_binding_compatibility_fields_have_a_named_consumer() -> None:
    """Each binding field is read by the compatibility validator, by source inspection."""
    source = inspect.getsource(compatibility_module)
    for model_name, field_name in sorted(_BINDING_FIELDS):
        assert f".{field_name}" in source, (
            f"{model_name}.{field_name} is classified BINDING but "
            "steel_onslaught.contracts.compatibility never reads it"
        )


def test_non_binding_compatibility_fields_say_so_at_the_declaration_site() -> None:
    """A non-enforced field must not read as if it were enforced."""
    models = _compatibility_models()
    for model_name, field_name in sorted(_NON_BINDING_FIELDS):
        description = models[model_name].model_fields[field_name].description
        assert description is not None and "NON-BINDING" in description, (
            f"{model_name}.{field_name} is not enforced and must say NON-BINDING "
            "in its Field description"
        )
