"""Replay engine — Tasks 27 + 34.

Reads events from an ``EventLedger`` in canonical order
``(tick ASC, sequence_in_tick ASC, event_id ASC)`` and folds them through
``MatchStateFold`` — the SAME fold the live match runner subscribes to the
bus — producing a ``ModelSOMatchState`` that is ``==`` to the live final
state by construction (R9 / Architectural Decision #6).

The fold consumes only canonical resolved events; intent / telemetry events
in the ledger pass through it as no-ops, and fold-internal emissions are
suppressed on the replay path (``bus=None``) because the live copies of those
events arrive from the ledger as idempotent re-statements.

API
---
``ReplayEngine`` is stateful: it tracks a ``_cursor_tick`` that is advanced by
``step_forward`` / ``step_backward`` and reset by ``reconstruct_at_tick``.

Usage::

    replay = ReplayEngine(ledger, match_id="match.2026-04-30.001", catalog=catalog)
    final  = replay.reconstruct_at_tick(200)   # fold through all events
    state3 = replay.reconstruct_at_tick(3)      # fold only through tick 3
    t4     = replay.step_forward()              # advance one tick
    t3_    = replay.step_backward()             # retreat one tick
"""

from __future__ import annotations

from collections.abc import Callable

from steel_onslaught.contracts.arena import ModelSOCurrentLiveArenaSnapshot
from steel_onslaught.contracts.card import ModelSOCardCatalog
from steel_onslaught.contracts.card_runtime import ModelSOCardRuntimeSnapshot
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import ModelSOMatchStartedPayload
from steel_onslaught.ledger.protocol import EventLedger
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.persona_prompts import ModelSOMatchPromptProvenance
from steel_onslaught.pilots.programming import ModelSOCardRulePackProvenance
from steel_onslaught.replay.card_round import (
    ModelSOCardRoundReplay,
    validate_card_event_stream,
)
from steel_onslaught.replay.migrations import migrate_historical_match_started_arena

CardRoundEventValidator = Callable[..., tuple[ModelSOCardRoundReplay, ...]]


