"""SelectionOutcomeEvaluator — the first live evaluator gated by real duels.

Design 2026-07-22 §4.4 stage 2: consume the after-match evidence the projector
already produces (decision/action/reason counters, card learning metrics),
propose ONE candidate parameter perturbation via the existing search lattice
(``learning/search.py``), and gate it through the EXISTING offline duel path —
``run_learning_loop`` (EXTERNAL strategy) over an injected ``EvaluatorProtocol``
which in production is ``DuelEvaluator`` over the composition-built duel
executor.  This deliberately reuses the only learning judgment that has ever
run (search -> paired duels -> stats -> ``evaluate_promotion``) instead of
inventing a second one; ``WinDamageDifferentialEvaluator`` remains the simple
overlay-selectable alternative behind the same ``LiveLearningEvaluator``
protocol.

Determinism: the proposal direction is a pure function of the match evidence
(win -> one lattice step up on the named parameter, loss -> one step down,
draw -> no candidate), the candidate itself comes off the archetype's
quantized bounds lattice, and the duel seed batteries derive from a
sha256-of-evidence master seed — re-evaluating the same evidence replays the
identical gate.  The returned record may be PROMOTED or REJECTED (rejections
are lineage evidence too, exactly like the offline loop); the live
coordinator maps a non-promoted record to a rejected outcome.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from steel_onslaught.contracts.lineage import ModelSOLineageRecord, ParamDict
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.loop import (
    ModelSOLearnConfig,
    SOSearchStrategy,
    run_learning_loop,
)
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds
from steel_onslaught.learning.protocols import (
    BoundsDict,
    EvaluatorProtocol,
    ModelSONumericBound,
)
from steel_onslaught.learning.search import hill_climb_neighbors
from steel_onslaught.learning.spec_adapter import bounds_for_archetype

GENERATOR_ID = "live.selection_outcome.v1"


def derive_master_seed(evidence: ModelSOAfterMatchLearningEvidence) -> int:
    """Deterministic 31-bit master seed for the gate's duel seed batteries.

    Derived from the match identity AND its scored event id so distinct
    terminals never share a battery, while re-evaluating the same evidence
    always replays the same duels.
    """

    digest = hashlib.sha256(f"{evidence.match_id}:{evidence.scored_event_id}".encode()).hexdigest()
    return int(digest[:8], 16) % (2**31 - 2) + 1


def _archetype_bounds_for_policy(policy: ModelSOLiveLearningPolicy) -> BoundsDict:
    """The archetype's full spec-parameter bounds, key-matched to the policy.

    The duel gate materializes real pilot specs, whose parameter models have
    NO defaults, so a duel-gated policy must carry the archetype's complete
    spec-parameter set — a partial or drifted key set is a configuration bug
    that fails here, before any duel spends compute.
    """

    full = bounds_for_archetype(policy.archetype)
    if set(policy.parameters) != set(full):
        missing = sorted(set(full) - set(policy.parameters))
        extra = sorted(set(policy.parameters) - set(full))
        raise ValueError(
            f"a duel-gated policy must carry the complete {policy.archetype!r} "
            f"spec-parameter set; missing={missing} extra={extra}"
        )
    return full


@dataclass(frozen=True)
class SelectionOutcomeEvaluator:
    """Evidence-driven single-candidate proposal gated by offline duels.

    Args:
        learning_player_id: Canonical player id (``player.<side>``) whose
            outcomes drive this policy lane.
        offline_evaluator:  The EXISTING offline evaluator seam — in
            production a ``DuelEvaluator`` over the composition-built duel
            executor; in tests a scripted ``FakeEvaluator``.
        parameter:          The numeric policy parameter perturbed per match.
        step_multiplier:    Lattice indices moved per proposal (>= 1).
        n_search_seeds / n_holdout_seeds: duel battery sizes for the gate.
        thresholds:         The §18 minting thresholds applied by the gate.
    """

    learning_player_id: str
    offline_evaluator: EvaluatorProtocol
    parameter: str = "aggression"
    step_multiplier: int = 1
    n_search_seeds: int = 3
    n_holdout_seeds: int = 2
    thresholds: ModelSOPromotionThresholds = field(default_factory=ModelSOPromotionThresholds)

    def __post_init__(self) -> None:
        if not self.learning_player_id:
            raise ValueError("learning_player_id must not be empty")
        if not self.parameter:
            raise ValueError("parameter must not be empty")
        if self.step_multiplier < 1:
            raise ValueError("step_multiplier must be >= 1")
        if self.n_search_seeds < 1 or self.n_holdout_seeds < 1:
            raise ValueError("duel battery sizes must be >= 1")

    def evaluate(
        self,
        *,
        evidence: ModelSOAfterMatchLearningEvidence,
        policy: ModelSOLiveLearningPolicy,
    ) -> ModelSOLineageRecord | None:
        if evidence.is_draw:
            return None  # a draw carries no directional selection signal
        direction = 1 if evidence.winner_player_id == self.learning_player_id else -1

        bounds = _archetype_bounds_for_policy(policy)
        if self.parameter not in bounds:
            raise ValueError(
                f"perturbation parameter {self.parameter!r} is not a policy parameter "
                f"(policy has {sorted(policy.parameters)})"
            )
        if not isinstance(bounds[self.parameter], ModelSONumericBound):
            raise ValueError(
                f"perturbation parameter {self.parameter!r} must be numeric; "
                "categorical parameters have no evidence direction"
            )
        candidate = self._directional_neighbor(dict(policy.parameters), bounds, direction=direction)
        if candidate is None:
            return None  # lattice bound reached in the evidence direction

        planned = sum(metric.planned_count for metric in evidence.card_learning_metrics)
        dealt = sum(metric.dealt_count for metric in evidence.card_learning_metrics)
        reason = (
            f"selection_outcome:{self.parameter}{'+' if direction > 0 else '-'}"
            f"{self.step_multiplier} from match {evidence.match_id} "
            f"(winner={evidence.winner_player_id}, learner={self.learning_player_id}, "
            f"cards_planned={planned}/{dealt} dealt)"
        )
        config = ModelSOLearnConfig(
            strategy=SOSearchStrategy.EXTERNAL,
            master_seed=derive_master_seed(evidence),
            n_search_seeds=self.n_search_seeds,
            n_holdout_seeds=self.n_holdout_seeds,
            max_evaluations=2,  # exactly one candidate evaluation + the gate
            thresholds=self.thresholds,
        )
        result = run_learning_loop(
            archetype=policy.archetype,
            parent_params=dict(policy.parameters),
            bounds=bounds,
            evaluator=self.offline_evaluator,
            opponent_spec_hashes=[policy.spec_hash],
            config=config,
            candidates=[(candidate, reason)],
            generator_id=GENERATOR_ID,
        )
        return result.record

    def _directional_neighbor(
        self, current: ParamDict, bounds: BoundsDict, *, direction: int
    ) -> ParamDict | None:
        """The single-parameter lattice neighbor in the evidence direction.

        Reuses ``hill_climb_neighbors`` (the existing search machinery) and
        selects the neighbor that moved ONLY ``self.parameter`` the requested
        way; ``None`` when the lattice is already clamped at that edge.
        """

        for neighbor in hill_climb_neighbors(current, bounds, self.step_multiplier):
            changed = [name for name in bounds if neighbor[name] != current[name]]
            if changed != [self.parameter]:
                continue
            delta = float(neighbor[self.parameter]) - float(current[self.parameter])
            if (delta > 0) == (direction > 0):
                return neighbor
        return None


__all__ = ["GENERATOR_ID", "SelectionOutcomeEvaluator", "derive_master_seed"]
