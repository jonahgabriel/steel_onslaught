"""After-match promotion boundary for live learning.

This module is intentionally a small orchestration seam around the existing
pure learning loop.  The evaluator is injected, so no provider or filesystem
I/O is hidden here.  A match receives an immutable policy snapshot at
``begin_match``.  ``handle_after_match`` may publish a promoted policy for
future matches, but it cannot mutate any snapshot already admitted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from steel_onslaught.contracts.lineage import ModelSOLineageRecord, SOPromotionStatus
from steel_onslaught.contracts.live_learning import (
    ModelSOLiveLearningOutcome,
    ModelSOLiveLearningPolicy,
    ModelSOLiveMatchPolicySnapshot,
)
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.lineage_store import record_digest


class LearningSeamViolationError(ValueError):
    """A learning-boundary CONTRACT was violated — wiring, not weather.

    This is the loud half of the containment split introduced after the
    L-GATE-2 live-fire crash (findings F1/F2):

    - **Evaluation-runtime failures** (LLM transport errors, duel battery
      aborts, evaluator/store I/O) are facts about the learning lane's
      environment.  The after-match handler CONTAINS them — the live match
      terminal already happened, so they must never re-raise into the bus.
    - **Seam violations** (an un-admitted terminal, a promoted record that
      contradicts the admitted policy, a promotion missing its lineage
      backing) mean the COMPOSITION or an evaluator's contract is wrong.
      Containing those would let a silently no-op learning lane masquerade as
      a healthy one, so they carry this type and the handler re-raises them.

    Subclasses ``ValueError`` so existing callers asserting ``ValueError``
    keep holding.
    """


class LiveLearningEvaluator(Protocol):
    """Evaluate one completed match without owning runtime state."""

    def evaluate(
        self,
        *,
        evidence: ModelSOAfterMatchLearningEvidence,
        policy: ModelSOLiveLearningPolicy,
    ) -> ModelSOLineageRecord | None: ...


class LiveLearningPromotionPort(Protocol):
    """Admission + terminal seam consumed by composition and the after-match
    evidence handler.

    ``begin_match`` MUST be called at match admission on the SAME instance
    that later receives ``handle_after_match`` for that match — the concrete
    coordinator fails closed on un-admitted terminals (the guard that was
    blocker learning-adaptation-03 when the port exposed only the terminal
    half).
    """

    def begin_match(self, match_id: str) -> ModelSOLiveMatchPolicySnapshot: ...

    def handle_after_match(
        self, evidence: ModelSOAfterMatchLearningEvidence
    ) -> ModelSOLiveLearningOutcome: ...


def _policy_from_record(
    record: ModelSOLineageRecord,
    *,
    generation: int,
) -> ModelSOLiveLearningPolicy:
    """Turn a *promoted* lineage record into the next-match policy contract."""

    if record.promotion.status is not SOPromotionStatus.PROMOTED:
        raise ValueError("only promoted lineage records can be fielded")
    return ModelSOLiveLearningPolicy(
        policy_id=f"policy.{record.archetype}.{record.spec_hash[:16]}",
        archetype=record.archetype,
        parameters=record.parameters,
        spec_hash=record.spec_hash,
        generation=generation,
        source_lineage_digest=record_digest(record),
    )


@dataclass
class LiveLearningCoordinator:
    """Coordinate terminal evaluation and next-match policy fielding.

    ``current_policy`` is the only mutable value.  Match snapshots are
    immutable and retained until their terminal evidence is accepted.  If two
    matches overlap and the older one finishes after a newer promotion, its
    candidate is marked ``stale`` instead of rolling the newer policy back.
    """

    current_policy: ModelSOLiveLearningPolicy
    evaluator: LiveLearningEvaluator
    # Durable persistence for the promoted lineage record (the parameter
    # truth the POLICY_PROMOTED event's digests resolve to).  Injected by
    # composition; called BEFORE the in-memory policy advances so a failed
    # write leaves the terminal retryable and never fields an unpersisted
    # policy.  None is only for tests that assert coordinator logic alone.
    persist_lineage: Callable[[ModelSOLineageRecord], None] | None = None
    # The canonical player id (``player.<side>``) whose seat this policy lane
    # governs.  Composition ALWAYS sets it (from the overlay binding) so match
    # assembly can record per-seat policy provenance and route the policy
    # guidance block to the right programmer; assembly fails closed when a
    # wired coordinator is missing it.  None is only for tests that assert
    # coordinator logic alone.
    learning_player_id: str | None = None
    _active: dict[str, ModelSOLiveMatchPolicySnapshot] = field(
        default_factory=dict, init=False, repr=False
    )
    _completed: set[str] = field(default_factory=set, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def begin_match(self, match_id: str) -> ModelSOLiveMatchPolicySnapshot:
        """Capture the policy for one match admission."""

        if not match_id:
            raise ValueError("match_id must not be empty")
        with self._lock:
            if match_id in self._active or match_id in self._completed:
                raise ValueError(f"match {match_id!r} has already been admitted")
            snapshot = ModelSOLiveMatchPolicySnapshot(
                match_id=match_id,
                policy=self.current_policy,
            )
            self._active[match_id] = snapshot
            return snapshot

    def handle_after_match(
        self, evidence: ModelSOAfterMatchLearningEvidence
    ) -> ModelSOLiveLearningOutcome:
        """Evaluate terminal evidence and, only on promotion, field next policy."""

        with self._lock:
            snapshot = self._active.get(evidence.match_id)
            if snapshot is None:
                if evidence.match_id in self._completed:
                    raise LearningSeamViolationError(
                        f"match {evidence.match_id!r} was already completed"
                    )
                raise LearningSeamViolationError(
                    f"match {evidence.match_id!r} must be admitted before terminal evidence"
                )

            # Keep the snapshot active until evaluation and publication succeed;
            # a failed evaluator/store call can therefore be retried safely.
            record = self.evaluator.evaluate(evidence=evidence, policy=snapshot.policy)

            if record is None:
                outcome = ModelSOLiveLearningOutcome(
                    match_id=evidence.match_id,
                    status="rejected",
                    policy_before=snapshot.policy,
                    reason="evaluator_returned_no_candidate",
                )
            elif record.promotion.status is not SOPromotionStatus.PROMOTED:
                outcome = ModelSOLiveLearningOutcome(
                    match_id=evidence.match_id,
                    status="rejected",
                    policy_before=snapshot.policy,
                    reason="candidate_failed_promotion_gate",
                )
            elif record.archetype != snapshot.policy.archetype:
                raise LearningSeamViolationError(
                    "promoted candidate archetype does not match admitted policy: "
                    f"{record.archetype!r} != {snapshot.policy.archetype!r}"
                )
            elif record.parent_hash != snapshot.policy.spec_hash:
                raise LearningSeamViolationError(
                    "promoted candidate parent does not match admitted policy: "
                    f"{record.parent_hash!r} != {snapshot.policy.spec_hash!r}"
                )
            elif record.spec_hash == snapshot.policy.spec_hash:
                raise LearningSeamViolationError(
                    "promoted candidate must change the admitted policy"
                )
            # A concurrent match may have promoted from a newer policy while
            # this snapshot was active.  Never roll that policy backwards.
            elif self.current_policy.spec_hash != snapshot.policy.spec_hash:
                outcome = ModelSOLiveLearningOutcome(
                    match_id=evidence.match_id,
                    status="stale",
                    policy_before=snapshot.policy,
                    reason="admitted_policy_is_no_longer_current",
                )
            else:
                if self.persist_lineage is not None:
                    self.persist_lineage(record)
                next_policy = _policy_from_record(
                    record,
                    generation=snapshot.policy.generation + 1,
                )
                outcome = ModelSOLiveLearningOutcome(
                    match_id=evidence.match_id,
                    status="promoted",
                    policy_before=snapshot.policy,
                    policy_after=next_policy,
                    reason="candidate_passed_promotion_gate",
                )
                self.current_policy = next_policy

            self._active.pop(evidence.match_id)
            self._completed.add(evidence.match_id)
            return outcome


__all__ = [
    "LearningSeamViolationError",
    "LiveLearningCoordinator",
    "LiveLearningEvaluator",
    "LiveLearningPromotionPort",
]
