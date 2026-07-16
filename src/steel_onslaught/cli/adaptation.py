"""``so run-adaptation`` — the cross-adaptation A/B experiment (plan R3).

Runs N seeded match PAIRS: a trace-OFF control (A and B play blind) and a
trace-ON adapted run (A additionally sees B's decision history from the control
match, same seed). Emits a win-rate table (adapted vs control), draw counts, a
McNemar paired significance test, and a qualitative sample of A's rationale
diffs (same tick, with/without the trace).

Nondeterminism: with a real sampling model, control and adapted are two distinct
stochastic runs even at the same seed. This command therefore measures a
**distribution shift** in A's win rate under opponent-trace exposure — it is not
a deterministic property. Use ``--provider stub`` for an offline, deterministic
smoke run.
"""

from __future__ import annotations

from pathlib import Path

import click

from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.llm.adaptation import AdaptationResult, run_adaptation_experiment
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_loadout,
)

_LOADOUT_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)


def _render(result: AdaptationResult) -> str:
    """Format the experiment result as a human-readable report."""
    lines: list[str] = []
    lines.append(
        f"cross-adaptation: {result.persona_a} (A) vs {result.persona_b} (B) "
        f"via {result.provider!r}, n={result.n_matches} pairs"
    )
    lines.append("")
    lines.append("A win-rate (does seeing B's history change A's play?)")
    lines.append(f"  {'arm':<10} {'A-wins':>7} {'draws':>6} {'win-rate':>9}  95% CI")
    c_lo, c_hi = result.control_win_rate_ci
    a_lo, a_hi = result.adapted_win_rate_ci
    lines.append(
        f"  {'control':<10} {result.control_a_wins:>7} {result.control_draws:>6} "
        f"{result.control_win_rate:>9.3f}  [{c_lo:.3f}, {c_hi:.3f}]"
    )
    lines.append(
        f"  {'adapted':<10} {result.adapted_a_wins:>7} {result.adapted_draws:>6} "
        f"{result.adapted_win_rate:>9.3f}  [{a_lo:.3f}, {a_hi:.3f}]"
    )
    lines.append("")
    lines.append("paired (McNemar) shift under trace exposure:")
    lines.append(
        f"  trace-helped={result.trace_helped}  trace-hurt={result.trace_hurt}  "
        f"concordant={result.concordant}  p={result.paired_p_value:.4f}"
    )
    lines.append(
        "  (measures a distribution shift, not a deterministic property; "
        "LLM play is nondeterministic)"
    )
    lines.append("")
    lines.append("rationale diffs (same tick, A with/without the opponent trace):")
    shown = 0
    for pair in result.pairs:
        for diff in pair.sample_diffs:
            lines.append(
                f"  seed {pair.seed} t{diff.tick}: {diff.control_action} -> {diff.adapted_action}"
            )
            if diff.control_rationale or diff.adapted_rationale:
                lines.append(f"      off: {diff.control_rationale}")
                lines.append(f"      on : {diff.adapted_rationale}")
            shown += 1
            if shown >= 6:
                break
        if shown >= 6:
            break
    if shown == 0:
        lines.append("  (none — A's actions were identical with and without the trace)")
    return "\n".join(lines)


@click.command(name="run-adaptation")
@click.option(
    "--overlay",
    "overlay_path",
    type=_LOADOUT_PATH,
    required=True,
)
@click.option(
    "--provider",
    required=True,
    help="Provider id declared by the application overlay.",
)
@click.option("--persona-a", required=True, help="Side-A persona id (the adapting pilot).")
@click.option("--persona-b", required=True, help="Side-B persona id (the observed opponent).")
@click.option(
    "--n-matches",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Number of seeded control/adapted match pairs.",
)
@click.option(
    "--seed",
    type=click.IntRange(min=0),
    required=True,
    help="Base seed; pair i uses seed+i.",
)
@click.option(
    "--loadout-a",
    "loadout_a_path",
    type=_LOADOUT_PATH,
    required=True,
    help="Side-A loadout contract (the persona overrides the pilot).",
)
@click.option(
    "--loadout-b",
    "loadout_b_path",
    type=_LOADOUT_PATH,
    required=True,
    help="Side-B loadout contract (the persona overrides the pilot).",
)
@click.option("--max-ticks", type=click.IntRange(min=1), required=True)
def adaptation_command(
    overlay_path: Path,
    provider: str,
    persona_a: str,
    persona_b: str,
    n_matches: int,
    seed: int,
    loadout_a_path: Path,
    loadout_b_path: Path,
    max_ticks: int,
) -> None:
    """Measure whether showing pilot A its opponent's decision history changes A's play."""
    overlay = load_application_overlay(overlay_path)
    with CliApplicationFactory.packaged().adaptation(overlay) as dependencies:
        result = run_adaptation_experiment(
            provider=provider,
            persona_a=persona_a,
            persona_b=persona_b,
            n_matches=n_matches,
            seed=seed,
            loadout_a=load_loadout(loadout_a_path),
            loadout_b=load_loadout(loadout_b_path),
            duel_executor=dependencies.duel_executor,
            max_ticks=max_ticks,
            most_recent_n=12,
            max_trace_chars=1200,
            max_sample_diffs=3,
            match_id_prefix="adapt",
        )
    click.echo(_render(result))
    click.echo(f"evidence: {overlay.evaluation_storage.root}", err=True)


__all__ = ["adaptation_command"]
