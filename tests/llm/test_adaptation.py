"""Tests for the cross-adaptation experiment (plan R3).

Proves, offline against scripted ``ProtocolLlmClient`` implementations:
  - the opponent trace block is assembled from ledger ``PILOT_DECISION_MADE``
    payloads (most-recent-N, token-capped), reusing the replay-trace arm;
  - ``OpponentAwareClient`` injects that trace into A's prompt without touching
    the shipped ``LLMPilot``;
  - a trace-sensitive client makes trace-ON produce *different* A actions;
  - the harness folds paired outcomes through the reused ``paired_comparison``
    (McNemar framing) and ``wilson_interval`` machinery consistently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.llm.adaptation import (
    OpponentAwareClient,
    build_opponent_trace_block,
    run_adaptation_experiment,
)
from steel_onslaught.llm.schemas import LlmResponse, LlmUsage
from steel_onslaught.match.runner import load_loadout

_CORR = uuid4()
_MECH_B = "mech.b.01"
_LOADOUT_A = Path("contracts_data/loadouts/example_aggressive_light.yaml")
_LOADOUT_B = Path("contracts_data/loadouts/example_predictive_heavy.yaml")


# ---------------------------------------------------------------------------
# Scripted clients.
# ---------------------------------------------------------------------------


class _TraceSensitiveClient:
    """Returns a DIFFERENT action when the opponent-adaptation marker is present.

    Blind (no trace) -> MOVE; adapted (trace injected) -> VENT. Both actions are
    always schema-available, so the pilot never falls to the REMAIN fallback and
    the action change is deterministic and observable.
    """

    def complete(self, system_prompt: str, user_prompt: str, **opts: Any) -> LlmResponse:
        if "OPPONENT ADAPTATION CONTEXT" in user_prompt:
            payload = {
                "action": "vent",
                "action_params": {},
                "confidence": 0.9,
                "rationale": "adapted: vent to counter the opponent's pattern",
            }
        else:
            payload = {
                "action": "move",
                "action_params": {"direction": "toward_enemy"},
                "confidence": 0.6,
                "rationale": "blind: advance on the enemy",
            }
        return LlmResponse(
            text=json.dumps(payload),
            usage=LlmUsage(prompt_tokens=10, completion_tokens=8),
            model="scripted",
            finish_reason="stop",
        )


class _CapturingClient:
    """Records the user prompts it is called with (for injection assertions)."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, system_prompt: str, user_prompt: str, **opts: Any) -> LlmResponse:
        self.prompts.append(user_prompt)
        return LlmResponse(
            text=json.dumps({"action": "remain", "action_params": {}, "confidence": 0.1}),
            model="capture",
            finish_reason="stop",
        )


def _decision_event(tick: int, mech_id: str, action: str, rationale: str) -> ModelSOEventEnvelope:
    return make_event(
        match_id="m.trace",
        tick=tick,
        sequence_in_tick=0,
        event_type=SOEventType.PILOT_DECISION_MADE,
        producer_node="node.test",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id="player.x"),
        payload={"action": action, "rationale": rationale},
        correlation_id=_CORR,
    )


# ---------------------------------------------------------------------------
# Trace assembly.
# ---------------------------------------------------------------------------


def test_trace_block_contains_opponent_decisions_and_rationale() -> None:
    events = [
        _decision_event(1, _MECH_B, "move", "close the distance"),
        _decision_event(1, "mech.a.01", "vent", "cool off"),  # A — must be excluded
        _decision_event(2, _MECH_B, "fire_weapon", "point-blank burst"),
    ]
    block = build_opponent_trace_block(events, opponent_mech_id=_MECH_B)
    assert "t1 move: close the distance" in block
    assert "t2 fire_weapon: point-blank burst" in block
    # A's own decision must not leak into B's trace.
    assert "cool off" not in block


def test_trace_block_empty_when_opponent_silent() -> None:
    events = [_decision_event(1, "mech.a.01", "move", "solo")]
    assert build_opponent_trace_block(events, opponent_mech_id=_MECH_B) == ""


def test_trace_block_keeps_most_recent_n() -> None:
    events = [_decision_event(t, _MECH_B, "move", f"tick {t}") for t in range(1, 11)]
    block = build_opponent_trace_block(events, opponent_mech_id=_MECH_B, most_recent_n=3)
    # Only the 3 most recent ticks (8, 9, 10) survive.
    assert "t10 move: tick 10" in block
    assert "t9 move: tick 9" in block
    assert "t8 move: tick 8" in block
    assert "t7 move" not in block


