"""End-to-end round-3 Moves-Scaled Evasion proof over a full split-deck match.

Covers, in deterministic sniper-vs-berserker matches on foundry_60 (no LLM — the
same priority planner the c11 match test uses), all read from the canonical
event ledger:

  - the mechanic BITES and is load-bearing: on the SAME seed, enabling the
    evasion policy lowers the shooter's recorded hit_probability against a target
    that resolved movement this round, while every shot before that first
    evasion-affected fire is byte-identical (proving a stationary/no-move target
    is unchanged) — this assertion FAILS if the policy is unwired (ON == OFF);
  - replay-exactness: re-reading the ON match's canonical ledger through the
    ReplayEngine reconstructs a state == the live final state (the evasion bonus
    is never persisted, so the recorded WEAPON_FIRED hit_probability is the one
    source of truth on replay).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cards.dealer import DealerCompute
from steel_onslaught.cards.registers import RegisterExecutionReducer
from steel_onslaught.cards.round import CardRoundRuntime
from steel_onslaught.cards.rules import default_rule_registry
from steel_onslaught.cards.split_deck import SplitDeckDealerAdapter
from steel_onslaught.contracts.application import (
    ModelSOCardCatalogBinding,
    ModelSOMovesEvasionBinding,
)
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.contracts.split_deck import (
    ModelSOCardDeckPolicy,
    ModelSODeckHandQuota,
    ModelSOSeatDeckPolicy,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.match.card_adapter import CardRunnerAdapter
from steel_onslaught.match.composition import (
    load_card_runtime_snapshot,
    load_loadout,
    load_match_contract_catalog,
)
from steel_onslaught.match.runner import MatchIdentity, MatchRunner
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from steel_onslaught.replay.engine import ReplayEngine
from tests.runtime import FixedClock, SequentialIdentities

pytestmark = pytest.mark.integration

_CONTRACTS = Path("contracts_data")
_BRAWLER = "mech.a.01"
_SNIPER = "mech.b.01"

# The shipped round-3 numbers (contracts_data/overlays/tactical_split_moves_evasion_qwen.yaml).
_EVASION = ModelSOMovesEvasionBinding(kind="moves_scaled_evasion", evasion_per_move=0.08, cap=0.24)


class _RemainPilot:
    """Card mode drives the round; this only satisfies the presence check."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.0)],
        )


def _policy() -> ModelSOCardDeckPolicy:
    return ModelSOCardDeckPolicy(
        schema_version="0.1.0",
        kind="steel_onslaught.card_deck_policy",
        seats=(
            ModelSOSeatDeckPolicy(
                side="red",
                archetype="berserker",
                movement_deck_id="deck.movement.v1",
                weapon_deck_id="deck.weapon.v1",
                hand_quota=ModelSODeckHandQuota(movement=3, weapon=2),
                register_count=5,
            ),
            ModelSOSeatDeckPolicy(
                side="blue",
                archetype="sniper",
                movement_deck_id="deck.movement.v1",
                weapon_deck_id="deck.weapon.v1",
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=3),
                register_count=5,
            ),
        ),
    )


def _snapshot() -> ModelSOCardRuntimeSnapshot:
    return load_card_runtime_snapshot(
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=(_CONTRACTS / "cards").resolve(),
            decks_dir=(_CONTRACTS / "decks").resolve(),
            card_mode_enabled=True,
            card_cadence="paced",
            deck_policy=_policy(),
        )
    )


def _adapter(snapshot: ModelSOCardRuntimeSnapshot) -> CardRunnerAdapter:
    dealer = DealerCompute()
    split = SplitDeckDealerAdapter(snapshot=snapshot, policy=_policy(), dealer=dealer)
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=5,
        split_deck_adapter=split,
    )
    # c11 handler ON in BOTH arms (unchanged from round 2): evasion is the only
    # variable across the two runs below.
    return CardRunnerAdapter(
        registers_enabled=True,
        card_round_runtime=runtime,
        dealer=dealer,
        reducer=reducer,
        split_deck_adapter=split,
        programmers=None,  # deterministic priority planner — no LLM
        rule_registry=default_rule_registry(),
        rule_handler_ids=("overpressure_cooldown",),
    )


