"""Match scoring reducer — Task 29.

Folds the match event stream into per-player scoring accumulators and, on the
terminal event, computes per-player scores and emits ``MATCH_SCORED`` per
design §22.2.

Score components per player:
- ``victory``: 1 if winner else 0.
- ``damage_efficiency``: damage_dealt / (pressure_consumed + 1).
- ``pressure_efficiency``: 1 - (pressure_wasted / pressure_consumed), where
  pressure_wasted is pressure drained while at full heat (heat pinned at the
  rupture-threshold cap) or while the boiler is in a disabled state.
  Defined as 1.0 when nothing was consumed (no waste possible).
- ``overload_penalty``: count of ``BOILER_OVERLOADED`` events for this player.
- ``replay_validity``: 1 if the Task 27 replay engine reproduces the live
  state at the final tick, else 0 — captured at scoring time via the injected
  ``replay_validity_check`` callable (see ``verify_replay_validity``).
- ``final_score = victory * 1000 + damage_dealt * 10
  + pressure_efficiency * 100 + replay_validity * 50
  - overload_penalty * 100``, floored at 0.

Determinism hard gate (plan invariant): ``replay_validity == 0`` zeroes the
final score entirely — a non-replayable match scores 0, which "zeroes out
>90% of the score" for every non-degenerate match and makes determinism a
hard requirement rather than a 50-point bonus.

Attribution decisions (documented, not in the plan text):
- ``damage_dealt`` accumulates from ``HIT_RESOLVED`` results
  (design §20: ``attacker_id`` + ``result.damage_after_armor``); misses and
  same-player hits are excluded (anti self-damage farming, design §23).
- ``pressure_consumed`` accumulates from ``WEAPON_FIRED.pressure_cost`` and
  ``MODE_TRANSITION_STARTED.costs.pressure`` — the same two drain events the
  boiler reducer (Task 22) folds.

Triggering: the lifecycle reducer's last-mech-standing path emits
``VICTORY_DECLARED`` without a following ``MATCH_ENDED``, so scoring fires on
either terminal event, exactly once (idempotent re-statements are no-ops).

The emitted payload carries both the design §22.2 structure
(``winner`` + ``scores``) and the flattened keys the Task 30 leaderboard
handler consumes (``winner_player_id`` .. ``is_draw``). MVP is duel-only:
flattening requires exactly two players.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from steel_onslaught.contracts.card import ModelSOCardCatalog
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import (
    ModelSOBoilerOverloadedPayload,
    ModelSOBoilerRupturedPayload,
    ModelSOBoilerUpdatedPayload,
    ModelSOHitResolvedPayload,
    ModelSOMatchEndedPayload,
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOModeTransitionStartedPayload,
    ModelSOPlayerScore,
    ModelSOScoredWinner,
    ModelSOVictoryDeclaredPayload,
    ModelSOWeaponFiredPayload,
)
from steel_onslaught.ledger.protocol import EventLedger
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.persona_prompts import ModelSOMatchPromptProvenance
from steel_onslaught.pilots.programming import ModelSOCardRulePackProvenance
from steel_onslaught.reducers.errors import ReducerError
from steel_onslaught.replay.engine import ReplayEngine

_PRODUCER_NODE = "node.reducer.scoring"

# Match-scoped events carry the wildcard subject (lifecycle convention).
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")

# ---------------------------------------------------------------------------
# Scoring constants (plan Task 29 formula)
# ---------------------------------------------------------------------------

VICTORY_POINTS = 1000
"""Points awarded for winning the match."""

DAMAGE_POINTS_PER_HP = 10
"""Points per hit point of damage dealt to opposing mechs."""

PRESSURE_EFFICIENCY_POINTS = 100
"""Points for a perfect (1.0) pressure efficiency."""

REPLAY_VALIDITY_POINTS = 50
"""Points for a replay-valid match (validity 0 additionally hard-gates to 0)."""

OVERLOAD_PENALTY_POINTS = 100
"""Points deducted per BOILER_OVERLOADED event."""


# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

EmitFn = Callable[[ModelSOEventEnvelope], None]
ReplayValidityCheck = Callable[[], bool]


# ---------------------------------------------------------------------------
# Score formula
# ---------------------------------------------------------------------------


def compute_final_score(
    *,
    victory: int,
    damage_dealt: int,
    pressure_efficiency: float,
    replay_validity: int,
    overload_penalty: int,
) -> int:
    """Apply the Task 29 score formula with the determinism hard gate.

    ``replay_validity == 0`` returns 0 outright (plan invariant: invalid
    replay zeroes out >90% of the score — determinism is a hard requirement).
    Otherwise the additive formula applies, rounded and floored at 0 (the
    leaderboard schema requires non-negative integer scores).
    """
    if replay_validity == 0:
        return 0
    raw = (
        victory * VICTORY_POINTS
        + damage_dealt * DAMAGE_POINTS_PER_HP
        + pressure_efficiency * PRESSURE_EFFICIENCY_POINTS
        + replay_validity * REPLAY_VALIDITY_POINTS
        - overload_penalty * OVERLOAD_PENALTY_POINTS
    )
    return max(0, round(raw))


# ---------------------------------------------------------------------------
# Replay-validity helper (Task 27 engine)
# ---------------------------------------------------------------------------


def verify_replay_validity(
    ledger: EventLedger,
    match_id: str,
    live_state: ModelSOMatchState,
    *,
    catalog: MatchContractCatalog,
    event_factory: EventFactory,
    card_catalog: ModelSOCardCatalog | None = None,
    card_runtime_snapshot: ModelSOCardRuntimeSnapshot | None = None,
    card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = None,
    prompt_provenance: ModelSOMatchPromptProvenance | None = None,
    validate_card_events: bool = False,
) -> bool:
    """Return True when the replay engine reproduces *live_state* exactly.

    Implements the plan's definition:
    ``replay.reconstruct_at_tick(final_tick) == live_state``.
    """
    engine = ReplayEngine(
        ledger,
        match_id,
        catalog=catalog,
        event_factory=event_factory,
        card_catalog=card_catalog,
        card_runtime_snapshot=card_runtime_snapshot,
        card_rule_pack_provenance=card_rule_pack_provenance,
        prompt_provenance=prompt_provenance,
        validate_card_events=validate_card_events,
    )
    return engine.reconstruct_at_tick(live_state.tick) == live_state


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


class ReducerScoring:
    """Per-match scoring reducer. Construct one per ``match_id``.

    Args:
        match_id:              Owning match; events for other matches are
                               silently ignored.
        correlation_id:        ONEX workflow correlation id shared across all
                               events of this match.
        emit:                  Callable receiving the produced MATCH_SCORED
                               envelope (e.g. ``bus.publish``).
        replay_validity_check: Zero-arg callable invoked once at scoring time;
                               wire it to ``verify_replay_validity`` against
                               the match ledger and live state.
    """

    def __init__(
        self,
        match_id: str,
        correlation_id: UUID,
        *,
        emit: EmitFn,
        event_factory: EventFactory,
        replay_validity_check: ReplayValidityCheck,
    ) -> None:
        self._match_id = match_id
        self._correlation_id = correlation_id
        self._emit = emit
        self._events = event_factory
        self._replay_validity_check = replay_validity_check

        # Roster (from MATCH_STARTED) — insertion order is deterministic.
        self._mech_player: dict[str, str] = {}
        self._mech_loadout: dict[str, str] = {}
        self._player_first_mech: dict[str, str] = {}

        # Boiler tracking for the pressure_wasted definition.
        self._heat: dict[str, int] = {}
        self._rupture_threshold: dict[str, int] = {}
        self._disabled: set[str] = set()

        # Per-player accumulators.
        self._damage_dealt: dict[str, int] = {}
        self._pressure_consumed: dict[str, int] = {}
        self._pressure_wasted: dict[str, int] = {}
        self._overloads: dict[str, int] = {}

        self._scored = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """``EventHandler``-shaped adapter for ``EventBus.subscribe``."""
        self.apply(event)

    def apply(self, event: ModelSOEventEnvelope) -> None:
        """Fold one event into the scoring accumulators.

        Non-scoring events — and events for other matches — are ignored so the
        replay engine can feed the full ledger through this reducer too.
        """
        if event.match_id != self._match_id:
            return

        match event.event_type:
            case SOEventType.MATCH_STARTED:
                self._register_roster(event)
            case SOEventType.WEAPON_FIRED:
                weapon_payload = ModelSOWeaponFiredPayload.model_validate(event.payload)
                self._drain_pressure(event.subject.mech_id, weapon_payload.pressure_cost)
            case SOEventType.MODE_TRANSITION_STARTED:
                mode_payload = ModelSOModeTransitionStartedPayload.model_validate(event.payload)
                self._drain_pressure(event.subject.mech_id, mode_payload.costs.pressure)
            case SOEventType.HIT_RESOLVED:
                self._accumulate_damage(event)
            case SOEventType.BOILER_UPDATED:
                boiler_payload = ModelSOBoilerUpdatedPayload.model_validate(event.payload)
                if event.subject.mech_id in self._mech_player:
                    self._heat[event.subject.mech_id] = boiler_payload.heat_after
            case SOEventType.BOILER_RUPTURED:
                ModelSOBoilerRupturedPayload.model_validate(event.payload)
                self._disabled.add(event.subject.mech_id)
            case SOEventType.BOILER_OVERLOADED:
                ModelSOBoilerOverloadedPayload.model_validate(event.payload)
                player = self._mech_player.get(event.subject.mech_id)
                if player is not None:
                    self._overloads[player] += 1
            case SOEventType.VICTORY_DECLARED:
                victory_payload = ModelSOVictoryDeclaredPayload.model_validate(event.payload)
                self._score(tick=event.tick, winner_player_id=victory_payload.winner_player_id)
            case SOEventType.MATCH_ENDED:
                ended_payload = ModelSOMatchEndedPayload.model_validate(event.payload)
                self._score(tick=event.tick, winner_player_id=ended_payload.winner_id)
            case _:
                pass  # not a scoring input

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def _register_roster(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSOMatchStartedPayload.model_validate(event.payload)
        for mech in payload.mechs:
            self._mech_player[mech.mech_id] = mech.player_id
            self._mech_loadout[mech.mech_id] = mech.loadout_id
            self._player_first_mech.setdefault(mech.player_id, mech.mech_id)
            self._heat[mech.mech_id] = mech.boiler.heat_current
            self._rupture_threshold[mech.mech_id] = mech.boiler.heat_rupture_threshold
            if mech.boiler.status_disabled or mech.boiler.status_ruptured:
                self._disabled.add(mech.mech_id)
            for accumulator in (
                self._damage_dealt,
                self._pressure_consumed,
                self._pressure_wasted,
                self._overloads,
            ):
                accumulator.setdefault(mech.player_id, 0)

    def _drain_pressure(self, mech_id: str, cost: int) -> None:
        player = self._mech_player.get(mech_id)
        if player is None or cost <= 0:
            return
        self._pressure_consumed[player] += cost
        at_full_heat = self._heat[mech_id] >= self._rupture_threshold[mech_id]
        if at_full_heat or mech_id in self._disabled:
            self._pressure_wasted[player] += cost

    def _accumulate_damage(self, event: ModelSOEventEnvelope) -> None:
        payload = ModelSOHitResolvedPayload.model_validate(event.payload)
        if not payload.result.hit:
            return
        attacker_player = self._mech_player.get(payload.attacker_id)
        defender_player = self._mech_player.get(payload.defender_id)
        if attacker_player is None or attacker_player == defender_player:
            return  # unknown attacker, self-damage, or friendly fire: no credit
        self._damage_dealt[attacker_player] += payload.result.damage_after_armor

    # ------------------------------------------------------------------
    # Scoring (terminal)
    # ------------------------------------------------------------------

    def _score(self, *, tick: int, winner_player_id: str | None) -> None:
        if self._scored:
            return  # idempotent re-statement (lifecycle owns consistency checks)
        if not self._mech_player:
            raise ReducerError("match_not_started: terminal event before MATCH_STARTED")
        players = sorted(self._player_first_mech)
        if winner_player_id is not None and winner_player_id not in self._player_first_mech:
            raise ReducerError(
                f"unknown_winner: {winner_player_id!r} fielded no mech in this match"
            )
        if len(players) != 2:
            raise ReducerError(
                f"unsupported_player_count: MVP scoring is duel-only, got {len(players)} players"
            )
        self._scored = True

        replay_validity = 1 if self._replay_validity_check() else 0
        scores = {
            player: self._player_score(
                player,
                victory=1 if player == winner_player_id else 0,
                replay_validity=replay_validity,
            )
            for player in players
        }

        is_draw = winner_player_id is None
        # Task 30 draw convention: alphabetically-first player fills the
        # winner slot; is_draw disambiguates so rankings can exclude it.
        winner_slot = players[0] if is_draw else winner_player_id
        assert winner_slot is not None  # narrowing: players is non-empty
        loser_slot = next(p for p in players if p != winner_slot)

        winner_block = (
            None
            if is_draw
            else ModelSOScoredWinner(
                player_id=winner_slot,
                mech_id=self._player_first_mech[winner_slot],
            )
        )
        payload = ModelSOMatchScoredPayload(
            match_id=self._match_id,
            winner=winner_block,
            scores=scores,
            winner_player_id=winner_slot,
            winner_loadout_id=self._mech_loadout[self._player_first_mech[winner_slot]],
            winner_score=scores[winner_slot].final_score,
            loser_player_id=loser_slot,
            loser_score=scores[loser_slot].final_score,
            duration_ticks=tick,
            scored_at=self._events.clock.now().isoformat(),
            is_draw=is_draw,
        )
        self._emit(
            self._events.make(
                match_id=self._match_id,
                tick=tick,
                sequence_in_tick=0,  # bus reassigns on publish
                event_type=SOEventType.MATCH_SCORED,
                producer_node=_PRODUCER_NODE,
                subject=_MATCH_SUBJECT,
                payload=payload.model_dump(mode="json"),
                correlation_id=self._correlation_id,
            )
        )

    def _player_score(
        self, player: str, *, victory: int, replay_validity: int
    ) -> ModelSOPlayerScore:
        damage_dealt = self._damage_dealt[player]
        consumed = self._pressure_consumed[player]
        wasted = self._pressure_wasted[player]
        overload_penalty = self._overloads[player]

        damage_efficiency = damage_dealt / (consumed + 1)
        # Nothing consumed -> nothing wasted -> perfect efficiency.
        pressure_efficiency = 1.0 if consumed == 0 else 1.0 - (wasted / consumed)

        return ModelSOPlayerScore(
            victory=victory,
            damage_dealt=damage_dealt,
            damage_efficiency=damage_efficiency,
            pressure_efficiency=pressure_efficiency,
            overload_penalty=overload_penalty,
            replay_validity=replay_validity,
            final_score=compute_final_score(
                victory=victory,
                damage_dealt=damage_dealt,
                pressure_efficiency=pressure_efficiency,
                replay_validity=replay_validity,
                overload_penalty=overload_penalty,
            ),
        )


__all__ = [
    "ModelSOMatchScoredPayload",
    "ModelSOPlayerScore",
    "ModelSOScoredWinner",
    "ReducerScoring",
    "compute_final_score",
    "verify_replay_validity",
]
