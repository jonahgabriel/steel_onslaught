"""Tests for typed cross-adaptation orchestration over an injected duel port."""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.events.envelope import ModelSOEventEnvelope, ModelSOEventSubject, SOEventType
from steel_onslaught.llm.adaptation import (
    AdaptationResult,
    OpponentAwareClient,
    build_opponent_trace_block,
    run_adaptation_experiment,
)
from steel_onslaught.llm.schemas import (
    LlmResponse,
    LlmUsage,
    ModelSOLlmCompletionRequest,
    ModelSOLlmPilotSelection,
)
from steel_onslaught.match.composition import load_loadout
from steel_onslaught.match.duel import DuelResult, ModelSOEvaluationStorageKey
from steel_onslaught.match.state import ModelSOMatchState, SOMatchEndReason, SOMatchStatus
from tests.runtime import runtime_dependencies

_MECH_B = "mech.b.01"
_LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")


class _CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelSOLlmCompletionRequest] = []

    def complete(self, request: ModelSOLlmCompletionRequest) -> LlmResponse:
        self.requests.append(request)
        return LlmResponse(
            text='{"action":"remain","action_params":{},"confidence":0.1}',
            usage=LlmUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.0),
            model="capture",
            finish_reason="stop",
        )


def _request() -> ModelSOLlmCompletionRequest:
    return ModelSOLlmCompletionRequest(
        system_prompt="system",
        user_prompt="OBS",
        persona="berserker",
        temperature=0.3,
        json_mode=True,
        evidence_context=None,
    )


def _decision_event(tick: int, mech_id: str, action: str, rationale: str) -> ModelSOEventEnvelope:
    runtime = runtime_dependencies()
    identities = runtime.event_factory.identities
    return runtime.event_factory.make(
        match_id="m.trace",
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.PILOT_DECISION_MADE,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id="player.x"),
        payload={"action": action, "rationale": rationale},
        correlation_id=identities.new_correlation_id(),
    )


@pytest.mark.unit
def test_trace_block_contains_only_opponent_decisions_and_rationales() -> None:
    events = [
        _decision_event(1, _MECH_B, "move", "close the distance"),
        _decision_event(1, "mech.a.01", "vent", "cool off"),
        _decision_event(2, _MECH_B, "fire_weapon", "point-blank burst"),
    ]
    block = build_opponent_trace_block(events, opponent_mech_id=_MECH_B)
    assert "t1 move: close the distance" in block
    assert "t2 fire_weapon: point-blank burst" in block
    assert "cool off" not in block


@pytest.mark.unit
def test_trace_block_empty_when_opponent_silent() -> None:
    events = [_decision_event(1, "mech.a.01", "move", "solo")]
    assert build_opponent_trace_block(events, opponent_mech_id=_MECH_B) == ""


@pytest.mark.unit
def test_trace_block_keeps_most_recent_n() -> None:
    events = [_decision_event(tick, _MECH_B, "move", f"tick {tick}") for tick in range(1, 11)]
    block = build_opponent_trace_block(events, opponent_mech_id=_MECH_B, most_recent_n=3)
    assert "t10 move: tick 10" in block
    assert "t9 move: tick 9" in block
    assert "t8 move: tick 8" in block
    assert "t7 move" not in block


@pytest.mark.unit
def test_trace_block_respects_char_budget() -> None:
    events = [_decision_event(tick, _MECH_B, "move", "x" * 100) for tick in range(1, 21)]
    block = build_opponent_trace_block(
        events,
        opponent_mech_id=_MECH_B,
        most_recent_n=20,
        max_chars=250,
    )
    assert "t20 move" in block
    assert "t1 move" not in block


@pytest.mark.unit
def test_opponent_aware_client_injects_trace_and_preserves_typed_request() -> None:
    capture = _CapturingClient()
    response = OpponentAwareClient(base=capture, trace_block="t1 move: rush").complete(_request())
    assert response.model == "capture"
    assert len(capture.requests) == 1
    sent = capture.requests[0]
    assert sent.system_prompt == "system"
    assert sent.temperature == 0.3
    assert "OBS" in sent.user_prompt
    assert "OPPONENT ADAPTATION CONTEXT" in sent.user_prompt
    assert "t1 move: rush" in sent.user_prompt


