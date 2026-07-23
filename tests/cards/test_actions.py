"""Pure and exhaustive card-category action mapping tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.cards import actions
from steel_onslaught.cards.actions import (
    ModelSOCardActionTranslation,
    ModelSOCardAttackParameters,
    ModelSOCardMovementParameters,
    ModelSOCardRotateParameters,
    ModelSOCardSpecialParameters,
    action_for_card,
    action_for_category,
    compile_card_action,
)
from steel_onslaught.contracts.card import (
    ModelSOCard,
    ModelSOCardEffect,
    SOCardCategory,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.pilots.schemas import SOPilotAction

_EXPECTED = {
    SOCardCategory.MOVEMENT: SOPilotAction.MOVE,
    SOCardCategory.ROTATE: SOPilotAction.MOVE,
    SOCardCategory.ATTACK: SOPilotAction.FIRE_WEAPON,
    SOCardCategory.VENT: SOPilotAction.VENT,
    SOCardCategory.SPECIAL: SOPilotAction.SWITCH_MODE,
    SOCardCategory.UTILITY: SOPilotAction.DEPLOY_UTILITY,
}


@pytest.mark.unit
def test_category_mapping_is_exhaustive_and_never_remain() -> None:
    assert set(_EXPECTED) == set(SOCardCategory)
    for category, expected in _EXPECTED.items():
        action = action_for_category(category)
        assert action is expected
        assert action is not SOPilotAction.REMAIN


@pytest.mark.unit
def test_action_for_card_is_only_a_pure_category_projection() -> None:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.attack.fire_primary",
        display_name="Fire Primary",
        category=SOCardCategory.ATTACK,
        priority=600,
        heat_cost=0,
        effect=ModelSOCardEffect(weapon_slot=0),
    )
    assert action_for_card(card) is SOPilotAction.FIRE_WEAPON
    assert action_for_card(card) is action_for_card(card)


def _card(category: SOCardCategory, *, card_id: str) -> ModelSOCard:
    effect = {
        SOCardCategory.MOVEMENT: ModelSOCardEffect(direction="toward_enemy", speed="full"),
        SOCardCategory.ROTATE: ModelSOCardEffect(direction="left"),
        SOCardCategory.ATTACK: ModelSOCardEffect(weapon_slot=2),
        SOCardCategory.VENT: ModelSOCardEffect(),
        SOCardCategory.SPECIAL: ModelSOCardEffect(target_mode=ModeId.EVASION),
    }[category]
    return ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id=card_id,
        display_name=card_id.rsplit(".", 1)[-1],
        category=category,
        priority=100,
        heat_cost=0,
        effect=effect,
    )


@pytest.mark.parametrize(
    ("category", "expected_action", "parameter_type"),
    [
        (SOCardCategory.MOVEMENT, SOPilotAction.MOVE, ModelSOCardMovementParameters),
        (SOCardCategory.ROTATE, SOPilotAction.MOVE, ModelSOCardRotateParameters),
        (SOCardCategory.ATTACK, SOPilotAction.FIRE_WEAPON, ModelSOCardAttackParameters),
        (SOCardCategory.VENT, SOPilotAction.VENT, None),
        (SOCardCategory.SPECIAL, SOPilotAction.SWITCH_MODE, ModelSOCardSpecialParameters),
    ],
)
def test_compiler_preserves_effect_shape_and_action_family(
    category: SOCardCategory,
    expected_action: SOPilotAction,
    parameter_type: type[object] | None,
) -> None:
    card = _card(category, card_id=f"card.test.{category.value}")
    compiled = compile_card_action(card)

    assert compiled.card_id == card.id
    assert compiled.category is category
    assert compiled.action is expected_action
    if parameter_type is None:
        assert compiled.parameters.kind == "vent"
    else:
        assert isinstance(compiled.parameters, parameter_type)

    if category is SOCardCategory.MOVEMENT:
        assert isinstance(compiled.parameters, ModelSOCardMovementParameters)
        assert compiled.parameters.direction == "toward_enemy"
        assert compiled.parameters.speed == "full"
    elif category is SOCardCategory.ROTATE:
        assert isinstance(compiled.parameters, ModelSOCardRotateParameters)
        assert compiled.parameters.direction == "left"
    elif category is SOCardCategory.ATTACK:
        assert isinstance(compiled.parameters, ModelSOCardAttackParameters)
        assert compiled.parameters.weapon_slot == 2
    elif category is SOCardCategory.SPECIAL:
        assert isinstance(compiled.parameters, ModelSOCardSpecialParameters)
        assert compiled.parameters.target_mode is ModeId.EVASION


def test_compiler_preserves_defensive_movement_without_collapsing_to_generic_move() -> None:
    card = ModelSOCard(
        schema_version="0.1.0",
        kind="steel_onslaught.card",
        id="card.test.defensive",
        display_name="Defensive",
        category=SOCardCategory.MOVEMENT,
        priority=10,
        heat_cost=0,
        effect=ModelSOCardEffect(direction="away_from_enemy", speed="full"),
    )
    compiled = compile_card_action(card)
    assert compiled.action is SOPilotAction.MOVE
    assert compiled.is_defensive is True
    assert isinstance(compiled.parameters, ModelSOCardMovementParameters)
    assert compiled.parameters.direction == "away_from_enemy"


def test_compiled_translation_is_closed_frozen_and_json_round_trippable() -> None:
    compiled = compile_card_action(_card(SOCardCategory.ATTACK, card_id="card.test.attack"))
    assert compiled.model_config["extra"] == "forbid"
    assert compiled.model_config["frozen"] is True
    assert ModelSOCardActionTranslation.model_validate_json(compiled.model_dump_json()) == compiled
    with pytest.raises(ValidationError):
        compiled.card_id = "card.test.changed"
    with pytest.raises(ValidationError):
        ModelSOCardActionTranslation.model_validate(
            {**compiled.model_dump(mode="json"), "unexpected": True}
        )
    with pytest.raises(ValidationError, match="does not match"):
        ModelSOCardActionTranslation(
            card_id=compiled.card_id,
            category=SOCardCategory.MOVEMENT,
            action=SOPilotAction.MOVE,
            parameters=compiled.parameters,
        )


def test_compiler_source_has_no_runtime_or_transport_authority() -> None:
    path = Path(inspect.getsourcefile(actions) or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_import_roots = {
        "asyncio",
        "aiohttp",
        "httpx",
        "omnibase_infra",
        "psycopg",
        "requests",
        "sqlite3",
        "yaml",
    }
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports.isdisjoint(forbidden_import_roots)
    source = path.read_text(encoding="utf-8")
    assert all(token not in source for token in ("EventFactory", "EventBus", "MatchRunner"))
