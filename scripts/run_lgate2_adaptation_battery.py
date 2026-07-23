"""L-GATE-2 before/after adaptation battery on live keyless Qwen.

Answers the gate's empirical question (design 2026-07-22 §5, speculation
register item 3): does a promotion change a later live decision, auditably?

Two modes:

``--mode battery`` (default) — three phases over ONE durable battery lane
(shared event ledger + lineage store, so the promotion chain carries across
phases exactly as it does across production processes), using the
``win_damage_differential_v1`` evaluator:

1. ``baseline``  — live-learning ON, evaluator capped at ``max_value == genesis``
   so promotion is impossible; every match flies the generation-0 policy
   (aggression 1.0) WITH its guidance block.  N matches.
2. ``promote``   — cap lifted (``max_value=3.0``); matches run until the first
   ``POLICY_PROMOTED`` lands on the ledger (bounded attempts).
3. ``post``      — cap re-pinned at the promoted value (genesis + step) so
   the chain freezes at generation 1; every match flies the promoted policy.
   N matches.

``--seat`` selects the learning seat (blue sniper / red berserker) and
``--step`` the perturbation size, so effect-size reruns can vary exactly one
knob per comparison.

``--mode live-fire`` — first live run of the ``selection_outcome_v1``
evaluator lane: real evidence-directed candidate proposal gated through the
offline duel machinery (``DuelEvaluator`` over the composition-built duel
executor), on the same live overlay.  Runs matches until the duel gate
promotes once (or the match budget is exhausted — a legitimate decline is a
reported finding), then flies ONE confirm match proving the promoted policy
governs the next admission.  This is a spine proof for the real judgment
path, not an effect-size battery.

The measured observable is the learning seat's card-selection behavior using
the #117 instruments: per-category keep-rates (planned/dealt) and category
selection distribution, read from the canonical event ledger.  The audit
chain (MATCH_STARTED policy provenance -> POLICY_PROMOTED -> lineage record
digest -> per-match replay validity) is verified inline.  An inconclusive
shift is a reported finding, not a failure to hide.

Run (battery defaults: 10+10, ~35 s/match on the AI-PC endpoint):

    uv run python scripts/run_lgate2_adaptation_battery.py --n 10
    uv run python scripts/run_lgate2_adaptation_battery.py \
        --mode battery --seat red --step 0.5 --n 30
    uv run python scripts/run_lgate2_adaptation_battery.py \
        --mode live-fire --seat red --lf-matches 8
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOLiveLearningBinding,
    ModelSOSelectionOutcomeThresholds,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOPolicyPromotedPayload,
)
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.match.composition import assemble_match_live, load_application_overlay

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERLAY = _REPO_ROOT / "contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/llm_qwen35_berserker.yaml"
_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad.yaml"

# seat -> (player_id, mech_id)
_SEATS = {
    "blue": ("player.blue", "mech.blue.01"),
    "red": ("player.red", "mech.red.01"),
}
_ARCHETYPE = "aggressive"
_GENESIS = {"aggression": 1.0}
_MAX_PROMOTE_ATTEMPTS = 5

# selection_outcome_v1 (live-fire) genesis: the complete aggressive
# spec-parameter set, values from contracts_data/pilots/template_aggressive.yaml
# (the archetype's canonical template) — the duel gate materializes real pilot
# specs, so a partial parameter set fails closed at composition.
_LIVE_FIRE_GENESIS: dict[str, int | float | str] = {
    "vent_at_heat_margin": 5,
    "idle_vent_heat_threshold": 90,
    "mode_switch_pressure_floor": 12,
    "mode_switch_heat_ceiling": 80,
    "weapon_preference": "highest_damage",
}


def _base_overlay_updates(base: ModelSOApplicationOverlay, state_root: Path) -> dict[str, Any]:
    """Repoint every durable surface of the overlay into the battery lane."""
    return {
        "event_ledger": base.event_ledger.model_copy(
            update={"path": state_root / "events.sqlite3"}
        ),
        "leaderboard": base.leaderboard.model_copy(
            update={"path": state_root / "leaderboard.sqlite3"}
        ),
        "learning_artifacts": base.learning_artifacts.model_copy(
            update={
                "evaluation_root": state_root / "evaluations",
                "lineage_root": state_root / "lineage",
                "experiment_root": state_root / "experiments",
            }
        ),
        "evaluation_storage": base.evaluation_storage.model_copy(
            update={"root": state_root / "evaluation_storage"}
        ),
    }


def _lane_overlay(
    state_root: Path, *, max_value: float, learning_player: str, step: float
) -> ModelSOApplicationOverlay:
    base = load_application_overlay(_OVERLAY)
    updates = _base_overlay_updates(base, state_root)
    updates["live_learning"] = ModelSOLiveLearningBinding(
        kind="win_damage_differential_v1",
        archetype=_ARCHETYPE,
        learning_player_id=learning_player,
        genesis_parameters=dict(_GENESIS),
        parameter="aggression",
        step=step,
        max_value=max_value,
    )
    return base.model_copy(update=updates)


def _live_fire_overlay(
    state_root: Path, *, learning_player: str, args: argparse.Namespace
) -> ModelSOApplicationOverlay:
    base = load_application_overlay(_OVERLAY)
    updates = _base_overlay_updates(base, state_root)
    updates["live_learning"] = ModelSOLiveLearningBinding(
        kind="selection_outcome_v1",
        archetype=_ARCHETYPE,
        learning_player_id=learning_player,
        genesis_parameters=dict(_LIVE_FIRE_GENESIS),
        parameter=args.lf_parameter,
        base_loadout_path=_RED_LOADOUT,
        duel_max_ticks=args.lf_duel_max_ticks,
        n_search_seeds=args.lf_search_seeds,
        n_holdout_seeds=args.lf_holdout_seeds,
        step_multiplier=1,
        thresholds=ModelSOSelectionOutcomeThresholds(
            p_value_max=args.lf_p_value_max,
            min_decisive_n=args.lf_min_decisive_n,
            max_draw_rate=args.lf_max_draw_rate,
        ),
    )
    return base.model_copy(update=updates)


def _category(card_id: str, catalog: Any) -> str:
    return str(catalog.require(card_id).category.value)


def _measure_match(
    overlay: ModelSOApplicationOverlay,
    *,
    seed: int,
    phase: str,
    learning_player: str,
    learning_seat: str,
    learning_mech: str,
) -> dict[str, Any]:
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=_RED_LOADOUT,
        blue_loadout_path=_BLUE_LOADOUT,
        seed=seed,
        max_ticks=None,
        secret_resolver=NoSecretResolver(),  # keyless provider; composition owns the transport
    )
    try:
        final = stack.runner.run()
        events: tuple[ModelSOEventEnvelope, ...] = tuple(
            stack.ledger.read_all(stack.identity.match_id)
        )
    finally:
        stack.close()

    snapshot = stack.card_runtime_snapshot
    assert snapshot is not None
    catalog = snapshot.card_catalog

    dealt: Counter[str] = Counter()
    planned: Counter[str] = Counter()
    started_provenance: dict[str, Any] | None = None
    scored: ModelSOMatchScoredPayload | None = None
    promoted: dict[str, Any] | None = None
    failed_completions = 0
    for event in events:
        if event.event_type is SOEventType.MATCH_STARTED:
            payload = ModelSOMatchStartedPayload.model_validate(event.payload)
            assert payload.policy_provenance is not None, "learning lane must record provenance"
            (seat_entry,) = payload.policy_provenance
            assert seat_entry.player_id == learning_player
            started_provenance = seat_entry.model_dump(mode="json")
        elif event.event_type is SOEventType.HAND_DEALT and event.subject.mech_id == learning_mech:
            raw_cards = event.payload["card_ids"]
            assert isinstance(raw_cards, (list, tuple))
            for card_id in raw_cards:
                dealt[_category(str(card_id), catalog)] += 1
        elif (
            event.event_type is SOEventType.PLAN_COMMITTED
            and event.subject.mech_id == learning_mech
        ):
            raw_registers = event.payload["registers"]
            assert isinstance(raw_registers, (list, tuple))
            for register in raw_registers:
                planned[_category(str(register["card_id"]), catalog)] += 1
        elif event.event_type is SOEventType.LLM_COMPLETION_FAILED:
            failed_completions += 1
        elif event.event_type is SOEventType.MATCH_SCORED:
            scored = ModelSOMatchScoredPayload.model_validate(event.payload)
        elif event.event_type is SOEventType.POLICY_PROMOTED:
            promoted = ModelSOPolicyPromotedPayload.model_validate(event.payload).model_dump(
                mode="json"
            )

    assert scored is not None, f"match {stack.identity.match_id} did not score"
    keep_rates = {
        category: (planned[category] / dealt[category]) if dealt[category] else None
        for category in sorted(dealt)
    }
    total_planned = sum(planned.values())
    return {
        "phase": phase,
        "seed": seed,
        "match_id": stack.identity.match_id,
        "policy_provenance": started_provenance,
        "winner_player_id": scored.winner_player_id,
        "is_draw": scored.is_draw,
        "end_reason": final.end_reason.value if final.end_reason else None,
        "duration_ticks": scored.duration_ticks,
        "replay_validity": {
            player: score.replay_validity for player, score in scored.scores.items()
        },
        "learning_seat": {
            "seat": learning_seat,
            "dealt": dict(sorted(dealt.items())),
            "planned": dict(sorted(planned.items())),
            "keep_rates": keep_rates,
            "planned_share": {
                category: (planned[category] / total_planned) if total_planned else None
                for category in sorted(planned)
            },
        },
        "failed_completions": failed_completions,
        "policy_promoted": promoted,
    }


def _summarize(rows: list[dict[str, Any]], *, learning_player: str) -> dict[str, Any]:
    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    categories = sorted(
        {category for row in rows for category in row["learning_seat"]["keep_rates"]}
    )
    return {
        "matches": len(rows),
        "policy_ids": sorted({row["policy_provenance"]["policy_id"] for row in rows}),
        "generations": sorted({row["policy_provenance"]["generation"] for row in rows}),
        "mean_keep_rate": {
            category: _mean(
                [
                    row["learning_seat"]["keep_rates"][category]
                    for row in rows
                    if row["learning_seat"]["keep_rates"].get(category) is not None
                ]
            )
            for category in categories
        },
        "mean_planned_share": {
            category: _mean(
                [
                    row["learning_seat"]["planned_share"][category]
                    for row in rows
                    if row["learning_seat"]["planned_share"].get(category) is not None
                ]
            )
            for category in categories
        },
        "learner_wins": sum(
            1 for row in rows if row["winner_player_id"] == learning_player and not row["is_draw"]
        ),
        "failed_completions": sum(row["failed_completions"] for row in rows),
    }


def _run_battery(args: argparse.Namespace, state_root: Path, raw_path: Path) -> int:
    learning_player, learning_mech = _SEATS[args.seat]
    rows: list[dict[str, Any]] = []

    def _run_phase(
        phase: str, *, max_value: float, seeds: list[int], stop_on_promotion: bool
    ) -> list[dict[str, Any]]:
        overlay = _lane_overlay(
            state_root, max_value=max_value, learning_player=learning_player, step=args.step
        )
        phase_rows: list[dict[str, Any]] = []
        for seed in seeds:
            row = _measure_match(
                overlay,
                seed=seed,
                phase=phase,
                learning_player=learning_player,
                learning_seat=args.seat,
                learning_mech=learning_mech,
            )
            rows.append(row)
            phase_rows.append(row)
            with raw_path.open("a", encoding="utf-8") as sink:
                sink.write(json.dumps(row, sort_keys=True) + "\n")
            provenance = row["policy_provenance"]
            print(
                f"[{phase}] seed={seed} match={row['match_id']} "
                f"gen={provenance['generation']} winner={row['winner_player_id']} "
                f"ticks={row['duration_ticks']} keep={row['learning_seat']['keep_rates']} "
                f"promoted={'yes' if row['policy_promoted'] else 'no'}",
                flush=True,
            )
            if stop_on_promotion and row["policy_promoted"] is not None:
                break
        return phase_rows

    baseline = _run_phase(
        "baseline",
        max_value=_GENESIS["aggression"],  # candidate would exceed the cap: never promotes
        seeds=[4000 + index for index in range(1, args.n + 1)],
        stop_on_promotion=False,
    )
    assert all(row["policy_promoted"] is None for row in baseline), (
        "baseline cap must forbid promotion"
    )
    assert all(row["policy_provenance"]["generation"] == 0 for row in baseline)

    promote = _run_phase(
        "promote",
        max_value=3.0,
        seeds=[4100 + index for index in range(1, _MAX_PROMOTE_ATTEMPTS + 1)],
        stop_on_promotion=True,
    )
    promotion = next((row["policy_promoted"] for row in promote if row["policy_promoted"]), None)
    if promotion is None:
        print(
            "FINDING: no promotion occurred within "
            f"{_MAX_PROMOTE_ATTEMPTS} promote-phase matches; L-GATE-2 not exercised",
            flush=True,
        )
        return 1

    post = _run_phase(
        "post",
        max_value=_GENESIS["aggression"] + args.step,  # freeze the chain at generation 1
        seeds=[4200 + index for index in range(1, args.n + 1)],
        stop_on_promotion=False,
    )
    for row in post:
        provenance = row["policy_provenance"]
        assert provenance["generation"] == 1, "post-phase match did not fly the promoted policy"
        assert provenance["policy_id"] == promotion["policy_id"]
        assert provenance["spec_hash"] == promotion["spec_hash"]
        assert provenance["source_lineage_digest"] == promotion["source_lineage_digest"]

    lineage_path = (
        state_root
        / "lineage"
        / promotion["archetype"]
        / promotion["spec_hash"]
        / f"{promotion['source_lineage_digest']}.yaml"
    )
    summary = {
        "seat": args.seat,
        "step": args.step,
        "baseline": _summarize(baseline, learning_player=learning_player),
        "promote": _summarize(promote, learning_player=learning_player),
        "post": _summarize(post, learning_player=learning_player),
        "promotion": promotion,
        "chain": {
            "lineage_record_exists": lineage_path.is_file(),
            "all_replay_valid": all(
                validity == 1 for row in rows for validity in row["replay_validity"].values()
            ),
        },
    }
    summary_path = state_root / "battery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")
    return 0


def _run_live_fire(args: argparse.Namespace, state_root: Path, raw_path: Path) -> int:
    """First live run of the selection_outcome_v1 lane: spine proof, small n."""
    learning_player, learning_mech = _SEATS[args.seat]
    overlay = _live_fire_overlay(state_root, learning_player=learning_player, args=args)
    rows: list[dict[str, Any]] = []
    promotion: dict[str, Any] | None = None

    def _one(seed: int, phase: str) -> dict[str, Any]:
        row = _measure_match(
            overlay,
            seed=seed,
            phase=phase,
            learning_player=learning_player,
            learning_seat=args.seat,
            learning_mech=learning_mech,
        )
        rows.append(row)
        with raw_path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(row, sort_keys=True) + "\n")
        provenance = row["policy_provenance"]
        print(
            f"[{phase}] seed={seed} match={row['match_id']} "
            f"gen={provenance['generation']} winner={row['winner_player_id']} "
            f"ticks={row['duration_ticks']} "
            f"promoted={'yes' if row['policy_promoted'] else 'no'}",
            flush=True,
        )
        return row

    for index in range(1, args.lf_matches + 1):
        row = _one(4300 + index, "live_fire")
        if row["policy_promoted"] is not None:
            promotion = row["policy_promoted"]
            break

    confirm: dict[str, Any] | None = None
    if promotion is not None:
        # The spine proof: the NEXT admission must fly the promoted policy.
        confirm = _one(4400, "live_fire_confirm")
        provenance = confirm["policy_provenance"]
        assert provenance["generation"] == promotion["generation"], (
            "confirm match did not fly the promoted policy"
        )
        assert provenance["policy_id"] == promotion["policy_id"]
        assert provenance["spec_hash"] == promotion["spec_hash"]
        assert provenance["source_lineage_digest"] == promotion["source_lineage_digest"]

    # Duel-gate evidence: every terminal evaluation leaves an evaluation
    # workspace (materialized specs/loadouts + per-duel sqlite ledgers) even
    # when the gate declines — cite them either way.
    evaluation_dirs = sorted(
        str(path.relative_to(state_root))
        for path in (state_root / "evaluations").glob("eval_*")
        if path.is_dir()
    )
    lineage_path: Path | None = None
    if promotion is not None:
        lineage_path = (
            state_root
            / "lineage"
            / promotion["archetype"]
            / promotion["spec_hash"]
            / f"{promotion['source_lineage_digest']}.yaml"
        )
    summary = {
        "mode": "live-fire",
        "seat": args.seat,
        "parameter": args.lf_parameter,
        "thresholds": {
            "p_value_max": args.lf_p_value_max,
            "min_decisive_n": args.lf_min_decisive_n,
            "max_draw_rate": args.lf_max_draw_rate,
        },
        "duel_battery": {
            "n_search_seeds": args.lf_search_seeds,
            "n_holdout_seeds": args.lf_holdout_seeds,
            "duel_max_ticks": args.lf_duel_max_ticks,
        },
        "matches": _summarize(rows, learning_player=learning_player),
        "promotion": promotion,
        "confirm_provenance": (confirm or {}).get("policy_provenance"),
        "chain": {
            "evaluation_workspaces": evaluation_dirs,
            "lineage_record_exists": lineage_path.is_file() if lineage_path else False,
            "all_replay_valid": all(
                validity == 1 for row in rows for validity in row["replay_validity"].values()
            ),
        },
    }
    summary_path = state_root / "live_fire_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")
    if promotion is None:
        print(
            f"FINDING: the duel gate declined promotion in all {len(rows)} matches; "
            "decline evidence retained in the evaluation workspaces above",
            flush=True,
        )
        return 0  # a legitimate decline is a reported finding, not a failure
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("battery", "live-fire"), default="battery")
    parser.add_argument("--seat", choices=tuple(_SEATS), default="blue", help="learning seat")
    parser.add_argument("--n", type=int, default=10, help="matches per before/after phase")
    parser.add_argument(
        "--step", type=float, default=0.25, help="aggression perturbation per promotion"
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=_REPO_ROOT / ".onex_state/steel_onslaught/lgate2_adaptation_battery",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe the battery lane first")
    # live-fire (selection_outcome_v1) knobs
    parser.add_argument("--lf-matches", type=int, default=8, help="live-fire match budget")
    parser.add_argument(
        "--lf-parameter",
        default="vent_at_heat_margin",
        help="perturbed aggressive-archetype spec parameter (numeric bound)",
    )
    parser.add_argument("--lf-search-seeds", type=int, default=2)
    parser.add_argument("--lf-holdout-seeds", type=int, default=2)
    parser.add_argument("--lf-duel-max-ticks", type=int, default=200)
    # Spine-proof thresholds: n_decisive from a 4-seed gate can never reach the
    # offline default min_decisive_n=10, so the lane would decline vacuously.
    # These overrides keep the gate real (parent can still win) while letting
    # promotion actually fire; the evidence doc must state them.
    parser.add_argument("--lf-min-decisive-n", type=int, default=1)
    parser.add_argument("--lf-p-value-max", type=float, default=1.0)
    parser.add_argument("--lf-max-draw-rate", type=float, default=1.0)
    args = parser.parse_args()

    state_root = args.state_root.resolve()
    if args.fresh and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    raw_path = state_root / (
        "battery_raw.jsonl" if args.mode == "battery" else "live_fire_raw.jsonl"
    )

    if args.mode == "battery":
        return _run_battery(args, state_root, raw_path)
    return _run_live_fire(args, state_root, raw_path)


if __name__ == "__main__":
    sys.exit(main())
