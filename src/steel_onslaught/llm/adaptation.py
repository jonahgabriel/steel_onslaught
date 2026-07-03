"""Cross-adaptation experiment (plan R3, HANDOFF §3).

The question this measures: **does showing model A its opponent's decision
history change A's play?**

The mechanism is pure composition — none of the shipped LLM-pilot code is
edited. An adaptive variant is built by *wrapping* the ``ProtocolLlmClient``
seam (``OpponentAwareClient``) so that the opponent's per-tick decision trace
from a prior match ledger is injected into the pilot's prompt. The unwrapped
pilot (trace-OFF) is the control; the wrapped pilot (trace-ON) is the adapted
arm. Both arms run the *same* seeds, so the comparison is paired.

Trace assembly reuses the existing replay-trace arm assembler
(``llm/context_arms.py::assemble_arm_context`` with ``ContextArm.LLM_REPLAY_TRACE``)
rather than duplicating a block formatter — the per-tick ``PILOT_DECISION_MADE``
payloads (action + rationale) are rendered compactly, most-recent-N, token-capped,
and handed to that assembler. (The assembler's tuner-oriented base header is
included verbatim as part of that reuse; an LLM ignores the empty parameter
lines, and re-implementing the block wrapping is exactly the duplication the
plan forbids.)

Statistics reuse ``learning/stats.py`` unchanged: the paired per-seed outcomes
are folded through ``paired_comparison`` in a McNemar framing (a discordant pair
where the trace flipped a loss into a win counts for the adapted arm; the reverse
counts against it), and each arm's raw win rate carries a ``wilson_interval``.
No new statistics framework is introduced.

**LLM matches are nondeterministic** (the model samples). This harness therefore
measures a *distribution shift* in A's win rate under trace exposure — not a
deterministic property. Offline, against a scripted ``ProtocolLlmClient``, the
whole pipeline is exercised deterministically (a trace-sensitive stub makes
trace-ON produce different actions than trace-OFF).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.learning.stats import paired_comparison, wilson_interval
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.llm.context_arms import ContextArm, assemble_arm_context
from steel_onslaught.llm.pilot import LLMPilot
from steel_onslaught.llm.schemas import LlmResponse, ProtocolLlmClient
from steel_onslaught.match.runner import MatchRunner
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.schemas import PilotProtocol

# Deterministic identities the runner assigns (match/runner.py::_build_mech):
# side "a"/"b" → mech.{side}.01 and player.{side}.
_MECH_A = "mech.a.01"
_MECH_B = "mech.b.01"
_PLAYER_A = "player.a"

# Defaults for trace compaction — most-recent-N decisions, hard char budget.
_DEFAULT_MOST_RECENT_N = 12
_DEFAULT_MAX_TRACE_CHARS = 1200

# Cap on rationale-diff samples retained per pair (qualitative output only).
_DEFAULT_SAMPLE_DIFFS = 3


# ---------------------------------------------------------------------------
# The adaptive variant: a client wrapper that injects the opponent's trace.
# ---------------------------------------------------------------------------


class OpponentAwareClient:
    """Wraps a ``ProtocolLlmClient`` and injects an opponent decision trace.

    This is the *entire* adaptive-pilot mechanism: the shipped ``LLMPilot`` is
    reused verbatim, constructed with this wrapping client instead of the base
    one. On every ``complete`` the wrapper appends the (pre-assembled) opponent
    trace block to the user prompt before delegating, so A's prompt carries B's
    history. The wrapper is transparent to opts and preserves the response.
    """

    def __init__(self, *, base: ProtocolLlmClient, trace_block: str) -> None:
        self._base = base
        self._trace_block = trace_block

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **opts: Any,
    ) -> LlmResponse:
        augmented = (
            f"{user_prompt}\n\n"
            "--- OPPONENT ADAPTATION CONTEXT ---\n"
            "Your opponent's recent decision history (adapt to exploit it):\n"
            f"{self._trace_block}"
        )
        return self._base.complete(system_prompt=system_prompt, user_prompt=augmented, **opts)


# ---------------------------------------------------------------------------
# Trace assembly (reuses the replay-trace arm assembler).
# ---------------------------------------------------------------------------


def _render_decision_lines(
    events: Iterable[ModelSOEventEnvelope],
    *,
    opponent_mech_id: str,
    most_recent_n: int,
    max_chars: int,
) -> str:
    """Compact the opponent's ``PILOT_DECISION_MADE`` payloads into trace text.

    Filters to the opponent's decisions, keeps the most-recent-N, and renders
    ``t{tick} {action}: {rationale}`` lines. Enforces a char budget by dropping
    oldest lines first (most-recent decisions are the most informative).
    """
    decisions: list[tuple[int, str, str | None]] = []
    for env in events:
        if env.event_type is not SOEventType.PILOT_DECISION_MADE:
            continue
        if env.subject.mech_id != opponent_mech_id:
            continue
        action = str(env.payload.get("action", "?"))
        rationale_raw = env.payload.get("rationale")
        rationale = str(rationale_raw) if rationale_raw is not None else None
        decisions.append((env.tick, action, rationale))

    recent = decisions[-most_recent_n:] if most_recent_n > 0 else []

    # Build from newest backward under the char budget, then restore order.
    kept: list[str] = []
    total = 0
    for tick, action, rationale in reversed(recent):
        line = f"t{tick} {action}" + (f": {rationale}" if rationale else "")
        if total + len(line) + 1 > max_chars and kept:
            break
        kept.append(line)
        total += len(line) + 1
    kept.reverse()
    return "\n".join(kept)


def build_opponent_trace_block(
    events: Iterable[ModelSOEventEnvelope],
    *,
    opponent_mech_id: str = _MECH_B,
    most_recent_n: int = _DEFAULT_MOST_RECENT_N,
    max_chars: int = _DEFAULT_MAX_TRACE_CHARS,
) -> str:
    """Assemble an opponent decision trace for prompt injection.

    Reuses ``assemble_arm_context(ContextArm.LLM_REPLAY_TRACE, ...)`` to wrap the
    rendered per-tick lines rather than re-implementing the block formatting.
    Returns an empty string when the opponent made no recorded decisions (the
    caller then runs the "adapted" arm with an empty trace — still a valid,
    honestly-empty control-vs-control comparison for that pair).
    """
    trace_text = _render_decision_lines(
        events,
        opponent_mech_id=opponent_mech_id,
        most_recent_n=most_recent_n,
        max_chars=max_chars,
    )
    if not trace_text:
        return ""
    ctx = assemble_arm_context(
        ContextArm.LLM_REPLAY_TRACE,
        archetype="llm",
        parent_params={},
        bounds={},
        replay_traces=[trace_text],
    )
    return ctx.prompt_addendum


# ---------------------------------------------------------------------------
# Result models.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RationaleDiff:
    """One tick where A's action or rationale differed with/without the trace."""

    tick: int
    control_action: str
    adapted_action: str
    control_rationale: str | None
    adapted_rationale: str | None


