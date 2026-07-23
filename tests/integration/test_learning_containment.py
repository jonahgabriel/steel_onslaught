"""L-GATE-2 containment regression tests (live-fire findings F1/F2).

RUN B attempt 1 of the L-GATE-2 significance battery crashed a LIVE match:
one holdout duel's LLM call raised a retryable ``LlmTransportError`` and the
exception propagated UNCONTAINED through ``DuelEvaluator -> run_learning_loop
-> LiveLearningCoordinator.handle_after_match -> AfterMatchLearningHandler ->
bus publish -> MatchRunner tick`` as a nested ``ExceptionGroup``, killing the
match whose terminal had already been scored.

These tests drive the EXACT crash chain through the real seam (real match,
real bus, real handler, real coordinator, real ``SelectionOutcomeEvaluator``
over a real ``DuelEvaluator``; only the innermost duel executor is scripted so
a transport failure can be injected deterministically) and lock in:

- (a) a transport failure inside the duel battery is retried, then contained:
  the live match terminal is unaffected, the evidence artifact is written, a
  typed contained-failure outcome is recorded, and NO exception reaches the
  runner (RED on the pre-fix tree: ``runner.run()`` raises ExceptionGroup);
- (c) a transient transport failure that clears on retry changes nothing: the
  battery completes and a winning candidate still promotes normally.

The seam-violation half — an UN-admitted terminal must still raise through
the real bus — stays locked by
``test_unadmitted_terminal_still_fails_closed_through_the_real_seam`` in
``test_live_learning_loop.py`` plus the unit tests in
``tests/learning/test_live.py`` / ``test_after_match.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.duel_evaluator import DuelEvaluator
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.live import LiveLearningCoordinator
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds
from steel_onslaught.learning.selection_outcome import SelectionOutcomeEvaluator
from steel_onslaught.llm.schemas import LlmTransportError
from steel_onslaught.match.composition import (
    LiveMatchStack,
    assemble_match_with_dependencies,
    build_runtime_dependencies,
    load_loadout,
)
from steel_onslaught.match.duel import DuelResult, ModelSOEvaluationStorageKey
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from tests.overlay import complete_test_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RED = _REPO_ROOT / "contracts_data/loadouts/proof_red_predictive_ironclad.yaml"
_BLUE = _REPO_ROOT / "contracts_data/loadouts/proof_blue_aggressive_hunter.yaml"
_DUEL_BASE = _REPO_ROOT / "contracts_data/loadouts/example_aggressive_light.yaml"
_ARCHETYPE = "aggressive"
_LEARNER = "player.red"
_PARAMETER = "mode_switch_heat_ceiling"

# Deterministic proof-pilot live match (same constant as
# test_live_learning_loop.py): seed 12345 -> red wins, so the evaluator
# proposes an upward candidate and the duel battery IS consulted.
_LIVE_SEED = 12345

# The complete aggressive spec-parameter set (the duel gate materializes real
# pilot specs whose parameter models have no defaults).
_FULL_PARAMS: ParamDict = {
    "vent_at_heat_margin": 10.0,
    "idle_vent_heat_threshold": 70.0,
    "mode_switch_pressure_floor": 20.0,
    "mode_switch_heat_ceiling": 60.0,
    "weapon_preference": "highest_damage",
}

_RELAXED = ModelSOPromotionThresholds(
    p_value_max=1.0,
    min_decisive_n=1,
    max_overload_rate_increase=10.0,
    max_draw_rate=1.0,
    min_param_distance=0.0,
)


def _overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    raw: dict[str, Any] = {
        "schema_version": "1",
        "bus": {"kind": "in_process"},
        "event_ledger": {
            "kind": "sqlite",
            "path": tmp_path / "events.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
        },
        "leaderboard": {
            "kind": "sqlite",
            "path": tmp_path / "leaderboard.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "storage_schema": "leaderboard_v1",
        },
        "learning_artifacts": {
            "kind": "filesystem_yaml",
            "evaluation_root": tmp_path / "evaluations",
            "lineage_root": tmp_path / "lineage",
        },
        "evaluation_storage": {
            "kind": "sqlite",
            "root": tmp_path / "evaluations",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
            "leaderboard_schema": "leaderboard_v1",
        },
        "contracts": {
            "catalog_dir": _REPO_ROOT / "contracts_data",
            "pilot_registry_dir": _REPO_ROOT / "contracts_data/pilots",
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }
    return ModelSOApplicationOverlay.model_validate(complete_test_overlay(raw, tmp_path))


@dataclass
class _RecordedCall:
    match_id: str
    storage: ModelSOEvaluationStorageKey


@dataclass
class _ScriptedDuelExecutor:
    """Innermost duel-executor double: fail N times, then script real results.

    ``failures`` counts injected retryable transport failures; after they are
    consumed, every duel returns a terminal state in which the CANDIDATE side
    (identified by its materialized ``loadout.learn.cand_*.yaml`` path) wins —
    so the retry-then-success path can reach a real promotion verdict.  With
    ``failures`` set high the executor never succeeds, reproducing RUN B
    attempt 1's uncontained-crash shape.
    """

    failures: int
    calls: list[_RecordedCall] = field(default_factory=list)

    def __call__(
        self,
        *,
        loadout_a: Any,
        loadout_b: Any,
        seed: int,
        max_ticks: int,
        storage: ModelSOEvaluationStorageKey,
        match_id: str,
        loadout_path_a: Path | None,
        loadout_path_b: Path | None,
        side_a: str,
        side_b: str,
    ) -> DuelResult:
        self.calls.append(_RecordedCall(match_id=match_id, storage=storage))
        if self.failures > 0:
            self.failures -= 1
            raise LlmTransportError("injected mid-duel transport failure", retryable=True)
        assert loadout_path_a is not None and loadout_path_b is not None
        winner_side = side_a if ".cand_" in loadout_path_a.name else side_b
        return DuelResult(
            final_state=ModelSOMatchState(
                match_id=match_id,
                tick=1,
                status=SOMatchStatus.ENDED,
                seed=seed,
                winner_id=f"player.{winner_side}",
                end_reason=SOMatchEndReason.LAST_MECH_STANDING,
            ),
            events=(),
        )


def _assemble(
    tmp_path: Path, executor: _ScriptedDuelExecutor
) -> tuple[LiveMatchStack, LiveLearningCoordinator, AfterMatchLearningHandler]:
    """The RUN B attempt-1 wiring: real stack + real learning chain, admitted."""

    dependencies = build_runtime_dependencies(_overlay(tmp_path))
    identity = MatchIdentity(
        match_id=dependencies.identities.new_match_id(),
        correlation_id=dependencies.identities.new_correlation_id(),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=load_loadout(_RED),
        blue=load_loadout(_BLUE),
        red_loadout_path=_RED,
        blue_loadout_path=_BLUE,
        seed=_LIVE_SEED,
        max_ticks=200,
        identity=identity,
    )
    artifacts = YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=tmp_path / "gate_evaluations",
            lineage_root=tmp_path / "gate_lineage",
            experiment_root=tmp_path / "gate_experiments",
        )
    )
    genesis = ModelSOLiveLearningPolicy(
        policy_id=f"policy.{_ARCHETYPE}.genesis",
        archetype=_ARCHETYPE,
        parameters=dict(_FULL_PARAMS),
        spec_hash=spec_hash(_ARCHETYPE, _FULL_PARAMS),
        generation=0,
    )
    coordinator = LiveLearningCoordinator(
        current_policy=genesis,
        evaluator=SelectionOutcomeEvaluator(
            learning_player_id=_LEARNER,
            offline_evaluator=DuelEvaluator(
                archetype=_ARCHETYPE,
                base_loadout=load_loadout(_DUEL_BASE),
                max_ticks=40,
                duel_executor=executor,
                artifacts=artifacts,
            ),
            parameter=_PARAMETER,
            n_search_seeds=1,
            n_holdout_seeds=1,
            thresholds=_RELAXED,
        ),
        learning_player_id=_LEARNER,
    )
    coordinator.begin_match(identity.match_id)
    handler = AfterMatchLearningHandler(
        ledger=stack.ledger,
        artifacts=artifacts,
        promotion=coordinator,
        emit=stack.bus.publish,
        event_factory=stack.event_factory,
    )
    stack.bus.subscribe(handler.handle, event_types=[SOEventType.MATCH_SCORED])
    return stack, coordinator, handler


@pytest.mark.integration
def test_transport_failure_in_duel_battery_cannot_kill_the_live_match(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Finding F2 locked shut: the RUN B attempt-1 crash chain, contained.

    The executor NEVER recovers (every attempt raises a retryable
    ``LlmTransportError``), so the bounded retry exhausts and the battery
    errors.  On the pre-fix tree this exact wiring killed the live match:
    ``runner.run()`` raised a nested ExceptionGroup out of the MATCH_SCORED
    publish.  Post-fix the match completes, the evidence artifact is intact,
    the failure is a typed contained outcome, and the policy did not move.
    """

    executor = _ScriptedDuelExecutor(failures=10_000)
    stack, coordinator, handler = _assemble(tmp_path, executor)
    genesis = coordinator.current_policy
    try:
        with caplog.at_level("ERROR", logger="steel_onslaught.learning.after_match"):
            final = stack.runner.run()  # RED (pre-fix): ExceptionGroup escapes here
    finally:
        stack.close()

    # The live match terminal is unaffected by the learning-lane failure.
    match_id = stack.identity.match_id
    assert final.winner_id == _LEARNER
    events = tuple(stack.ledger.read_all(match_id))
    event_types = [event.event_type for event in events]
    assert SOEventType.MATCH_ENDED in event_types
    assert SOEventType.MATCH_SCORED in event_types
    assert SOEventType.POLICY_PROMOTED not in event_types

    # Evidence survived the promotion failure (write ordered BEFORE the gate).
    evidence_files = sorted((tmp_path / "gate_evaluations" / "matches").glob("*.yaml"))
    assert len(evidence_files) == 1
    assert match_id in evidence_files[0].name

    # The failure is a typed, logged, contained learning-lane fact.
    assert len(handler.contained_failures) == 1
    failure = handler.contained_failures[0]
    assert failure.match_id == match_id
    assert failure.stage == "promotion_evaluation"
    assert failure.error_type == "DuelBatteryError"
    assert "injected mid-duel transport failure" in failure.message
    assert any(
        record.levelname == "ERROR" and match_id in record.getMessage() for record in caplog.records
    )

    # Bounded retry actually ran: 1 first attempt + 2 retries on the FIRST
    # duel, each against a fresh evidence target (exclusive-create storage).
    assert len(executor.calls) == 3
    assert [call.match_id for call in executor.calls] == [
        executor.calls[0].match_id,
        f"{executor.calls[0].match_id}.retry1",
        f"{executor.calls[0].match_id}.retry2",
    ]
    assert len({call.storage.duel for call in executor.calls}) == 3

    # The policy never advanced: an errored battery is a DECLINE, not a
    # promotion on incomplete evidence.
    assert coordinator.current_policy == genesis