def test_trace_block_respects_char_budget() -> None:
    events = [_decision_event(t, _MECH_B, "move", "x" * 100) for t in range(1, 21)]
    block = build_opponent_trace_block(
        events, opponent_mech_id=_MECH_B, most_recent_n=20, max_chars=250
    )
    # The most-recent tick is always retained; older ones drop under the budget.
    assert "t20 move" in block
    assert "t1 move" not in block


# ---------------------------------------------------------------------------
# OpponentAwareClient injection.
# ---------------------------------------------------------------------------


def test_opponent_aware_client_injects_trace_into_user_prompt() -> None:
    capture = _CapturingClient()
    wrapped = OpponentAwareClient(base=capture, trace_block="t1 move: rush")
    wrapped.complete(system_prompt="sys", user_prompt="OBS", persona="berserker")
    assert len(capture.prompts) == 1
    sent = capture.prompts[0]
    assert "OBS" in sent
    assert "OPPONENT ADAPTATION CONTEXT" in sent
    assert "t1 move: rush" in sent


def test_opponent_aware_client_forwards_opts_and_response() -> None:
    capture = _CapturingClient()
    wrapped = OpponentAwareClient(base=capture, trace_block="trace")
    resp = wrapped.complete(system_prompt="s", user_prompt="u", temperature=0.3, json_mode=True)
    assert resp.model == "capture"


# ---------------------------------------------------------------------------
# End-to-end harness.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_experiment_runs_and_reports_consistent_counts(tmp_path: Path) -> None:
    result = run_adaptation_experiment(
        provider="scripted",
        persona_a="berserker",
        persona_b="sniper",
        n_matches=3,
        seed=100,
        loadout_a=load_loadout(_LOADOUT_A),
        loadout_b=load_loadout(_LOADOUT_B),
        base_client=_TraceSensitiveClient(),
        ledger_dir=tmp_path / "ledgers",
        max_ticks=20,
    )
    assert result.n_matches == 3
    assert len(result.pairs) == 3
    # McNemar buckets partition every pair.
    assert result.trace_helped + result.trace_hurt + result.concordant == 3
    assert 0.0 <= result.paired_p_value <= 1.0
    # Win counts are in range and CIs are ordered.
    assert 0 <= result.control_a_wins <= 3
    assert 0 <= result.adapted_a_wins <= 3
    assert result.control_win_rate_ci[0] <= result.control_win_rate_ci[1]
    assert result.adapted_win_rate_ci[0] <= result.adapted_win_rate_ci[1]


@pytest.mark.integration
def test_trace_on_changes_a_actions(tmp_path: Path) -> None:
    """The load-bearing claim: exposure to B's history changes A's play."""
    result = run_adaptation_experiment(
        provider="scripted",
        persona_a="berserker",
        persona_b="sniper",
        n_matches=2,
        seed=7,
        loadout_a=load_loadout(_LOADOUT_A),
        loadout_b=load_loadout(_LOADOUT_B),
        base_client=_TraceSensitiveClient(),
        ledger_dir=tmp_path / "ledgers",
        max_ticks=15,
    )
    # Every pair's A changed its actions (MOVE blind -> VENT adapted), and a
    # rationale diff was captured proving the with/without contrast.
    assert all(pair.actions_changed for pair in result.pairs)
    diffs = [d for pair in result.pairs for d in pair.sample_diffs]
    assert diffs, "expected at least one captured rationale diff"
    sample = diffs[0]
    assert sample.control_action == "move"
    assert sample.adapted_action == "vent"
    assert sample.control_rationale != sample.adapted_rationale


@pytest.mark.integration
def test_stub_client_baseline_produces_no_action_change(tmp_path: Path) -> None:
    """A trace-insensitive base client (the shipped stub) yields no A change.

    This is the honest negative: the harness only reports adaptation when the
    model actually conditions on the trace, not as an artifact of the wiring.
    """
    from steel_onslaught.llm.stub import StubLlmClient

    result = run_adaptation_experiment(
        provider="stub",
        persona_a="berserker",
        persona_b="sniper",
        n_matches=2,
        seed=42,
        loadout_a=load_loadout(_LOADOUT_A),
        loadout_b=load_loadout(_LOADOUT_B),
        base_client=StubLlmClient(),
        ledger_dir=tmp_path / "ledgers",
        max_ticks=15,
    )
    assert all(not pair.actions_changed for pair in result.pairs)
    # No discordant pairs → concordant covers all of them.
    assert result.concordant == 2


def test_n_matches_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="n_matches must be >= 1"):
        run_adaptation_experiment(
            provider="scripted",
            persona_a="berserker",
            persona_b="sniper",
            n_matches=0,
            seed=1,
            loadout_a=load_loadout(_LOADOUT_A),
            loadout_b=load_loadout(_LOADOUT_B),
            base_client=_TraceSensitiveClient(),
            ledger_dir=tmp_path / "ledgers",
        )