@dataclass(frozen=True)
class PairOutcome:
    """One seeded control-vs-adapted pair."""

    seed: int
    control_winner: str | None
    adapted_winner: str | None
    control_a_won: bool
    adapted_a_won: bool
    actions_changed: bool
    sample_diffs: tuple[RationaleDiff, ...] = ()


@dataclass(frozen=True)
class AdaptationResult:
    """Aggregate outcome of a cross-adaptation experiment."""

    provider: str
    persona_a: str
    persona_b: str
    n_matches: int
    control_a_wins: int
    adapted_a_wins: int
    control_draws: int
    adapted_draws: int
    control_win_rate: float
    adapted_win_rate: float
    control_win_rate_ci: tuple[float, float]
    adapted_win_rate_ci: tuple[float, float]
    # McNemar-framed paired comparison (candidate = adapted, parent = control).
    paired_p_value: float
    trace_helped: int  # discordant pairs where trace flipped loss -> win
    trace_hurt: int  # discordant pairs where trace flipped win -> loss
    concordant: int  # pairs with identical A-win outcome
    pairs: tuple[PairOutcome, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Match execution + decision extraction.
# ---------------------------------------------------------------------------


def _run_one_match(
    *,
    match_id: str,
    seed: int,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    pilot_a: PilotProtocol,
    pilot_b: PilotProtocol,
    max_ticks: int,
    ledger: SQLiteLedger,
) -> ModelSOMatchState:
    """Drive one match with injected pilots, appending every event to ``ledger``."""
    bus = InProcessEventBus()
    bus.subscribe(ledger.append)
    runner = MatchRunner(
        match_id=match_id,
        seed=seed,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        bus=bus,
        max_ticks=max_ticks,
        pilots_override={_MECH_A: pilot_a, _MECH_B: pilot_b},
    )
    return runner.run()


def _a_decisions(
    events: Iterable[ModelSOEventEnvelope],
) -> list[tuple[int, str, str | None]]:
    """Extract A's ``(tick, action, rationale)`` decisions in ledger order."""
    out: list[tuple[int, str, str | None]] = []
    for env in events:
        if env.event_type is not SOEventType.PILOT_DECISION_MADE:
            continue
        if env.subject.mech_id != _MECH_A:
            continue
        rationale_raw = env.payload.get("rationale")
        out.append(
            (
                env.tick,
                str(env.payload.get("action", "?")),
                str(rationale_raw) if rationale_raw is not None else None,
            )
        )
    return out


def _diff_decisions(
    control: list[tuple[int, str, str | None]],
    adapted: list[tuple[int, str, str | None]],
    *,
    max_samples: int,
) -> tuple[bool, tuple[RationaleDiff, ...]]:
    """Compare A's decision streams tick-by-tick; return (changed?, samples)."""
    control_by_tick = {tick: (action, rationale) for tick, action, rationale in control}
    changed = False
    samples: list[RationaleDiff] = []
    for tick, adapted_action, adapted_rationale in adapted:
        if tick not in control_by_tick:
            continue
        control_action, control_rationale = control_by_tick[tick]
        if control_action == adapted_action and control_rationale == adapted_rationale:
            continue
        changed = True
        if len(samples) < max_samples:
            samples.append(
                RationaleDiff(
                    tick=tick,
                    control_action=control_action,
                    adapted_action=adapted_action,
                    control_rationale=control_rationale,
                    adapted_rationale=adapted_rationale,
                )
            )
    return changed, tuple(samples)


# ---------------------------------------------------------------------------
# The A/B harness.
# ---------------------------------------------------------------------------


def run_adaptation_experiment(
    *,
    provider: str,
    persona_a: str,
    persona_b: str,
    n_matches: int,
    seed: int,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    base_client: ProtocolLlmClient,
    ledger_dir: Path,
    max_ticks: int = 60,
    most_recent_n: int = _DEFAULT_MOST_RECENT_N,
    max_trace_chars: int = _DEFAULT_MAX_TRACE_CHARS,
    max_sample_diffs: int = _DEFAULT_SAMPLE_DIFFS,
    match_id_prefix: str = "adapt",
) -> AdaptationResult:
    """Run N seeded control/adapted match pairs and summarise the win-rate shift.

    For pair ``i`` (seed ``seed + i``):
      1. **Control** — A(persona_a) vs B(persona_b), both on ``base_client``.
      2. Assemble B's decision trace from the control ledger.
      3. **Adapted** — same seed; A on ``OpponentAwareClient(base_client, trace)``
         (A now sees B's history), B unchanged on ``base_client``.

    Nondeterminism note: with a real sampling model, control and adapted are two
    *different* stochastic runs even at the same seed, so this measures a
    distribution shift, not a deterministic effect. Offline against a scripted
    client the pipeline is deterministic.
    """
    if n_matches < 1:
        raise ValueError(f"n_matches must be >= 1; got {n_matches}")

    ledger_dir.mkdir(parents=True, exist_ok=True)

    pairs: list[PairOutcome] = []
    seed_outcomes: list[ModelSOSeedOutcome] = []

    for i in range(n_matches):
        pair_seed = seed + i
        ledger_path = ledger_dir / f"{match_id_prefix}.seed{pair_seed}.sqlite"
        ledger = SQLiteLedger(ledger_path)
        control_id = f"{match_id_prefix}.{pair_seed}.control"
        adapted_id = f"{match_id_prefix}.{pair_seed}.adapted"

        # 1. Control run (trace-OFF).
        control_final = _run_one_match(
            match_id=control_id,
            seed=pair_seed,
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            pilot_a=LLMPilot.from_persona_id(client=base_client, persona_id=persona_a),
            pilot_b=LLMPilot.from_persona_id(client=base_client, persona_id=persona_b),
            max_ticks=max_ticks,
            ledger=ledger,
        )
        control_events = list(ledger.read_all(control_id))

        # 2. Assemble the opponent (B) trace from the control ledger.
        trace_block = build_opponent_trace_block(
            control_events,
            opponent_mech_id=_MECH_B,
            most_recent_n=most_recent_n,
            max_chars=max_trace_chars,
        )
        adapted_client: ProtocolLlmClient = OpponentAwareClient(
            base=base_client, trace_block=trace_block
        )

        # 3. Adapted run (trace-ON) — same seed, A wrapped.
        adapted_final = _run_one_match(
            match_id=adapted_id,
            seed=pair_seed,
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            pilot_a=LLMPilot.from_persona_id(client=adapted_client, persona_id=persona_a),
            pilot_b=LLMPilot.from_persona_id(client=base_client, persona_id=persona_b),
            max_ticks=max_ticks,
            ledger=ledger,
        )
        adapted_events = list(ledger.read_all(adapted_id))

        control_a_won = control_final.winner_id == _PLAYER_A
        adapted_a_won = adapted_final.winner_id == _PLAYER_A

        actions_changed, samples = _diff_decisions(
            _a_decisions(control_events),
            _a_decisions(adapted_events),
            max_samples=max_sample_diffs,
        )

        pairs.append(
            PairOutcome(
                seed=pair_seed,
                control_winner=control_final.winner_id,
                adapted_winner=adapted_final.winner_id,
                control_a_won=control_a_won,
                adapted_a_won=adapted_a_won,
                actions_changed=actions_changed,
                sample_diffs=samples,
            )
        )

        # McNemar framing: candidate = adapted arm, parent = control arm.
        if adapted_a_won and not control_a_won:
            winner = SOSeedWinner.CANDIDATE  # trace flipped a loss into a win
        elif control_a_won and not adapted_a_won:
            winner = SOSeedWinner.PARENT  # trace flipped a win into a loss
        else:
            winner = SOSeedWinner.DRAW  # concordant — no change to A's outcome
        seed_outcomes.append(
            ModelSOSeedOutcome(
                seed=pair_seed,
                winner=winner,
                candidate_overloads=0,
                parent_overloads=0,
            )
        )

    comparison = paired_comparison(seed_outcomes)

    control_a_wins = sum(1 for p in pairs if p.control_a_won)
    adapted_a_wins = sum(1 for p in pairs if p.adapted_a_won)
    control_draws = sum(1 for p in pairs if p.control_winner is None)
    adapted_draws = sum(1 for p in pairs if p.adapted_winner is None)

    return AdaptationResult(
        provider=provider,
        persona_a=persona_a,
        persona_b=persona_b,
        n_matches=n_matches,
        control_a_wins=control_a_wins,
        adapted_a_wins=adapted_a_wins,
        control_draws=control_draws,
        adapted_draws=adapted_draws,
        control_win_rate=control_a_wins / n_matches,
        adapted_win_rate=adapted_a_wins / n_matches,
        control_win_rate_ci=wilson_interval(control_a_wins, n_matches),
        adapted_win_rate_ci=wilson_interval(adapted_a_wins, n_matches),
        paired_p_value=comparison.p_value,
        trace_helped=comparison.candidate_wins,
        trace_hurt=comparison.parent_wins,
        concordant=comparison.draws,
        pairs=tuple(pairs),
    )


__all__ = [
    "AdaptationResult",
    "OpponentAwareClient",
    "PairOutcome",
    "RationaleDiff",
    "build_opponent_trace_block",
    "run_adaptation_experiment",
]
