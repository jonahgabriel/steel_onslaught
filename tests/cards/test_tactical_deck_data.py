"""Contract and runtime-shape checks for the tactical card pack."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.cards.actions import (
    ModelSOCardAttackParameters,
    ModelSOCardMovementParameters,
    ModelSOCardSpecialParameters,
    compile_card_action,
)
from steel_onslaught.cards.dealer import DealerCompute, ModelSODeckState
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.contracts.deck import ModelSODeck
from steel_onslaught.contracts.mode import ModeId, ModelSOModeSwitchIntentPayload
from steel_onslaught.events.card_payloads import ModelSOPlanCommittedPayload, ModelSOPlanRegister
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMoveIntentPayload,
    ModelSOWeaponFireIntentPayload,
)
from steel_onslaught.match.card_adapter import CardRunnerAdapter
from steel_onslaught.match.composition import load_application_overlay, load_card_runtime_snapshot
from steel_onslaught.pilots.programming import ModelSOProgrammingObservation
from tests.match.test_card_adapter import _request

_ROOT = Path(__file__).resolve().parents[2]
_DECK_DIR = _ROOT / "contracts_data/decks"


def _load_deck(filename: str) -> ModelSODeck:
    raw: object = yaml.safe_load((_DECK_DIR / filename).read_text(encoding="utf-8"))
    return ModelSODeck.model_validate(raw)


@pytest.mark.unit
def test_tactical_v1_is_a_fixed_thirty_card_pack_with_four_runtime_roles() -> None:
    deck = _load_deck("tactical_v1.yaml")

    assert deck.id == "deck.tactical.v1"
    assert deck.hand_size == 5
    assert deck.register_count == 5
    assert deck.total_cards() == 30
    assert Counter(deck.card_multiset()) == Counter(
        {
            "card.attack.fire_primary": 6,
            "card.attack.fire_secondary": 6,
            "card.movement.advance": 5,
            "card.movement.flank_left": 2,
            "card.movement.flank_right": 2,
            "card.movement.reposition": 3,
            "card.vent.emergency_vent": 3,
            "card.special.mode_evasion": 2,
            "card.special.mode_recon": 1,
        }
    )


@pytest.mark.unit
def test_tactical_cards_compile_to_distinct_canonical_effect_parameters() -> None:
    overlay_path = _ROOT / "contracts_data/overlays/tactical_v1_qwen.yaml"
    overlay = load_application_overlay(overlay_path)
    assert overlay.contracts.card_catalog is not None
    snapshot = load_card_runtime_snapshot(overlay.contracts.card_catalog)
    catalog = snapshot.card_catalog

    precision = compile_card_action(catalog.require("card.attack.fire_primary"))
    suppressive = compile_card_action(catalog.require("card.attack.fire_secondary"))
    guard = compile_card_action(catalog.require("card.special.mode_evasion"))
    cover = compile_card_action(catalog.require("card.movement.reposition"))

    assert isinstance(precision.parameters, ModelSOCardAttackParameters)
    assert precision.parameters.weapon_slot == 0
    assert isinstance(suppressive.parameters, ModelSOCardAttackParameters)
    assert suppressive.parameters.weapon_slot == 1
    assert isinstance(guard.parameters, ModelSOCardSpecialParameters)
    assert guard.parameters.target_mode is ModeId.EVASION
    assert isinstance(cover.parameters, ModelSOCardMovementParameters)
    assert cover.parameters.direction == "away_from_enemy"

    request = _request("a", weapon_ids=("weapon.primary", "weapon.secondary"))
    precision_event, precision_payload = CardRunnerAdapter._intent_for_translation(
        precision, request
    )
    suppressive_event, suppressive_payload = CardRunnerAdapter._intent_for_translation(
        suppressive, request
    )
    guard_event, guard_payload = CardRunnerAdapter._intent_for_translation(guard, request)
    cover_event, cover_payload = CardRunnerAdapter._intent_for_translation(cover, request)
    assert precision_event is SOEventType.WEAPON_FIRE_INTENT
    assert suppressive_event is SOEventType.WEAPON_FIRE_INTENT
    assert guard_event is SOEventType.MODE_SWITCH_INTENT
    assert cover_event is SOEventType.MOVE_INTENT
    assert isinstance(precision_payload, ModelSOWeaponFireIntentPayload)
    assert isinstance(suppressive_payload, ModelSOWeaponFireIntentPayload)
    assert isinstance(guard_payload, ModelSOModeSwitchIntentPayload)
    assert isinstance(cover_payload, ModelSOMoveIntentPayload)
    assert precision_payload.weapon_id == "weapon.primary"
    assert suppressive_payload.weapon_id == "weapon.secondary"
    assert guard_payload.target_mode is ModeId.EVASION
    assert cover_payload.direction == "defensive"


@pytest.mark.unit
def test_tactical_overlay_selects_isolated_deck_and_qwen_provider() -> None:
    overlay_path = _ROOT / "contracts_data/overlays/tactical_v1_qwen.yaml"
    overlay = load_application_overlay(overlay_path)
    binding = overlay.contracts.card_catalog
    assert binding is not None
    assert binding.card_mode_enabled is True
    assert binding.deck_id == "deck.tactical.v1"
    assert binding.card_cadence == "paced"
    assert tuple(programmer.pilot_spec_id for programmer in binding.programmers) == (
        "pilot.llm.qwen35",
        "pilot.llm.qwen35",
    )
    assert overlay.llm.providers[0].provider_id == "qwen35"
    assert overlay.event_ledger.path.parts[-2:] == ("tactical_v1_qwen", "events.sqlite3")


@pytest.mark.unit
def test_tactical_pack_round_emits_canonical_actions_for_all_four_roles() -> None:
    overlay = load_application_overlay(_ROOT / "contracts_data/overlays/tactical_v1_qwen.yaml")
    assert overlay.contracts.card_catalog is not None
    snapshot = load_card_runtime_snapshot(overlay.contracts.card_catalog)
    dealer = DealerCompute()
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=5,
    )

    class TacticalProgram:
        def program(
            self, observation: ModelSOProgrammingObservation
        ) -> ModelSOPlanCommittedPayload:
            desired = (
                "card.attack.fire_primary",
                "card.attack.fire_secondary",
                "card.special.mode_evasion",
                "card.movement.reposition",
                "card.movement.advance",
            )
            assert tuple(desired) == observation.hand
            return ModelSOPlanCommittedPayload(
                seat=observation.seat,
                registers=tuple(
                    ModelSOPlanRegister(register_index=index, card_id=card_id)
                    for index, card_id in enumerate(desired)
                ),
                rationale="tactical-role-proof",
                confidence=1.0,
            )

    adapter = CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=dealer,
        reducer=reducer,
        programmers={"a": TacticalProgram()},
    )
    desired_hand = (
        "card.attack.fire_primary",
        "card.attack.fire_secondary",
        "card.special.mode_evasion",
        "card.movement.reposition",
        "card.movement.advance",
    )
    remaining = list(snapshot.selected_deck.card_multiset())
    for card_id in desired_hand:
        remaining.remove(card_id)
    emission = adapter.produce(
        seats=(_request("a", weapon_ids=("weapon.primary", "weapon.secondary")),),
        round_index=0,
        tick=3,
        causation_id="round.tactical.roles",
        starting_deck_state=ModelSODeckState(
            draw_pile=desired_hand + tuple(remaining),
            discard_pile=(),
        ),
    )

    assert emission.sequence is not None
    assert len(emission.sequence.plan_committed) == 1
    assert len(emission.sequence.register_resolved) == 5
    assert {action.event_type for action in emission.actions} == {
        SOEventType.WEAPON_FIRE_INTENT,
        SOEventType.MODE_SWITCH_INTENT,
        SOEventType.MOVE_INTENT,
    }
    fire_payloads = []
    for action in emission.actions:
        if action.event_type is SOEventType.WEAPON_FIRE_INTENT:
            assert isinstance(action.payload, ModelSOWeaponFireIntentPayload)
            fire_payloads.append(action.payload)
    assert [payload.weapon_id for payload in fire_payloads] == [
        "weapon.primary",
        "weapon.secondary",
    ]
