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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.artifacts import LearningArtifactStore
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.ledger.protocol import EventLedger


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
    _processed_match_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

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
            self._processed_match_ids.add(event.match_id)


__all__ = ["AfterMatchLearningHandler"]
