"""First concrete live-match evaluator: deterministic win + damage differential.

This is the minimal judgment that proves the live learning spine end-to-end.
It is deliberately conservative and fully deterministic:

- promote ONLY when the learning seat won decisively (no draw) AND out-dealt
  its opponent on damage;
- the candidate is a bounded, fixed-step perturbation of one named numeric
  parameter; at the bound the evaluator returns ``None`` (no candidate) so
  promotion generations cannot run away;
- every derived value (seeds, meta hash, selection reason) is a pure function
  of the match evidence, so re-evaluating the same evidence yields the same
  lineage record byte-for-byte.

Honest limits, recorded here rather than hidden: a single live match is not a
statistical battery.  The lineage record's ``performance`` block therefore
reports the one observed sample (``decisive_n=1``, ``p_value=1.0`` — no
significance claim), and ``evidence.search_seeds`` / ``holdout_seeds`` carry
match-digest-derived identifiers of the live sample, not offline battery
seeds.  The richer ``SelectionOutcomeEvaluator`` (design 2026-07-22 §4.4,
gated through the offline duel machinery) replaces this judgment behind the
same ``LiveLearningEvaluator`` protocol without any rewiring.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from steel_onslaught.contracts.lineage import (
    ModelSOLineageEvidence,
    ModelSOLineageGenerator,
    ModelSOLineagePerformance,
    ModelSOLineagePromotion,
    ModelSOLineageRecord,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence

GENERATOR_ID = "live.win_damage_differential.v1"


def _sample_seed(match_id: str) -> int:
    """Deterministic 31-bit identifier of the live sample (NOT a battery seed)."""

    digest = hashlib.sha256(match_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2**31 - 2)


@dataclass(frozen=True)
class WinDamageDifferentialEvaluator:
    """Deterministic single-match promotion judgment for one learning seat.

    Args:
        learning_player_id: The canonical player id (``player.<side>``) whose
            outcomes drive this policy lane.
        parameter:          The numeric policy parameter perturbed on a win.
        step:               Fixed additive step applied to ``parameter``.
        max_value:          Inclusive bound; at or beyond it no candidate is
            proposed (returns ``None``), capping the promotion chain.
    """

    learning_player_id: str
    parameter: str = "aggression"
    step: float = 0.25
    max_value: float = 3.0

    def __post_init__(self) -> None:
        if not self.learning_player_id:
            raise ValueError("learning_player_id must not be empty")
        if not self.parameter:
            raise ValueError("parameter must not be empty")
        if self.step <= 0:
            raise ValueError("step must be positive")

    def evaluate(
        self,
        *,
        evidence: ModelSOAfterMatchLearningEvidence,
        policy: ModelSOLiveLearningPolicy,
    ) -> ModelSOLineageRecord | None:
        if evidence.is_draw or evidence.winner_player_id != self.learning_player_id:
            return None
        learner_score = evidence.scores.get(self.learning_player_id)
        if learner_score is None:
            return None
        opponent_damage = max(
            (
                score.damage_dealt
                for player_id, score in evidence.scores.items()
                if player_id != self.learning_player_id
            ),
            default=0,
        )
        damage_differential = learner_score.damage_dealt - opponent_damage
        if damage_differential <= 0:
            return None

        current = policy.parameters.get(self.parameter)
        if not isinstance(current, int | float) or isinstance(current, bool):
            raise ValueError(
                f"policy parameter {self.parameter!r} must be numeric to perturb, got {current!r}"
            )
        candidate_value = round(float(current) + self.step, 6)
        if candidate_value > self.max_value:
            return None  # bound reached: no further candidates from this judgment

        candidate_parameters = {**dict(policy.parameters), self.parameter: candidate_value}
        sample = _sample_seed(evidence.match_id)
        opponents = sorted(set(evidence.scores) - {self.learning_player_id})
        return ModelSOLineageRecord(
            archetype=policy.archetype,
            parameters=candidate_parameters,
            spec_hash=spec_hash(policy.archetype, candidate_parameters),
            parent_hash=policy.spec_hash,
            meta_hash=meta_hash(f"live:{player_id}" for player_id in opponents),
            evidence=ModelSOLineageEvidence(
                search_seeds=(sample,),
                holdout_seeds=(sample + 1,),
            ),
            performance=ModelSOLineagePerformance(
                candidate_win_rate=1.0,
                win_rate_delta=0.5,
                overload_rate_delta=0.0,
                draw_rate=0.0,
                p_value=1.0,  # single live sample: explicitly no significance claim
                decisive_n=1,
            ),
            generator=ModelSOLineageGenerator(
                generator_id=GENERATOR_ID,
                selection_reason=(
                    f"live win by {self.learning_player_id} with damage differential "
                    f"+{damage_differential} in match {evidence.match_id}"
                ),
            ),
            promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
        )


__all__ = ["GENERATOR_ID", "WinDamageDifferentialEvaluator"]
