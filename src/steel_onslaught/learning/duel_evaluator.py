"""Real deterministic duel evaluator over an injected duel capability."""

from __future__ import annotations

from collections.abc import Sequence

from steel_onslaught.contracts.card_learning import (
    ModelSOCardLearningMetric,
    aggregate_card_learning_metrics,
)
from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.artifacts import (
    EvaluationWorkspace,
    LearningArtifactStore,
    MaterializedLoadout,
)
from steel_onslaught.learning.post_match import project_card_learning_metrics
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.learning.spec_adapter import spec_from_params
from steel_onslaught.llm.schemas import LlmTransportError
from steel_onslaught.match.duel import DuelExecutor, DuelResult, ModelSOEvaluationStorageKey

_SIDE_RED = "red"
_SIDE_BLUE = "blue"

_TEMPLATE_ID_FORMAT = "pilot.template.{archetype}"


class DuelBatteryError(RuntimeError):
    """One duel of an evaluation battery could not produce a result.

    Raised after the bounded transport-retry budget is exhausted (or
    immediately for a non-retryable transport error).  This is an
    evaluation-RUNTIME failure, not a seam violation: the after-match handler
    contains it, the gate never sees the incomplete battery, and declining is
    the safe verdict — a candidate is never promoted on partial evidence
    (L-GATE-2 live-fire finding F2).
    """

    def __init__(self, message: str, *, match_id: str, attempts: int) -> None:
        super().__init__(message)
        self.match_id = match_id
        self.attempts = attempts


def aggregate_pair(first: SOSeedWinner, second: SOSeedWinner) -> SOSeedWinner:
    """Pure pair aggregation per Architectural Decision #2: CANDIDATE+CANDIDATE
    -> CANDIDATE, PARENT+PARENT -> PARENT, all 7 other combinations -> DRAW.
    Inputs are already side-normalized (each duel's winner mapped to
    candidate/parent/draw by the caller)."""
    if first is SOSeedWinner.CANDIDATE and second is SOSeedWinner.CANDIDATE:
        return SOSeedWinner.CANDIDATE
    if first is SOSeedWinner.PARENT and second is SOSeedWinner.PARENT:
        return SOSeedWinner.PARENT
    return SOSeedWinner.DRAW