def _run(
    seed: int,
    *,
    moves_evasion: ModelSOMovesEvasionBinding | None,
    ledger: SQLiteLedger | None = None,
) -> tuple[list[ModelSOEventEnvelope], ModelSOMatchState]:
    catalog = load_match_contract_catalog(_CONTRACTS)
    arena = catalog.arenas["foundry_60"]
    snapshot = _snapshot()
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    if ledger is not None:
        bus.subscribe(ledger.append)
    # The match_id feeds the dealer scope, so it MUST be identical across the
    # A/B arms — the evasion policy is the only thing allowed to differ.
    runner = MatchRunner(
        identity=MatchIdentity(f"match.evasion.{seed}", UUID(int=seed)),
        seed=seed,
        loadout_a=load_loadout(_CONTRACTS / "loadouts/llm_qwen35_berserker.yaml"),
        loadout_b=load_loadout(_CONTRACTS / "loadouts/qwen35/sniper_ironclad.yaml"),
        bus=bus,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        catalog=catalog,
        arena=arena,
        pilots={_BRAWLER: _RemainPilot(), _SNIPER: _RemainPilot()},
        max_ticks=None,  # uncapped: sudden death bounds the match like the live demo
        card_runtime_snapshot=snapshot,
        card_adapter=_adapter(snapshot),
        card_cadence="paced",
        moves_evasion=moves_evasion,
    )
    final = runner.run()
    return events, final


def _weapon_fire_hit_probs(events: list[ModelSOEventEnvelope]) -> list[float]:
    return [
        float(event.payload["hit_probability"])
        for event in events
        if event.event_type is SOEventType.WEAPON_FIRED
    ]


def _first_divergent_shot(on: list[float], off: list[float]) -> int | None:
    """Index of the first WEAPON_FIRED whose hit_probability differs, or None."""
    for index in range(min(len(on), len(off))):
        if on[index] != off[index]:
            return index
    return None


# A spread of seeds: with the deterministic (no-LLM) priority planner many
# matches resolve entirely on line-of-sight-blocked shots (hit_probability 0.0,
# never touching evasion) or via sudden-death, so the mechanic only bites on the
# subset of seeds that produce a real aimed shot at a target that moved this
# round.  The test requires it to bite on at least one and to be directionally
# correct on EVERY seed it bites.
_SEEDS = tuple(range(1, 13))
# A seed whose sniper lands real aimed shots (0.702 -> 0.534 = full 0.24 cap),
# used for the replay-exactness proof.
_AIMED_SEED = 2


def test_moves_evasion_lowers_hit_chance_and_is_load_bearing() -> None:
    """More movement -> higher evasion -> LOWER recorded hit_probability, with an
    identical event prefix up to the first evasion-affected shot (so a stationary
    target is provably unchanged). Fails if the policy is unwired (ON == OFF)."""

    bit_at_least_once = False
    for seed in _SEEDS:
        on_probs = _weapon_fire_hit_probs(_run(seed, moves_evasion=_EVASION)[0])
        off_probs = _weapon_fire_hit_probs(_run(seed, moves_evasion=None)[0])

        diverge = _first_divergent_shot(on_probs, off_probs)
        if diverge is None:
            # No aimed shot at a moved target this seed: the two arms are
            # byte-identical, which is itself the "stationary/blocked => unchanged"
            # guarantee.
            continue
        bit_at_least_once = True

        # Every shot BEFORE the first evasion-affected fire is byte-identical:
        # those are shots at a target that had resolved no movement yet this
        # round, so the bonus is 0 and the hit chance is unchanged.
        assert on_probs[:diverge] == off_probs[:diverge], f"seed {seed} prefix diverged early"

        # At the first affected shot the target had moved this round, so evasion
        # only ever LOWERS the shooter's hit chance — never raises it.
        assert on_probs[diverge] < off_probs[diverge], (
            f"seed {seed}: evasion did not lower hit chance "
            f"(on={on_probs[diverge]} off={off_probs[diverge]})"
        )

    # Load-bearing: if the policy were unwired every arm would be identical and no
    # seed would ever diverge.
    assert bit_at_least_once, "evasion policy never changed any shot across all seeds (unwired?)"


def test_moves_evasion_replay_exact(tmp_path: Path) -> None:
    """The evasion bonus is never persisted, so re-folding the ON match's
    canonical ledger reconstructs a state == the live final state."""

    ledger = SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=tmp_path / "evasion_replay.sqlite3",
            journal_mode="WAL",
            check_same_thread=True,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )
    _events, final = _run(_AIMED_SEED, moves_evasion=_EVASION, ledger=ledger)

    catalog = load_match_contract_catalog(_CONTRACTS)
    replay = ReplayEngine(
        ledger,
        final.match_id,
        catalog=catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)

    assert reconstructed == final