class _PilotDuelRecorder:
    """Returns canonical event/state evidence based only on typed selections."""

    def __init__(self, *, change_actions: bool = True) -> None:
        self.change_actions = change_actions
        self.calls: list[
            tuple[ModelSOLlmPilotSelection, ModelSOLlmPilotSelection, ModelSOEvaluationStorageKey]
        ] = []

    def __call__(
        self,
        *,
        loadout_a: object,
        loadout_b: object,
        pilot_a: ModelSOLlmPilotSelection,
        pilot_b: ModelSOLlmPilotSelection,
        seed: int,
        max_ticks: int,
        storage: ModelSOEvaluationStorageKey,
        match_id: str,
        side_a: str,
        side_b: str,
    ) -> DuelResult:
        self.calls.append((pilot_a, pilot_b, storage))
        adapted = pilot_a.opponent_trace is not None
        action = "vent" if adapted and self.change_actions else "move"
        rationale = "adapted rationale" if adapted and self.change_actions else "control rationale"
        events = (
            _decision_event(1, "mech.a.01", action, rationale),
            _decision_event(1, "mech.b.01", "fire_weapon", "opponent pattern"),
        )
        return DuelResult(
            final_state=ModelSOMatchState(
                match_id=match_id,
                tick=1,
                status=SOMatchStatus.ENDED,
                seed=seed,
                max_ticks=max_ticks,
                winner_id="player.a" if adapted else None,
                end_reason=(
                    SOMatchEndReason.LAST_MECH_STANDING
                    if adapted
                    else SOMatchEndReason.DRAW_MAX_TICKS
                ),
            ),
            events=events,
        )


def _run(executor: _PilotDuelRecorder, *, n_matches: int = 3) -> AdaptationResult:
    return run_adaptation_experiment(
        provider="scripted",
        persona_a="berserker",
        persona_b="sniper",
        n_matches=n_matches,
        seed=100,
        loadout_a=load_loadout(_LOADOUT_A),
        loadout_b=load_loadout(_LOADOUT_B),
        duel_executor=executor,
        max_ticks=20,
        most_recent_n=12,
        max_trace_chars=1200,
        max_sample_diffs=3,
        match_id_prefix="adapt",
    )


@pytest.mark.integration
def test_experiment_runs_paired_typed_selections_and_reports_consistent_counts() -> None:
    executor = _PilotDuelRecorder()
    result = _run(executor)
    assert result.n_matches == 3
    assert len(result.pairs) == 3
    assert len(executor.calls) == 6
    assert all(executor.calls[index][0].opponent_trace is None for index in (0, 2, 4))
    assert all(executor.calls[index][0].opponent_trace for index in (1, 3, 5))
    assert {call[2].duel for call in executor.calls} == {"control", "adapted"}
    assert result.trace_helped + result.trace_hurt + result.concordant == 3
    assert 0.0 <= result.paired_p_value <= 1.0
    assert result.control_win_rate_ci[0] <= result.control_win_rate_ci[1]
    assert result.adapted_win_rate_ci[0] <= result.adapted_win_rate_ci[1]


@pytest.mark.integration
def test_trace_on_changes_actions_and_captures_rationale_diff() -> None:
    result = _run(_PilotDuelRecorder(), n_matches=2)
    assert all(pair.actions_changed for pair in result.pairs)
    sample = result.pairs[0].sample_diffs[0]
    assert sample.control_action == "move"
    assert sample.adapted_action == "vent"
    assert sample.control_rationale != sample.adapted_rationale


@pytest.mark.integration
def test_trace_insensitive_executor_produces_no_action_change() -> None:
    result = _run(_PilotDuelRecorder(change_actions=False), n_matches=2)
    assert all(not pair.actions_changed for pair in result.pairs)
    assert result.concordant == 0  # outcome still changes in this scripted state seam


@pytest.mark.unit
def test_n_matches_must_be_positive_without_invoking_executor() -> None:
    executor = _PilotDuelRecorder()
    with pytest.raises(ValueError, match="n_matches must be >= 1"):
        _run(executor, n_matches=0)
    assert executor.calls == []