@pytest.mark.integration
def test_transient_transport_failure_recovers_on_retry_and_still_promotes(
    tmp_path: Path,
) -> None:
    """Retry-then-success: one transient failure changes NOTHING downstream.

    The first duel attempt fails with a retryable transport error, the retry
    succeeds, the battery completes with the candidate winning every duel,
    and the gate promotes exactly as it would have without the flake.
    """

    executor = _ScriptedDuelExecutor(failures=1)
    stack, coordinator, handler = _assemble(tmp_path, executor)
    try:
        final = stack.runner.run()
    finally:
        stack.close()

    match_id = stack.identity.match_id
    assert final.winner_id == _LEARNER
    events = tuple(stack.ledger.read_all(match_id))
    promoted = [event for event in events if event.event_type is SOEventType.POLICY_PROMOTED]
    assert len(promoted) == 1
    assert handler.contained_failures == ()
    assert coordinator.current_policy.generation == 1
    assert coordinator.current_policy.parameters[_PARAMETER] == 61

    # Exactly one extra attempt: the failed first duel, retried once, then the
    # remaining three duels of the search+holdout batteries, one attempt each.
    assert len(executor.calls) == 5
    assert executor.calls[1].match_id == f"{executor.calls[0].match_id}.retry1"
    assert len({call.storage.duel for call in executor.calls}) == 5
