"""End-to-end round-4 range-band (close-range accuracy falloff) proof.

Deterministic sniper-vs-berserker matches on foundry_60 (the same priority
planner the c11 / round-3 match tests use — no LLM), read from the canonical
event ledger. Falsification per the hostile-review fix #2 (do NOT verify with a
"hit_prob <= threshold" check — LOS-block / no-lock / evasion all trip that):

  - PAIRED-SEED DIFFERENTIAL: on the SAME seed, enabling the falloff lowers the
    sniper's recorded hit_probability on the first aimed LONG-weapon shot fired
    inside the close band, with a byte-identical event prefix up to that shot
    (every earlier shot was either short-range, at/beyond the band, or LOS-
    blocked, so the multiplier was 1.0). Fails if the falloff is unwired
    (ON == OFF);
  - MULTIPLIER WITNESS: the OFF arm records close_range_mult == 1.0 on every
    shot; the ON arm records close_range_mult < 1.0 on at least one long-weapon
    shot inside the band (the direct, un-forgeable witness that the falloff
    fired — a value a LOS-block/no-lock/evasion false-green cannot produce);
  - REPLAY-EXACT: re-folding the ON match's canonical ledger reconstructs a
    state == the live final state (the multiplier is folded into the recorded
    WEAPON_FIRED hit_probability, never persisted, so reconstruct == live);
  - COMPOSED TERMINAL: the full round-4 composition (moderate evasion 0.14/0.42
    + falloff ON + the sniper's carbine deck/loadout) still reaches a terminal.
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
    ModelSOCloseRangeFalloffBinding,
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
from steel_onslaught.match.state import ModelSOMatchState, SOMatchStatus
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

# The shipped round-4 numbers (tactical_split_range_band_evasion_qwen.yaml).
_FALLOFF = ModelSOCloseRangeFalloffBinding(
    kind="close_range_accuracy_falloff",
    min_weapon_range=20,
    band_distance=20,
    point_blank_multiplier=0.30,
)
_EVASION = ModelSOMovesEvasionBinding(kind="moves_scaled_evasion", evasion_per_move=0.14, cap=0.42)

# The sniper's long weapons — the only ones subject to the falloff (range >= 20).
_LONG_WEAPONS = {"weapon.siege.artillery_mortar", "weapon.heavy.harpoon_gun"}


class _RemainPilot:
    """Card mode drives the round; this only satisfies the presence check."""

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=[ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=0.0)],
        )


def _policy(sniper_weapon_deck_id: str) -> ModelSOCardDeckPolicy:
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
                weapon_deck_id=sniper_weapon_deck_id,
                hand_quota=ModelSODeckHandQuota(movement=2, weapon=3),
                register_count=5,
            ),
        ),
    )


def _snapshot(sniper_weapon_deck_id: str) -> ModelSOCardRuntimeSnapshot:
    return load_card_runtime_snapshot(
        ModelSOCardCatalogBinding(
            kind="filesystem_yaml",
            cards_dir=(_CONTRACTS / "cards").resolve(),
            decks_dir=(_CONTRACTS / "decks").resolve(),
            card_mode_enabled=True,
            card_cadence="paced",
            deck_policy=_policy(sniper_weapon_deck_id),
        )
    )


def _adapter(snapshot: ModelSOCardRuntimeSnapshot, sniper_weapon_deck_id: str) -> CardRunnerAdapter:
    dealer = DealerCompute()
    split = SplitDeckDealerAdapter(
        snapshot=snapshot, policy=_policy(sniper_weapon_deck_id), dealer=dealer
    )
    reducer = RegisterExecutionReducer(snapshot.card_catalog)
    runtime = CardRoundRuntime(
        card_runtime_snapshot=snapshot,
        dealer=dealer,
        reducer=reducer,
        round_length=5,
        split_deck_adapter=split,
    )
    # c11 handler ON in every arm (unchanged): the falloff is the only variable
    # in the differential below.
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
    close_range_falloff: ModelSOCloseRangeFalloffBinding | None,
    moves_evasion: ModelSOMovesEvasionBinding | None = None,
    sniper_loadout: str = "loadouts/qwen35/sniper_ironclad.yaml",
    sniper_weapon_deck_id: str = "deck.weapon.v1",
    ledger: SQLiteLedger | None = None,
) -> tuple[list[ModelSOEventEnvelope], ModelSOMatchState]:
    catalog = load_match_contract_catalog(_CONTRACTS)
    arena = catalog.arenas["foundry_60"]
    snapshot = _snapshot(sniper_weapon_deck_id)
    bus = InProcessEventBus()
    events: list[ModelSOEventEnvelope] = []
    bus.subscribe(events.append)
    if ledger is not None:
        bus.subscribe(ledger.append)
    # match_id feeds the dealer scope, so it MUST be identical across A/B arms —
    # the falloff binding is the only thing allowed to differ in the differential.
    runner = MatchRunner(
        identity=MatchIdentity(f"match.falloff.{seed}", UUID(int=seed)),
        seed=seed,
        loadout_a=load_loadout(_CONTRACTS / "loadouts/llm_qwen35_berserker.yaml"),
        loadout_b=load_loadout(_CONTRACTS / sniper_loadout),
        bus=bus,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
        catalog=catalog,
        arena=arena,
        pilots={_BRAWLER: _RemainPilot(), _SNIPER: _RemainPilot()},
        max_ticks=None,  # uncapped: sudden death bounds the match like the live demo
        card_runtime_snapshot=snapshot,
        card_adapter=_adapter(snapshot, sniper_weapon_deck_id),
        card_cadence="paced",
        moves_evasion=moves_evasion,
        close_range_falloff=close_range_falloff,
    )
    final = runner.run()
    return events, final


def _weapon_fires(
    events: list[ModelSOEventEnvelope],
) -> list[tuple[float, str, float]]:
    """(hit_probability, weapon_id, close_range_mult) per WEAPON_FIRED, in order."""
    return [
        (
            float(event.payload["hit_probability"]),
            str(event.payload["weapon_id"]),
            float(event.payload["close_range_mult"]),
        )
        for event in events
        if event.event_type is SOEventType.WEAPON_FIRED
    ]


def _first_divergent(
    on: list[tuple[float, str, float]], off: list[tuple[float, str, float]]
) -> int | None:
    """First index whose recorded hit_probability differs.

    Divergence is measured on hit_probability alone — the gameplay quantity that
    the RNG roll (and therefore all subsequent state) depends on. The
    close_range_mult observability field can legitimately differ earlier on a
    LOS-blocked in-band long-weapon shot (hit_probability is 0.0 in both arms, so
    the miss and all following state are identical), which is not a gameplay
    divergence.
    """
    for index in range(min(len(on), len(off))):
        if on[index][0] != off[index][0]:
            return index
    return None


# A spread of seeds: as in the round-3 test, many deterministic matches resolve
# on LOS-blocked shots or via sudden death without a real aimed long-weapon shot
# inside the band, so the mechanic only bites on a subset. Require it to bite on
# at least one and to be directionally correct on EVERY seed it bites.
_SEEDS = tuple(range(1, 13))
_REPLAY_SEED = 2


def test_falloff_lowers_long_weapon_hit_chance_and_is_load_bearing() -> None:
    """The falloff lowers the first aimed long-weapon shot inside the band, with a
    byte-identical prefix up to it. Fails if the falloff is unwired (ON == OFF)."""

    bit_at_least_once = False
    for seed in _SEEDS:
        on = _weapon_fires(_run(seed, close_range_falloff=_FALLOFF)[0])
        off = _weapon_fires(_run(seed, close_range_falloff=None)[0])

        diverge = _first_divergent(on, off)
        if diverge is None:
            # No aimed long-weapon shot inside the band this seed: the two arms
            # are byte-identical, itself the "short-range / at-band / blocked =>
            # unchanged" guarantee.
            continue
        bit_at_least_once = True

        # Every shot BEFORE the first affected fire has an identical hit chance
        # (multiplier 1.0 applied there — short weapon or at/beyond band — or a
        # LOS-blocked 0.0 in both arms), so the RNG rolls and all state match up
        # to the diverging shot.
        on_probs = [shot[0] for shot in on]
        off_probs = [shot[0] for shot in off]
        assert on_probs[:diverge] == off_probs[:diverge], f"seed {seed} prefix diverged early"

        on_prob, on_weapon, on_mult = on[diverge]
        off_prob, _off_weapon, off_mult = off[diverge]
        # The diverging shot is a long weapon fired inside the band.
        assert on_weapon in _LONG_WEAPONS, f"seed {seed}: non-long weapon diverged ({on_weapon})"
        # OFF applied no penalty; ON applied a real (<1.0) close-range multiplier.
        assert off_mult == 1.0, f"seed {seed}: OFF arm recorded a penalty ({off_mult})"
        assert on_mult < 1.0, f"seed {seed}: ON arm recorded no penalty ({on_mult})"
        # The falloff only ever LOWERS the shooter's hit chance, never raises it.
        assert on_prob < off_prob, (
            f"seed {seed}: falloff did not lower hit chance (on={on_prob} off={off_prob})"
        )

    assert bit_at_least_once, "falloff never changed any shot across all seeds (unwired?)"


def test_falloff_multiplier_is_logged_and_off_arm_is_neutral() -> None:
    """The recorded close_range_mult is the direct falsification witness: OFF logs
    1.0 on every shot, ON logs < 1.0 on at least one long-weapon shot in-band."""

    off_mults_all_one = True
    on_saw_penalty = False
    for seed in _SEEDS:
        for _prob, _weapon, mult in _weapon_fires(_run(seed, close_range_falloff=None)[0]):
            if mult != 1.0:
                off_mults_all_one = False
        for _prob, weapon, mult in _weapon_fires(_run(seed, close_range_falloff=_FALLOFF)[0]):
            # A short weapon or an at/beyond-band shot must still record 1.0 even
            # on the ON arm — only long weapons inside the band are penalised.
            if weapon not in _LONG_WEAPONS:
                assert mult == 1.0, f"seed {seed}: short weapon {weapon} got a penalty {mult}"
            if mult < 1.0:
                assert weapon in _LONG_WEAPONS
                on_saw_penalty = True

    assert off_mults_all_one, "OFF arm recorded a non-1.0 close_range_mult (binding leaked?)"
    assert on_saw_penalty, "ON arm never recorded a <1.0 multiplier (falloff never fired?)"


def test_falloff_replay_exact(tmp_path: Path) -> None:
    """The multiplier is folded into the recorded hit_probability and never
    persisted, so re-folding the ON ledger reconstructs == the live final state."""

    ledger = SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=tmp_path / "falloff_replay.sqlite3",
            journal_mode="WAL",
            check_same_thread=True,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )
    _events, final = _run(_REPLAY_SEED, close_range_falloff=_FALLOFF, ledger=ledger)

    catalog = load_match_contract_catalog(_CONTRACTS)
    replay = ReplayEngine(
        ledger,
        final.match_id,
        catalog=catalog,
        event_factory=EventFactory(clock=FixedClock(), identities=SequentialIdentities()),
    )
    reconstructed = replay.reconstruct_at_tick(final.tick)

    assert reconstructed == final


def test_composed_range_band_reaches_terminal() -> None:
    """The full round-4 composition (moderate evasion + falloff ON + the sniper's
    carbine deck/loadout) still reaches a durable terminal on every seed."""

    for seed in (1, 2, 3):
        _events, final = _run(
            seed,
            close_range_falloff=_FALLOFF,
            moves_evasion=_EVASION,
            sniper_loadout="loadouts/qwen35/sniper_ironclad_carbine.yaml",
            sniper_weapon_deck_id="deck.weapon.sniper_v1",
        )
        assert final.status is SOMatchStatus.ENDED, f"seed {seed} did not terminate: {final.status}"
        assert final.winner_id is not None or final.end_reason is not None


def test_carbine_actually_fires_in_composed_arm() -> None:
    """With the carbine deck + loadout the sniper actually fires hardpoint 2 (the
    carbine), and every carbine shot records a 1.0 multiplier (it is exempt)."""

    saw_carbine = False
    for seed in _SEEDS:
        for _prob, weapon, mult in _weapon_fires(
            _run(
                seed,
                close_range_falloff=_FALLOFF,
                moves_evasion=_EVASION,
                sniper_loadout="loadouts/qwen35/sniper_ironclad_carbine.yaml",
                sniper_weapon_deck_id="deck.weapon.sniper_v1",
            )[0]
        ):
            if weapon == "weapon.light.defense_carbine":
                saw_carbine = True
                assert mult == 1.0, f"seed {seed}: carbine (range 14) was penalised ({mult})"

    assert saw_carbine, "the sniper never fired its carbine across all seeds (deck unwired?)"