class ReplayEngine:
    """Reconstruct ``ModelSOMatchState`` at any tick from a ledger.

    Args:
        ledger:   Event ledger holding the target match's canonical events.
        match_id: The match identifier whose events are replayed.
        catalog:  Already resolved static contract catalog for the fold.
        card_catalog: Optional immutable card snapshot selected by the same
                      composition root as live execution. Card events remain
                      outside this fold until the register-runtime slice.
        card_runtime_snapshot: Optional immutable card/deck snapshot. Required
                      when ``validate_card_events`` is enabled.
        validate_card_events: Opt-in complete-stream card lifecycle validation;
                      the validated evidence is retained but never folded into
                      ``ModelSOMatchState``.
        card_round_validator: Optional injected stream validator with the same
                      keyword arguments as ``validate_card_event_stream``.

    The engine caches the full ordered event list on first construction to
    avoid repeated ledger scans.  The ledger is expected to be complete
    (match has ended) before replay is meaningful, though partial replays
    for running matches are supported.
    """

    def __init__(
        self,
        ledger: EventLedger,
        match_id: str,
        *,
        catalog: MatchContractCatalog,
        event_factory: EventFactory,
        card_catalog: ModelSOCardCatalog | None = None,
        card_runtime_snapshot: ModelSOCardRuntimeSnapshot | None = None,
        card_rule_pack_provenance: ModelSOCardRulePackProvenance | None = None,
        prompt_provenance: ModelSOMatchPromptProvenance | None = None,
        historical_arena_migration: ModelSOCurrentLiveArenaSnapshot | None = None,
        card_round_validator: CardRoundEventValidator | None = None,
        validate_card_events: bool = False,
    ) -> None:
        self._ledger = ledger
        self._match_id = match_id
        self._catalog = catalog
        # Keep the composition snapshot available to replay without activating
        # card-event folding; register gameplay is a later slice.
        self._card_catalog = (
            card_catalog
            if card_catalog is not None
            else card_runtime_snapshot.card_catalog
            if card_runtime_snapshot is not None
            else None
        )
        self._card_runtime_snapshot = card_runtime_snapshot
        if card_rule_pack_provenance is not None and not isinstance(
            card_rule_pack_provenance, ModelSOCardRulePackProvenance
        ):
            raise TypeError(
                "card_rule_pack_provenance must be ModelSOCardRulePackProvenance when supplied"
            )
        self._card_rule_pack_provenance = card_rule_pack_provenance
        if prompt_provenance is not None and not isinstance(
            prompt_provenance, ModelSOMatchPromptProvenance
        ):
            raise TypeError("prompt_provenance must be ModelSOMatchPromptProvenance when supplied")
        self._prompt_provenance = prompt_provenance
        if card_runtime_snapshot is not None and card_catalog is not None:
            if card_runtime_snapshot.card_catalog is not card_catalog:
                raise ValueError("card_catalog and card_runtime_snapshot must share identity")
        self._event_factory = event_factory
        self._historical_arena_migration = historical_arena_migration
        if not isinstance(validate_card_events, bool):
            raise TypeError("validate_card_events must be a bool")
        if card_round_validator is not None and not callable(card_round_validator):
            raise TypeError("card_round_validator must be callable when supplied")
        # Cache the full canonical event list once.
        self._events: list[ModelSOEventEnvelope] = list(ledger.read_all(match_id))
        if not self._events:
            raise ValueError(f"no events for match_id={match_id!r}")
        if card_round_validator is not None or validate_card_events:
            if self._card_runtime_snapshot is None:
                raise ValueError("card event validation requires an injected card_runtime_snapshot")
            validator = card_round_validator or validate_card_event_stream
            # Validate the complete cached stream exactly once. Prefix folds
            # must never feed an incomplete card lifecycle into the parser.
            self._validated_card_rounds = tuple(
                validator(
                    self._events,
                    snapshot=self._card_runtime_snapshot,
                    expected_match_id=self._match_id,
                    expected_provenance=self._card_runtime_snapshot.provenance,
                )
            )
        else:
            self._validated_card_rounds = ()
        # ONEX workflow correlation id shared across every event of this match.
        # Derived from the ledger (the replay path never emits, so the fold's
        # bus=None; correlation_id is threaded only to satisfy the factory
        # signature and stays unused on this path). All events of one match
        # share it (the runner generates one per match).
        self._correlation_id = self._events[0].correlation_id
        # Current cursor position — updated by reconstruct_at_tick / step_*.
        self._cursor_tick: int = 0

    # ------------------------------------------------------------------
    # Public API (matches the plan's spec)
    # ------------------------------------------------------------------

    def reconstruct_at_tick(self, tick: int) -> ModelSOMatchState:
        """Fold all events up to and including *tick* through the reducer stack.

        Sets the internal cursor to *tick* (clamped to [0, all_ticks()[-1]]).
        Returns the reconstructed ``ModelSOMatchState``.

        Args:
            tick: Target tick number (0 = initial state after MATCH_STARTED).

        Returns:
            ``ModelSOMatchState`` after folding all events with tick <= *tick*.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        clamped = max(all_t[0], min(tick, all_t[-1]))
        self._cursor_tick = clamped
        return self._fold_up_to(clamped)

    def step_forward(self) -> ModelSOMatchState:
        """Advance one tick and return the reconstructed state.

        Clamps at the final tick — if already at the end, returns the current
        (final) state unchanged.
        """
        all_t = self.all_ticks()
        if not all_t:
            raise ValueError(f"no events for match_id={self._match_id!r}")
        final_tick = all_t[-1]
        next_tick = min(self._cursor_tick + 1, final_tick)
        self._cursor_tick = next_tick
        return self._fold_up_to(next_tick)

    def step_backward(self) -> ModelSOMatchState:
        """Retreat one tick and return the reconstructed state.

        Clamps at tick 0 — if already at the start, returns the tick-0 state.
        """
        prev_tick = max(self._cursor_tick - 1, 0)
        self._cursor_tick = prev_tick
        return self._fold_up_to(prev_tick)

    def all_ticks(self) -> list[int]:
        """Return a sorted list of all distinct tick numbers in the ledger.

        Tick 0 is always present (MATCH_STARTED is emitted at tick 0 by
        ``InProcessEventBus`` before the first ``MATCH_TICK``).
        """
        seen: dict[int, None] = {}  # ordered-set via dict insertion order
        for e in self._events:
            seen[e.tick] = None
        return list(seen)

    @property
    def card_catalog(self) -> ModelSOCardCatalog | None:
        """Return the immutable composition snapshot retained for later card replay."""
        return self._card_catalog

    @property
    def card_runtime_snapshot(self) -> ModelSOCardRuntimeSnapshot | None:
        """Return the immutable composition snapshot retained for replay."""

        return self._card_runtime_snapshot

    @property
    def validated_card_rounds(self) -> tuple[ModelSOCardRoundReplay, ...]:
        """Return immutable card-round evidence validated at construction.

        The tuple is empty for the default replay path or a match with no
        card lifecycle events. Card rounds remain outside
        ``ModelSOMatchState`` and the canonical fold is unchanged.
        """

        return self._validated_card_rounds

    def events_at_tick(self, tick: int) -> list[ModelSOEventEnvelope]:
        """Return all events for *tick* in canonical order
        ``(sequence_in_tick ASC, event_id ASC)``.

        Returns an empty list if *tick* is not present in the ledger.
        """
        at_tick = [e for e in self._events if e.tick == tick]
        return sorted(at_tick, key=lambda e: (e.sequence_in_tick, e.event_id))

    # ------------------------------------------------------------------
    # Internal fold implementation
    # ------------------------------------------------------------------

    def _fold_up_to(self, target_tick: int) -> ModelSOMatchState:
        """Fold events with tick <= *target_tick* through ``MatchStateFold``.

        A fresh fold per call keeps reconstruction stateless and exact: the
        result is a pure function of the canonical event prefix.
        """
        fold = MatchStateFold(
            self._match_id,
            self._correlation_id,
            bus=None,
            event_factory=self._event_factory,
            catalog=self._catalog,
            historical_arena_migration=self._historical_arena_migration,
        )
        for event in self._events:
            if event.tick > target_tick:
                break
            if event.event_type is SOEventType.MATCH_STARTED and "arena" not in event.payload:
                if self._historical_arena_migration is None:
                    raise ValueError(
                        "historical MATCH_STARTED requires explicit offline arena migration"
                    )
                event = migrate_historical_match_started_arena(
                    event,
                    arena=self._historical_arena_migration,
                )
            self._validate_card_runtime_provenance(event)
            self._validate_card_rule_pack_provenance(event)
            self._validate_prompt_provenance(event)
            fold.apply(event)
        return fold.state

    def _validate_card_runtime_provenance(self, event: ModelSOEventEnvelope) -> None:
        """Check optional start provenance against the injected snapshot."""

        if event.event_type is not SOEventType.MATCH_STARTED:
            return
        payload = ModelSOMatchStartedPayload.model_validate(event.payload)
        recorded = payload.card_runtime_provenance
        snapshot = self._card_runtime_snapshot
        if snapshot is None and recorded is None:
            return
        if snapshot is None:
            raise ValueError(
                "MATCH_STARTED carries card runtime provenance but replay has no snapshot"
            )
        expected = snapshot.provenance
        if expected is None and recorded is None:
            return
        if expected is None or recorded is None or recorded != expected:
            raise ValueError("card runtime provenance does not match the replay snapshot")

    def _validate_prompt_provenance(self, event: ModelSOEventEnvelope) -> None:
        """Reject replay when the effective pilot prompts drift.

        A persona prompt is a decision input, so an edited prompt must be
        detectable at replay.  Unlike the opt-in card rule pack, *every*
        match records prompt provenance, so a mandatory expected value would
        force every bare state-reconstruction caller to re-derive prompts.
        Instead this is opt-in verification: ``model_validate`` above already
        proves the recorded provenance is internally consistent (its digest
        matches its own prompt text), and a strict caller — the
        composition-driven replay-validity check run at scoring — supplies the
        expected value so a recomposition that changed a prompt fails closed.
        """

        if event.event_type is not SOEventType.MATCH_STARTED:
            return
        payload = ModelSOMatchStartedPayload.model_validate(event.payload)
        expected = self._prompt_provenance
        if expected is None:
            # No external expectation; the recorded value is self-validating.
            return
        recorded = payload.prompt_provenance
        if recorded is None or recorded != expected:
            raise ValueError("effective prompt provenance does not match the replay composition")

    def _validate_card_rule_pack_provenance(self, event: ModelSOEventEnvelope) -> None:
        """Reject replay when the selected card-rule pack is absent or drifts."""

        if event.event_type is not SOEventType.MATCH_STARTED:
            return
        payload = ModelSOMatchStartedPayload.model_validate(event.payload)
        recorded = payload.card_rule_pack_provenance
        expected = self._card_rule_pack_provenance
        if expected is None and recorded is None:
            return
        if expected is None:
            raise ValueError(
                "MATCH_STARTED carries card rule-pack provenance but replay has no pack"
            )
        if recorded is None or recorded != expected:
            raise ValueError("card rule-pack provenance does not match the replay pack")
