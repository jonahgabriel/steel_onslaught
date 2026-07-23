"""L-GATE-2 before/after adaptation battery on live keyless Qwen.

Answers the gate's empirical question (design 2026-07-22 §5, speculation
register item 3): does a promotion change a later live decision, auditably?

Three phases over ONE durable battery lane (shared event ledger + lineage
store, so the promotion chain carries across phases exactly as it does across
production processes):

1. ``baseline``  — live-learning ON, evaluator capped at ``max_value == genesis``
   so promotion is impossible; every match flies the generation-0 policy
   (aggression 1.0) WITH its guidance block.  N matches.
2. ``promote``   — cap lifted (``max_value=3.0``); matches run until the first
   ``POLICY_PROMOTED`` lands on the ledger (bounded attempts).
3. ``post``      — cap re-pinned at the promoted value (``max_value=1.25``) so
   the chain freezes at generation 1; every match flies the promoted policy
   (aggression 1.25).  N matches.

The measured observable is the learning seat's card-selection behavior using
the #117 instruments: per-category keep-rates (planned/dealt) and category
selection distribution, read from the canonical event ledger.  The audit
chain (MATCH_STARTED policy provenance -> POLICY_PROMOTED -> lineage record
digest -> per-match replay validity) is verified inline.  An inconclusive
shift is a reported finding, not a failure to hide.

Run (defaults: 10+10, ~35 s/match on the AI-PC endpoint):

    uv run python scripts/run_lgate2_adaptation_battery.py --n 10
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

_LEARNING_PLAYER = "player.blue"
_LEARNING_SEAT = "blue"
_LEARNING_MECH = "mech.blue.01"
_ARCHETYPE = "aggressive"
_GENESIS = {"aggression": 1.0}
_STEP = 0.25
_MAX_PROMOTE_ATTEMPTS = 5


def _lane_overlay(state_root: Path, *, max_value: float) -> ModelSOApplicationOverlay:
    base = load_application_overlay(_OVERLAY)
    return base.model_copy(
        update={
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
            "live_learning": ModelSOLiveLearningBinding(
                kind="win_damage_differential_v1",
                archetype=_ARCHETYPE,
                learning_player_id=_LEARNING_PLAYER,
                genesis_parameters=dict(_GENESIS),
                parameter="aggression",
                step=_STEP,
                max_value=max_value,
            ),
        }
    )


def _category(card_id: str, catalog: Any) -> str:
    return str(catalog.require(card_id).category.value)


def _measure_match(overlay: ModelSOApplicationOverlay, *, seed: int, phase: str) -> dict[str, Any]:
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
            assert seat_entry.player_id == _LEARNING_PLAYER
            started_provenance = seat_entry.model_dump(mode="json")
        elif event.event_type is SOEventType.HAND_DEALT and event.subject.mech_id == _LEARNING_MECH:
            raw_cards = event.payload["card_ids"]
            assert isinstance(raw_cards, (list, tuple))
            for card_id in raw_cards:
                dealt[_category(str(card_id), catalog)] += 1
        elif (
            event.event_type is SOEventType.PLAN_COMMITTED
            and event.subject.mech_id == _LEARNING_MECH
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
            "seat": _LEARNING_SEAT,
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


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
            1 for row in rows if row["winner_player_id"] == _LEARNING_PLAYER and not row["is_draw"]
        ),
        "failed_completions": sum(row["failed_completions"] for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=10, help="matches per before/after phase")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=_REPO_ROOT / ".onex_state/steel_onslaught/lgate2_adaptation_battery",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe the battery lane first")
    args = parser.parse_args()

    state_root = args.state_root.resolve()
    if args.fresh and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    raw_path = state_root / "battery_raw.jsonl"
    rows: list[dict[str, Any]] = []

    def _run_phase(
        phase: str, *, max_value: float, seeds: list[int], stop_on_promotion: bool
    ) -> list[dict[str, Any]]:
        overlay = _lane_overlay(state_root, max_value=max_value)
        phase_rows: list[dict[str, Any]] = []
        for seed in seeds:
            row = _measure_match(overlay, seed=seed, phase=phase)
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
        max_value=_GENESIS["aggression"] + _STEP,  # freeze the chain at generation 1
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
        "baseline": _summarize(baseline),
        "promote": _summarize(promote),
        "post": _summarize(post),
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


if __name__ == "__main__":
    sys.exit(main())
