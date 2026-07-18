"""Strict, closed, frozen card contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.card import ModelSOCard, ModelSOCardEffect, SOCardCategory


def _card(**overrides: object) -> ModelSOCard:
    data: dict[str, object] = {
        "schema_version": "0.1.0",
        "kind": "steel_onslaught.card",
        "id": "card.attack.fire_primary",
        "display_name": "Fire Primary",
        "category": "attack",
        "priority": 600,
        "heat_cost": 0,
        "effect": {"weapon_slot": 0},
    }
    data.update(overrides)
    return ModelSOCard.model_validate(data)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("category", "effect"),
    (
        ("movement", {"direction": "toward_enemy", "speed": "full"}),
        ("rotate", {"direction": "left"}),
        ("attack", {"weapon_slot": 0}),
        ("vent", {}),
        ("special", {"target_mode": "assault"}),
    ),
)
def test_each_closed_category_accepts_exactly_its_effect_shape(
    category: str, effect: dict[str, object]
) -> None:
    card = _card(category=category, effect=effect)
    assert card.category is SOCardCategory(category)


@pytest.mark.unit
def test_category_effect_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires effect fields"):
        _card(category="movement", effect={"direction": "toward_enemy"})
    with pytest.raises(ValidationError, match="requires effect fields"):
        _card(category="vent", effect={"weapon_slot": 0})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("category", "effect"),
    (
        ("movement", {"direction": "arbitrary_direction", "speed": "full"}),
        ("movement", {"direction": "toward_enemy", "speed": "arbitrary_speed"}),
        ("special", {"target_mode": "invalid"}),
        ("attack", {"weapon_slot": -1}),
        ("attack", {"weapon_slot": True}),
    ),
)
def test_effect_values_are_closed_and_strict(category: str, effect: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _card(category=category, effect=effect)


@pytest.mark.unit
def test_card_tags_ids_and_values_are_strict() -> None:
    for overrides in (
        {"schema_version": None},
        {"kind": "wrong"},
        {"id": "not-a-card"},
        {"display_name": ""},
        {"priority": "600"},
        {"priority": True},
        {"heat_cost": -1},
        {"category": "unknown"},
    ):
        with pytest.raises(ValidationError):
            _card(**overrides)


@pytest.mark.unit
def test_required_tags_effect_and_unknown_fields_fail_closed() -> None:
    base = _card().model_dump()
    for field in ("schema_version", "kind", "effect"):
        data = dict(base)
        del data[field]
        with pytest.raises(ValidationError):
            ModelSOCard.model_validate(data)
    with pytest.raises(ValidationError):
        _card(unknown=True)


@pytest.mark.unit
def test_card_and_nested_effect_are_frozen() -> None:
    card = _card()
    with pytest.raises(ValidationError):
        card.priority = 1
    with pytest.raises(ValidationError):
        card.effect.weapon_slot = 1
    assert card.effect == ModelSOCardEffect(weapon_slot=0)
