"""Durable after-match learning-evidence effect.

The live match owns truth in the canonical event ledger.  This effect listens
    for each terminal ``MATCH_SCORED`` envelope, reprojects the complete ledger
    stream, and persists only the strict learning-evidence artifact.  It never
changes a pilot, a loadout, a match fold, or a promotion record.

The handler is deliberately independent of the in-process bus implementation:
composition injects the ledger and artifact ports, while the bus supplies only
canonical ``ModelSOEventEnvelope`` values.  The in-memory claim set avoids
reprojecting duplicate terminal deliveries during one process lifetime; the
artifact store's content-addressed first-write-wins contract supplies the same
idempotence across process restarts.

When a promotion port is wired, a promoted outcome additionally appends one
``POLICY_PROMOTED`` event to the promoting match's stream, caused by the
``MATCH_SCORED`` envelope that carried the evidence.  Emission is fail-closed:
wiring a promotion port without the emission capabilities is a composition
error, never a silent skip.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock

from steel_onslaught.contracts.live_learning import ModelSOLiveLearningOutcome
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.factory import EventFactory
from steel_onslaught.events.payloads import ModelSOPolicyPromotedPayload
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.live import LiveLearningPromotionPort
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.ledger.protocol import EventLedger

_PRODUCER_NODE = "node.learning.after_match"

# Promotion is match-scoped policy truth; per-seat provenance arrives with the
# MATCH_STARTED policy-provenance slice (L-GATE-2), so the event carries the
# lifecycle wildcard subject like MATCH_SCORED does.
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")


@dataclass
class AfterMatchLearningHandler:
    """Persist one strict learning-evidence artifact per scored match.

    ``ledger`` and ``artifacts`` are the only capabilities required.  A
    non-terminal envelope is ignored so the handler can safely be attached to
    a wildcard bus in tests or to a transport that does not support filters.
    ``MATCH_SCORED`` is the terminal trigger; projection itself verifies that
    the complete stream contains exactly one canonical score and rejects any
    malformed or mixed-correlation stream before persistence.
    """

    ledger: EventLedger
    artifacts: LearningArtifactStore
    promotion: LiveLearningPromotionPort | None = None
    # Required together with ``promotion``: the bus publish callable and the
    # canonical event factory used to append POLICY_PROMOTED to the stream.
    emit: Callable[[ModelSOEventEnvelope], None] | None = None
    event_factory: EventFactory | None = None
    _processed_match_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.promotion is not None and (self.emit is None or self.event_factory is None):
            raise ValueError(
                "a promotion port requires emit and event_factory so promotions "
                "are event-sourced — silent in-memory promotion is forbidden"
            )

    def handle(self, event: ModelSOEventEnvelope) -> None:
        """Project and persist evidence for one terminal score envelope."""

        if event.event_type is not SOEventType.MATCH_SCORED:
            return

        # EventBus delivery is synchronous today, but the lock keeps the
        # idempotence claim valid for a future transport with concurrent
        # terminal deliveries.  Do not mark a match processed until the store
        # has accepted the artifact; a failed write remains retryable.
        with self._lock:
            if event.match_id in self._processed_match_ids:
                return
            evidence = project_match_learning_evidence(tuple(self.ledger.read_all(event.match_id)))
            self.artifacts.write_after_match_evidence(evidence)
            if self.promotion is not None:
                outcome = self.promotion.handle_after_match(evidence)
                if outcome.status == "promoted":
                    self._emit_policy_promoted(event, outcome)
            self._processed_match_ids.add(event.match_id)

    def _emit_policy_promoted(
        self, scored: ModelSOEventEnvelope, outcome: ModelSOLiveLearningOutcome
    ) -> None:
        """Append the promotion fact, caused by the MATCH_SCORED envelope."""

        promoted = outcome.policy_after
        if promoted is None or promoted.source_lineage_digest is None:
            raise ValueError("promoted outcome must carry a lineage-backed policy_after")
        assert self.emit is not None and self.event_factory is not None  # __post_init__
        payload = ModelSOPolicyPromotedPayload(
            match_id=scored.match_id,
            policy_id=promoted.policy_id,
            archetype=promoted.archetype,
            generation=promoted.generation,
            spec_hash=promoted.spec_hash,
            parent_spec_hash=outcome.policy_before.spec_hash,
            source_lineage_digest=promoted.source_lineage_digest,
            evidence_scored_event_id=scored.event_id,
        )
        self.emit(
            self.event_factory.make(
                match_id=scored.match_id,
                tick=scored.tick,
                sequence_in_tick=0,  # bus reassigns on publish
                event_type=SOEventType.POLICY_PROMOTED,
                producer_node=_PRODUCER_NODE,
                subject=_MATCH_SUBJECT,
                payload=payload.model_dump(mode="json"),
                correlation_id=scored.envelope.correlation_id,
                causation_id=scored.envelope.message_id,
            )
        )


__all__ = ["AfterMatchLearningHandler"]