class DuelEvaluator:
    """EvaluatorProtocol implementation that runs real deterministic duels.

    Per seed: two duels with sides swapped, candidate and parent fielding the
    SAME base loadout (chassis, boiler, modules — only pilot parameters differ).
    candidate_overloads / parent_overloads = count of BOILER_OVERLOADED ledger
    events for that side's mech, summed over the seed's two duels.
    """

    def __init__(
        self,
        *,
        archetype: str,
        base_loadout: ModelSOLoadout,
        max_ticks: int,
        duel_executor: DuelExecutor,
        artifacts: LearningArtifactStore,
        transport_retry_budget: int = 2,
    ) -> None:
        if transport_retry_budget < 0:
            raise ValueError("transport_retry_budget must be >= 0")
        self._archetype = archetype
        self._max_ticks = max_ticks
        self._base = base_loadout
        self._duel_executor = duel_executor
        self._artifacts = artifacts
        # Bounded retry for RETRYABLE transport failures inside the battery,
        # reusing the live LLM client's classification (LlmTransportError
        # .retryable) rather than a second retry stack.  The live-play HTTP
        # binding deliberately pins max_attempts=1 (a mid-match retry would
        # stall live ticks); a duel battery has no such constraint, so the
        # retry lives HERE, at duel granularity.  Each retry re-runs the
        # whole deterministic duel against a FRESH evidence target (the
        # storage allocator is exclusive-create; a failed attempt's partial
        # ledger is retained as forensic evidence but contributes nothing).
        self._transport_retry_budget = transport_retry_budget
        # Per-instance evaluate counter: each call gets its own subdirectory so
        # ledgers from distinct calls never collide and the gate evaluation's
        # ledgers can be retained as replay evidence.
        self._eval_count = 0

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        """One outcome per seed, in the given seed order (EvaluatorProtocol)."""
        seed_list = list(seeds)
        if len(set(seed_list)) != len(seed_list):
            duplicates = sorted({s for s in seed_list if seed_list.count(s) > 1})
            raise ValueError(f"duplicate seeds in evaluation battery: {duplicates}")

        self._eval_count += 1
        workspace = self._artifacts.prepare_evaluation(self._eval_count)
        candidate_loadout, parent_loadout = self._materialize(
            workspace, candidate_params, parent_params
        )

        outcomes: list[ModelSOSeedOutcome] = []
        for seed in seed_list:
            # Side-swapped pair (Decision #2): candidate fields red, then blue.
            first, cand_first, par_first, cand_metrics_first, par_metrics_first = self._duel(
                workspace,
                seed=seed,
                loadout_red=candidate_loadout,
                loadout_blue=parent_loadout,
                candidate_side=_SIDE_RED,
            )
            second, cand_second, par_second, cand_metrics_second, par_metrics_second = self._duel(
                workspace,
                seed=seed,
                loadout_red=parent_loadout,
                loadout_blue=candidate_loadout,
                candidate_side=_SIDE_BLUE,
            )
            outcomes.append(
                ModelSOSeedOutcome(
                    seed=seed,
                    winner=aggregate_pair(first, second),
                    candidate_overloads=cand_first + cand_second,
                    parent_overloads=par_first + par_second,
                    candidate_card_learning_metrics=aggregate_card_learning_metrics(
                        (cand_metrics_first, cand_metrics_second)
                    ),
                    parent_card_learning_metrics=aggregate_card_learning_metrics(
                        (par_metrics_first, par_metrics_second)
                    ),
                )
            )
        return outcomes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _materialize(
        self,
        workspace: EvaluationWorkspace,
        candidate_params: ParamDict,
        parent_params: ParamDict,
    ) -> tuple[MaterializedLoadout, MaterializedLoadout]:
        """Write the two pilot spec YAMLs + two derived loadout YAMLs (pinned).

        The parent spec's ``lineage.parent`` is the archetype's template id
        (path-resolved specs must have a non-null parent — characterization
        (c)); the candidate spec's ``lineage.parent`` is the parent spec's id.
        """
        parent_hash = spec_hash(self._archetype, parent_params)
        candidate_hash = spec_hash(self._archetype, candidate_params)
        parent_spec = spec_from_params(
            archetype=self._archetype,
            params=parent_params,
            spec_id=f"pilot.learn.par_{parent_hash[:12]}",
            parent_id=_TEMPLATE_ID_FORMAT.format(archetype=self._archetype),
            display_name=f"Learn parent {parent_hash[:12]}",
        )
        candidate_spec = spec_from_params(
            archetype=self._archetype,
            params=candidate_params,
            spec_id=f"pilot.learn.cand_{candidate_hash[:12]}",
            parent_id=parent_spec.id,
            display_name=f"Learn candidate {candidate_hash[:12]}",
        )
        candidate_loadout = self._artifacts.materialize_loadout(
            workspace,
            base=self._base,
            spec=candidate_spec,
            role="cand",
        )
        parent_loadout = self._artifacts.materialize_loadout(
            workspace,
            base=self._base,
            spec=parent_spec,
            role="par",
        )
        return candidate_loadout, parent_loadout

    def _duel(
        self,
        workspace: EvaluationWorkspace,
        *,
        seed: int,
        loadout_red: MaterializedLoadout,
        loadout_blue: MaterializedLoadout,
        candidate_side: str,
    ) -> tuple[
        SOSeedWinner,
        int,
        int,
        tuple[ModelSOCardLearningMetric, ...],
        tuple[ModelSOCardLearningMetric, ...],
    ]:
        """Run one duel; return (side-normalized winner, candidate_overloads,
        parent_overloads) for this duel alone."""
        parent_side = _SIDE_BLUE if candidate_side == _SIDE_RED else _SIDE_RED
        base_match_id = f"match.learn.seed_{seed}.cand_{candidate_side}"
        base_duel_key = f"seed_{seed}_cand_{candidate_side}"
        result = self._run_duel_with_bounded_retry(
            workspace,
            seed=seed,
            loadout_red=loadout_red,
            loadout_blue=loadout_blue,
            base_match_id=base_match_id,
            base_duel_key=base_duel_key,
        )
        match_id = result.final_state.match_id
        final = result.final_state
        if final.winner_id is None:
            winner = SOSeedWinner.DRAW
        elif final.winner_id == f"player.{candidate_side}":
            winner = SOSeedWinner.CANDIDATE
        elif final.winner_id == f"player.{parent_side}":
            winner = SOSeedWinner.PARENT
        else:  # pragma: no cover - lifecycle invariant violation
            raise ValueError(f"unrecognized winner_id {final.winner_id!r} in {match_id}")
        candidate_overloads = self._count_overloads(
            result.events, mech_id=f"mech.{candidate_side}.01"
        )
        parent_overloads = self._count_overloads(result.events, mech_id=f"mech.{parent_side}.01")
        candidate_metrics = project_card_learning_metrics(
            result.events, mech_id=f"mech.{candidate_side}.01"
        )
        parent_metrics = project_card_learning_metrics(
            result.events, mech_id=f"mech.{parent_side}.01"
        )
        return winner, candidate_overloads, parent_overloads, candidate_metrics, parent_metrics

    def _run_duel_with_bounded_retry(
        self,
        workspace: EvaluationWorkspace,
        *,
        seed: int,
        loadout_red: MaterializedLoadout,
        loadout_blue: MaterializedLoadout,
        base_match_id: str,
        base_duel_key: str,
    ) -> DuelResult:
        """One duel, retried on RETRYABLE transport errors within the budget.

        Attempt N > 1 uses a ``.retryK``/``_retryK``-suffixed match id and
        storage key so every attempt writes to a never-before-used evidence
        target (the allocator is exclusive-create by contract).  A
        non-retryable transport error, or budget exhaustion, raises
        ``DuelBatteryError`` — the battery is incomplete and the gate must
        DECLINE, never promote on partial evidence.
        """

        max_attempts = 1 + self._transport_retry_budget
        last_error: LlmTransportError | None = None
        for attempt in range(1, max_attempts + 1):
            suffix = "" if attempt == 1 else f"retry{attempt - 1}"
            match_id = base_match_id if not suffix else f"{base_match_id}.{suffix}"
            storage = ModelSOEvaluationStorageKey(
                namespace=workspace.key,
                duel=base_duel_key if not suffix else f"{base_duel_key}_{suffix}",
            )
            try:
                return self._duel_executor(
                    loadout_a=loadout_red.loadout,
                    loadout_b=loadout_blue.loadout,
                    seed=seed,
                    max_ticks=self._max_ticks,
                    storage=storage,
                    match_id=match_id,
                    loadout_path_a=loadout_red.path,
                    loadout_path_b=loadout_blue.path,
                    side_a=_SIDE_RED,
                    side_b=_SIDE_BLUE,
                )
            except LlmTransportError as exc:
                last_error = exc
                if not exc.retryable:
                    raise DuelBatteryError(
                        f"duel {match_id!r} failed with a non-retryable transport "
                        f"error on attempt {attempt}: {exc}",
                        match_id=base_match_id,
                        attempts=attempt,
                    ) from exc
        raise DuelBatteryError(
            f"duel {base_match_id!r} exhausted its transport retry budget "
            f"({max_attempts} attempts): {last_error}",
            match_id=base_match_id,
            attempts=max_attempts,
        ) from last_error

    @staticmethod
    def _count_overloads(events: tuple[ModelSOEventEnvelope, ...], *, mech_id: str) -> int:
        """Count BOILER_OVERLOADED ledger events for one mech in one duel."""
        return sum(
            1
            for envelope in events
            if envelope.event_type is SOEventType.BOILER_OVERLOADED
            and envelope.subject.mech_id == mech_id
        )
