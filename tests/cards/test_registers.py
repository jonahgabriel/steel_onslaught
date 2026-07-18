"""Pure register reducer invariants over an explicitly injected card catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.cards.registers import (
    ModelSOSeatResolutionContext,
    RegisterExecutionReducer,
    RegisterPlanError,
    RegisterReplayDriftError,
    heat_locked_indices,
    resolve_register,
    resolve_round,
    verify_register_replay,
)
from steel_onslaught.contracts.card import ModelSOCard, ModelSOCardCatalog
from steel_onslaught.events.card_payloads import (
    ModelSOPlanCommittedPayload,
    ModelSOPlanRegister,
    SORegisterFillReason,
    SORegisterOutcome,
)

pytestmark = pytest.mark.unit

_CARD_DIR = Path(__file__).resolve().parents[2] / "contracts_data/cards"
_FIRE_PRIMARY = "card.attack.fire_primary"
_FIRE_SECONDARY = "card.attack.fire_secondary"
_ADVANCE = "card.movement.advance"
_REPOSITION = "card.movement.reposition"
_VENT = "card.vent.emergency_vent"


@pytest.fixture(scope="module")
def cards() -> ModelSOCardCatalog:
    definitions = tuple(
        ModelSOCard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(_CARD_DIR.glob("*.yaml"))
    )
    return ModelSOCardCatalog(cards=definitions)


def _plan(seat: str, mapping: dict[int, str]) -> ModelSOPlanCommittedPayload:
    return ModelSOPlanCommittedPayload(
        seat=seat,
        registers=tuple(
            ModelSOPlanRegister(register_index=index, card_id=card_id)
            for index, card_id in sorted(mapping.items())
        ),
        rationale=None,
        confidence=0.8,
    )


def _ctx(
    seat: str,
    mapping: dict[int, str],
    *,
    register_count: int = 5,
    initiative: int = 100,
    lock_depth: int = 0,
    previous: dict[int, str] | None = None,
) -> ModelSOSeatResolutionContext:
    return ModelSOSeatResolutionContext(
        seat=seat,
        register_count=register_count,
        initiative=initiative,
        lock_depth=lock_depth,
        plan=_plan(seat, mapping),
        previous_plan=_plan(seat, previous) if previous is not None else None,
    )


def test_catalog_is_explicit_immutable_and_rejects_duplicates(cards: ModelSOCardCatalog) -> None:
    assert cards.model_config["frozen"] is True
    assert cards.require(_FIRE_PRIMARY).id == _FIRE_PRIMARY
    with pytest.raises(ValidationError, match="unique"):
        ModelSOCardCatalog(cards=(cards.cards[0], cards.cards[0]))
    with pytest.raises(ValueError, match="unknown card id"):
        cards.require("card.unknown.id")
    with pytest.raises(ValidationError, match="extra"):
        ModelSOCardCatalog.model_validate(
            {"cards": cards.model_dump(mode="json")["cards"], "extra": True}
        )


def test_reducer_requires_an_explicit_catalog(cards: ModelSOCardCatalog) -> None:
    with pytest.raises(TypeError):
        RegisterExecutionReducer()  # type: ignore[call-arg]
    reducer = RegisterExecutionReducer(cards)
    rows = reducer.resolve_round((_ctx("a", {0: _FIRE_PRIMARY}, register_count=1),), 1)
    assert rows[0].card_id == _FIRE_PRIMARY


def test_heat_lock_suffix_preserves_one_free_register() -> None:
    assert heat_locked_indices(0, 5) == frozenset()
    assert heat_locked_indices(1, 5) == frozenset({4})
    assert heat_locked_indices(2, 5) == frozenset({3, 4})
    assert heat_locked_indices(99, 5) == frozenset({1, 2, 3, 4})
    assert heat_locked_indices(99, 1) == frozenset()
    with pytest.raises(ValueError, match="register_count"):
        heat_locked_indices(0, 0)
    with pytest.raises(ValueError, match="lock_depth"):
        heat_locked_indices(-1, 5)
    with pytest.raises(ValueError, match="integer"):
        heat_locked_indices(True, 5)


def test_priority_initiative_and_seat_tiebreaks_are_total(cards: ModelSOCardCatalog) -> None:
    a = _ctx("a", {0: _VENT}, register_count=1, initiative=999)
    b = _ctx("b", {0: _FIRE_PRIMARY}, register_count=1, initiative=1)
    assert [row.seat for row in resolve_register((a, b), 0, cards)] == ["b", "a"]

    a = _ctx("a", {0: _FIRE_PRIMARY}, register_count=1, initiative=1)
    b = _ctx("b", {0: _FIRE_PRIMARY}, register_count=1, initiative=999)
    assert [row.seat for row in resolve_register((a, b), 0, cards)] == ["b", "a"]

    assert [row.seat for row in resolve_register((b, a), 0, cards)] == ["b", "a"]
    equal_a = _ctx("a", {0: _FIRE_PRIMARY}, register_count=1, initiative=10)
    equal_b = _ctx("b", {0: _FIRE_PRIMARY}, register_count=1, initiative=10)
    rows = resolve_register((equal_b, equal_a), 0, cards)
    assert [row.seat for row in rows] == ["a", "b"]
    assert [row.priority_rank for row in rows] == [0, 1]


def test_round_contains_every_seat_for_every_register(cards: ModelSOCardCatalog) -> None:
    a = _ctx("a", {0: _FIRE_PRIMARY, 1: _ADVANCE}, register_count=2)
    b = _ctx("b", {0: _VENT, 1: _FIRE_SECONDARY}, register_count=2)
    rows = resolve_round((a, b), 2, cards)
    assert len(rows) == 4
    assert {(row.register_index, row.seat) for row in rows} == {
        (0, "a"),
        (0, "b"),
        (1, "a"),
        (1, "b"),
    }
    for index in (0, 1):
        register_rows = tuple(row for row in rows if row.register_index == index)
        assert len(register_rows) == 2
        assert [row.priority_rank for row in register_rows] == [0, 1]


def test_auto_remain_is_short_deck_only(cards: ModelSOCardCatalog) -> None:
    context = _ctx(
        "a",
        {0: _FIRE_PRIMARY, 1: _ADVANCE, 2: _VENT, 3: _REPOSITION},
        register_count=4,
    )
    row = next(row for row in resolve_round((context,), 5, cards) if row.register_index == 4)
    assert row.outcome is SORegisterOutcome.AUTO_REMAIN
    assert row.card_id is None
    assert row.fill_reason is SORegisterFillReason.SHORT_DECK
    assert row.priority == 0
    assert row.action == "remain"


def test_heat_locked_repeats_prior_card_and_is_distinct(cards: ModelSOCardCatalog) -> None:
    context = _ctx(
        "a",
        {0: _FIRE_PRIMARY, 1: _ADVANCE, 2: _VENT, 3: _REPOSITION},
        lock_depth=1,
        previous={4: _FIRE_SECONDARY},
    )
    row = next(row for row in resolve_round((context,), 5, cards) if row.register_index == 4)
    assert row.outcome is SORegisterOutcome.HEAT_LOCKED
    assert row.card_id == _FIRE_SECONDARY
    assert row.fill_reason is None
    assert row.action == "fire_weapon"

    short = _ctx(
        "s",
        {0: _FIRE_PRIMARY, 1: _ADVANCE, 2: _VENT, 3: _REPOSITION},
        register_count=4,
    )
    short_row = next(row for row in resolve_round((short,), 5, cards) if row.register_index == 4)
    assert short_row.outcome is not row.outcome
    assert short_row.card_id is None


def test_heat_locked_without_prior_card_fails_closed(cards: ModelSOCardCatalog) -> None:
    context = _ctx(
        "a",
        {0: _FIRE_PRIMARY, 1: _ADVANCE, 2: _VENT, 3: _REPOSITION},
        lock_depth=1,
    )
    with pytest.raises(RegisterPlanError, match="no prior card"):
        resolve_round((context,), 5, cards)


def test_plan_coverage_unknown_cards_and_context_identity_are_strict(
    cards: ModelSOCardCatalog,
) -> None:
    missing = _ctx("a", {0: _FIRE_PRIMARY}, register_count=2)
    with pytest.raises(RegisterPlanError, match="exactly its free registers"):
        resolve_round((missing,), 2, cards)

    locked = _ctx(
        "a",
        {0: _FIRE_PRIMARY, 1: _ADVANCE, 2: _VENT, 3: _REPOSITION, 4: _FIRE_SECONDARY},
        lock_depth=1,
        previous={4: _FIRE_SECONDARY},
    )
    with pytest.raises(RegisterPlanError, match="exactly its free registers"):
        resolve_round((locked,), 5, cards)

    unknown = _ctx("a", {0: "card.unknown.id"}, register_count=1)
    with pytest.raises(ValueError, match="unknown card id"):
        resolve_round((unknown,), 1, cards)

    with pytest.raises(ValueError, match="unique seat"):
        resolve_round((_ctx("a", {0: _FIRE_PRIMARY}), _ctx("a", {0: _VENT})), 1, cards)
    with pytest.raises(ValueError, match="at least one seat"):
        resolve_round((), 1, cards)
    with pytest.raises(ValidationError, match="does not match context"):
        ModelSOSeatResolutionContext(
            seat="a",
            register_count=1,
            initiative=1,
            plan=_plan("b", {0: _FIRE_PRIMARY}),
        )
    with pytest.raises(ValidationError, match="previous_plan seat"):
        ModelSOSeatResolutionContext(
            seat="a",
            register_count=1,
            initiative=1,
            plan=_plan("a", {0: _FIRE_PRIMARY}),
            previous_plan=_plan("b", {0: _FIRE_PRIMARY}),
        )


def test_replay_is_byte_identical_and_detects_drift(cards: ModelSOCardCatalog) -> None:
    a = _ctx("a", {0: _FIRE_PRIMARY, 1: _VENT}, register_count=2, initiative=50)
    b = _ctx("b", {0: _ADVANCE, 1: _FIRE_SECONDARY}, register_count=2, initiative=70)
    recorded = resolve_round((a, b), 2, cards)
    assert recorded == resolve_round((a, b), 2, cards)
    assert [row.model_dump(mode="json") for row in recorded] == [
        row.model_dump(mode="json") for row in resolve_round((a, b), 2, cards)
    ]
    verify_register_replay(recorded, (a, b), 2, cards)
    RegisterExecutionReducer(cards).verify_replay(recorded, (a, b), 2)

    tampered = (
        recorded[0].model_copy(update={"priority": recorded[0].priority + 1}),
        *recorded[1:],
    )
    with pytest.raises(RegisterReplayDriftError, match="replay drift"):
        verify_register_replay(tampered, (a, b), 2, cards)

    tampered_action = (recorded[0].model_copy(update={"action": "remain"}), *recorded[1:])
    with pytest.raises(RegisterReplayDriftError, match="replay drift"):
        verify_register_replay(tampered_action, (a, b), 2, cards)

    before_contexts = (a, b)
    before_catalog = cards
    resolve_round(before_contexts, 2, before_catalog)
    assert before_contexts == (a, b)
    assert before_catalog == cards


def test_input_permutation_does_not_change_output_bytes(cards: ModelSOCardCatalog) -> None:
    a = _ctx("a", {0: _FIRE_PRIMARY}, register_count=1, initiative=10)
    b = _ctx("b", {0: _FIRE_PRIMARY}, register_count=1, initiative=10)
    first = resolve_round((a, b), 1, cards)
    second = resolve_round((b, a), 1, cards)
    assert first == second
    assert json.dumps([row.model_dump(mode="json") for row in first], sort_keys=True) == json.dumps(
        [row.model_dump(mode="json") for row in second], sort_keys=True
    )


def test_invalid_lengths_and_boolean_integers_fail_closed(cards: ModelSOCardCatalog) -> None:
    context = _ctx("a", {0: _FIRE_PRIMARY}, register_count=1)
    with pytest.raises(ValueError, match="round_length"):
        resolve_round((context,), 0, cards)
    with pytest.raises(ValueError, match="register index"):
        resolve_register((context,), -1, cards)
    with pytest.raises(ValueError, match="integer"):
        resolve_round((context,), True, cards)
