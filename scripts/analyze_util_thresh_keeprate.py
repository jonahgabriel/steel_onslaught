#!/usr/bin/env python3
"""SO-UTIL-THRESH recompute: every number in the arm's evidence doc, from RAW
ledgers only (``battery_raw.jsonl`` + ``events.sqlite3``), never from driver
stdout, ``battery_summary.json``, or memory.

Reproduces the U-GATE paired ``hand_dealt``/``plan_committed`` keep-rate
method exactly as every sibling arm in this program defines it (see e.g.
``docs/evidence/2026-07-25-util_incentive_vp6-battery.md`` §Method): for each
seat, pair every ``hand_dealt`` with the ``plan_committed`` that follows it
for the same ``(match_id, seat)`` in ledger order (``tick``,
``sequence_in_tick``); keep-rate = (utility cards in
``plan_committed.registers[].card_id``) / (utility cards in
``hand_dealt.card_ids``); unpaired hands excluded from BOTH numerator and
denominator.

Also recomputes: all-card keep-rate (mechanical control), per-seat keep-rate,
per-round-index keep-rate table, terminal-class mix, VP composition
(bounty vs objective), utility deploy counts/conversion, match length, and
completion health -- then two-proportion z-tests against the vp6 baseline
(91/484 = 0.188017) and the vp4 bar (138/652 = 0.211656), reading both
baseline figures from their own published ledgers, not copied from a
document.

Usage::

    uv run python scripts/analyze_util_thresh_keeprate.py \\
        --state-root .onex_state/steel_onslaught/util_incentive_vp6_vpthresh48 \\
        --vp6-baseline-root <path-to>/util_incentive_vp6 \\
        --vp4-baseline-root <path-to>/util_incentive_vp4

Every path is supplied on the command line so no developer-machine absolute
path is committed. ``--vp6-baseline-root``/``--vp4-baseline-root`` are
optional; when omitted, the script reports only this arm's own recomputed
figures and the hardcoded published headline numbers for context.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

Z95 = 1.959963984540054


def wilson_interval(numerator: int, denominator: int, z: float = Z95) -> tuple[float, float, float]:
    if denominator == 0:
        return (0.0, 0.0, 0.0)
    phat = numerator / denominator
    z2 = z * z
    denom = 1 + z2 / denominator
    center = (phat + z2 / (2 * denominator)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / denominator + z2 / (4 * denominator**2)) / denom
    return (phat, center - margin, center + margin)


def two_proportion_z(n1: int, d1: int, n2: int, d2: int) -> tuple[float, float]:
    """Two-sided two-proportion z-test; returns (z, p)."""
    p1, p2 = n1 / d1, n2 / d2
    pooled = (n1 + n2) / (d1 + d2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / d1 + 1 / d2))
    if se == 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    p = math.erfc(abs(z) / math.sqrt(2))
    return (z, p)


def one_proportion_z(numerator: int, denominator: int, p0: float) -> float:
    phat = numerator / denominator
    se = math.sqrt(p0 * (1 - p0) / denominator)
    return (phat - p0) / se


def seat_of(player_id: str) -> str:
    return player_id.split(".")[1]


class Lane:
    def __init__(self, root: Path) -> None:
        self.root = root
        raw_path = root / "battery_raw.jsonl"
        db_path = root / "events.sqlite3"
        for path in (raw_path, db_path):
            if not path.exists():
                raise SystemExit(f"missing {path.name} under {root}")
        self.rows = [json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
        self.match_ids = [r["match_id"] for r in self.rows]
        self.match_by_id = {r["match_id"]: r for r in self.rows}
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    def _q(self, sql: str, extra: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        placeholders = ",".join("?" * len(self.match_ids))
        return list(self.conn.execute(sql.format(ph=placeholders), (*self.match_ids, *extra)))

    # -- keep-rate (U-GATE paired method) ------------------------------------
    def keep_rate_pairs(self) -> tuple[dict[str, dict[str, int]], int, list[dict[str, Any]]]:
        """Returns (per-seat {utility_kept, utility_dealt, all_kept, all_dealt},
        unpaired_hand_count, per-round rows [{seat, round_index, utility_kept,
        utility_dealt}])."""
        hands: dict[tuple[str, str], list[tuple[int, int, list[str]]]] = defaultdict(list)
        plans: dict[tuple[str, str], list[tuple[int, int, list[str]]]] = defaultdict(list)
        for mid, tick, seq, pid, payload in self._q(
            "select match_id, tick, sequence_in_tick, "
            'json_extract(subject_json,"$.player_id"), payload_json from events '
            'where event_type="hand_dealt" and match_id in ({ph}) '
            "order by match_id, tick, sequence_in_tick"
        ):
            hd = json.loads(payload)
            seat = hd.get("seat") or seat_of(pid)
            hands[(mid, seat)].append((tick, seq, hd["card_ids"]))
        for mid, tick, seq, pid, payload in self._q(
            "select match_id, tick, sequence_in_tick, "
            'json_extract(subject_json,"$.player_id"), payload_json from events '
            'where event_type="plan_committed" and match_id in ({ph}) '
            "order by match_id, tick, sequence_in_tick"
        ):
            pc = json.loads(payload)
            seat = pc.get("seat") or seat_of(pid)
            card_ids = [r["card_id"] for r in pc.get("registers", [])]
            plans[(mid, seat)].append((tick, seq, card_ids))

        totals: dict[str, dict[str, int]] = {
            "red": {"utility_kept": 0, "utility_dealt": 0, "all_kept": 0, "all_dealt": 0},
            "blue": {"utility_kept": 0, "utility_dealt": 0, "all_kept": 0, "all_dealt": 0},
        }
        per_round: list[dict[str, Any]] = []
        unpaired = 0
        for key, hand_list in hands.items():
            mid, seat = key
            plan_list = list(plans.get(key, []))
            plan_idx = 0
            for round_index, (h_tick, h_seq, hand_cards) in enumerate(hand_list, start=1):
                # find the next plan_committed strictly after this hand_dealt
                matched = None
                while plan_idx < len(plan_list):
                    p_tick, p_seq, plan_cards = plan_list[plan_idx]
                    if (p_tick, p_seq) > (h_tick, h_seq):
                        matched = plan_cards
                        plan_idx += 1
                        break
                    plan_idx += 1
                if matched is None:
                    unpaired += 1
                    continue
                util_dealt = sum(1 for c in hand_cards if c.startswith("card.utility."))
                util_kept = sum(1 for c in matched if c.startswith("card.utility."))
                totals[seat]["utility_dealt"] += util_dealt
                totals[seat]["utility_kept"] += util_kept
                totals[seat]["all_dealt"] += len(hand_cards)
                totals[seat]["all_kept"] += len(matched)
                per_round.append(
                    {
                        "seat": seat,
                        "round_index": round_index,
                        "utility_kept": util_kept,
                        "utility_dealt": util_dealt,
                    }
                )
        return totals, unpaired, per_round

    # -- terminal / VP / utility-deploy metrics ------------------------------
    def terminal_classes(self) -> Counter[str]:
        return Counter(r["terminal_class"] for r in self.rows)

    def vp_threshold_terminals(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["terminal_class"] == "vp_threshold"]

    def utility_deployed(self) -> tuple[int, Counter[str], Counter[str]]:
        by_seat: Counter[str] = Counter()
        by_kind: Counter[str] = Counter()
        rows = self._q(
            'select json_extract(subject_json,"$.player_id"), payload_json from events '
            'where event_type="utility_deployed" and match_id in ({ph})'
        )
        for pid, payload in rows:
            payload_d = json.loads(payload)
            by_seat[seat_of(pid)] += 1
            kind = payload_d.get("utility_kind") or "unknown"
            by_kind[kind] += 1
        return len(rows), by_seat, by_kind

    def utility_deploy_intent_count(self) -> int:
        return len(
            self._q(
                'select 1 from events where event_type="utility_deploy_intent" '
                "and match_id in ({ph})"
            )
        )

    def vp_composition(self) -> dict[str, int]:
        bounty = self.utility_deployed()[0] * 6
        objective_awards = self._q(
            'select 1 from events where event_type="objective_scored" and match_id in ({ph})'
        )
        # vp_per_round = 1 for every objective in this arena
        objective_vp = len(objective_awards)
        return {
            "bounty_vp": bounty,
            "objective_vp": objective_vp,
            "total_vp": bounty + objective_vp,
        }

    def completion_health(self) -> dict[str, Any]:
        counts: dict[str, Any] = {}
        for et in (
            "llm_completion_requested",
            "llm_completion_resolved",
            "llm_completion_failed",
            "plan_committed",
        ):
            counts[et] = len(
                self._q(f'select 1 from events where event_type="{et}" and match_id in ({{ph}})')
            )
        failure_reasons: Counter[str] = Counter(
            row[0]
            for row in self._q(
                'select json_extract(payload_json,"$.reason_code") from events '
                'where event_type="llm_completion_failed" and match_id in ({ph})'
            )
        )
        counts["failure_reasons"] = dict(failure_reasons)
        return counts

    def duration_ticks(self) -> list[int]:
        return sorted(int(r["duration_ticks"]) for r in self.rows)


def summarize_keeprate(totals: dict[str, dict[str, int]]) -> dict[str, Any]:
    pooled_kept = sum(t["utility_kept"] for t in totals.values())
    pooled_dealt = sum(t["utility_dealt"] for t in totals.values())
    phat, lo, hi = wilson_interval(pooled_kept, pooled_dealt)
    out = {
        "pooled": {"kept": pooled_kept, "dealt": pooled_dealt, "rate": phat, "wilson": (lo, hi)},
    }
    for seat, t in totals.items():
        p, slo, shi = wilson_interval(t["utility_kept"], t["utility_dealt"])
        out[seat] = {
            "kept": t["utility_kept"],
            "dealt": t["utility_dealt"],
            "rate": p,
            "wilson": (slo, shi),
        }
    all_kept = sum(t["all_kept"] for t in totals.values())
    all_dealt = sum(t["all_dealt"] for t in totals.values())
    out["all_card_control"] = {"kept": all_kept, "dealt": all_dealt, "rate": all_kept / all_dealt}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--vp6-baseline-root", type=Path, default=None)
    parser.add_argument("--vp4-baseline-root", type=Path, default=None)
    args = parser.parse_args()

    lane = Lane(args.state_root)
    totals, unpaired, per_round = lane.keep_rate_pairs()
    summary = summarize_keeprate(totals)

    print(f"=== SO-UTIL-THRESH recompute: {args.state_root} ===")
    print(f"rows: {len(lane.rows)}  unpaired hands: {unpaired}")
    print()
    print("-- keep-rate (U-GATE paired hand_dealt/plan_committed) --")
    p = summary["pooled"]
    print(
        f"pooled: {p['kept']}/{p['dealt']} = {p['rate']:.6f}  "
        f"95% Wilson [{p['wilson'][0]:.4f}, {p['wilson'][1]:.4f}] "
        f"(width {p['wilson'][1] - p['wilson'][0]:.4f})"
    )
    for seat in ("red", "blue"):
        s = summary[seat]
        print(
            f"{seat}: {s['kept']}/{s['dealt']} = {s['rate']:.6f}  "
            f"95% Wilson [{s['wilson'][0]:.4f}, {s['wilson'][1]:.4f}]"
        )
    ac = summary["all_card_control"]
    print(f"all-card control: {ac['kept']}/{ac['dealt']} = {ac['rate']:.6f}")
    print()

    print("-- per-round-index keep-rate (pooled both seats) --")
    by_round: dict[int, dict[str, int]] = defaultdict(lambda: {"kept": 0, "dealt": 0})
    for row in per_round:
        by_round[row["round_index"]]["kept"] += row["utility_kept"]
        by_round[row["round_index"]]["dealt"] += row["utility_dealt"]
    for ridx in sorted(by_round):
        d = by_round[ridx]
        rate = d["kept"] / d["dealt"] if d["dealt"] else float("nan")
        print(f"  round {ridx}: {d['kept']}/{d['dealt']} = {rate:.4f}")
    r12_kept = sum(by_round[r]["kept"] for r in by_round if r <= 2)
    r12_dealt = sum(by_round[r]["dealt"] for r in by_round if r <= 2)
    print(f"  rounds 1-2 only: {r12_kept}/{r12_dealt} = {r12_kept / r12_dealt:.6f}")
    r13_kept = sum(by_round[r]["kept"] for r in by_round if r <= 3)
    r13_dealt = sum(by_round[r]["dealt"] for r in by_round if r <= 3)
    r4p_kept = sum(by_round[r]["kept"] for r in by_round if r >= 4)
    r4p_dealt = sum(by_round[r]["dealt"] for r in by_round if r >= 4)
    if r4p_dealt:
        z, pval = two_proportion_z(r13_kept, r13_dealt, r4p_kept, r4p_dealt)
        print(
            f"  rounds 1-3 ({r13_kept}/{r13_dealt}={r13_kept / r13_dealt:.6f}) vs "
            f"rounds 4+ ({r4p_kept}/{r4p_dealt}={r4p_kept / r4p_dealt:.6f}): z={z:.3f} p={pval:.4f}"
        )
    else:
        print("  rounds 4+: NONE PLAYED (all matches ended by round 3)")
    print()

    print("-- terminal classes --")
    tc = lane.terminal_classes()
    for k, v in sorted(tc.items()):
        print(f"  {k}: {v}")
    vpterm = lane.vp_threshold_terminals()
    print(f"  vp_threshold terminals: {len(vpterm)}/{len(lane.rows)}")
    print()

    print("-- utility deploy / VP composition --")
    n_deployed, by_seat, by_kind = lane.utility_deployed()
    n_intent = lane.utility_deploy_intent_count()
    print(f"  utility_deploy_intent: {n_intent}  utility_deployed: {n_deployed}")
    print(f"  by seat: {dict(sorted(by_seat.items()))}")
    print(f"  by kind: {dict(sorted(by_kind.items()))}")
    print(
        f"  intent-to-resolved (engine-internal; expected ~100% every rung): "
        f"{n_deployed}/{n_intent} = {n_deployed / n_intent:.4f}"
        if n_intent
        else "  n/a"
    )
    # "Programmed-to-resolved conversion" (the quantity every sibling evidence
    # doc reports under this name) divides utility_deployed by the POOLED
    # utility "kept" figure from the U-GATE keep-rate pairing above -- NOT by
    # the utility_deploy_intent event count. Verified against all three
    # published ladder figures: vp2 102/115=88.7%, vp4 119/138=86.2%,
    # vp6 84/91=92.3%, where 115/138/91 are each rung's own PRIMARY pooled
    # "kept" number, not its utility_deploy_intent event count (102/119/84,
    # which instead equals utility_deployed exactly in every rung -- intent
    # always resolves once fired; the two are simply unrelated statistics).
    pooled_kept = summary["pooled"]["kept"]
    print(
        f"  programmed-to-resolved conversion (deployed / pooled utility 'kept'): "
        f"{n_deployed}/{pooled_kept} = {n_deployed / pooled_kept:.4f}"
    )
    vpc = lane.vp_composition()
    if vpc["total_vp"]:
        share = vpc["bounty_vp"] / vpc["total_vp"]
        print(f"  VP composition: {vpc}  bounty share = {share:.4f}")
    else:
        print("  no VP scored")
    print()

    print("-- match length --")
    ticks = lane.duration_ticks()
    import statistics as st

    print(f"  min={ticks[0]} median={st.median(ticks)} mean={st.fmean(ticks):.2f} max={ticks[-1]}")
    print()

    print("-- completion health --")
    ch = lane.completion_health()
    print(f"  {ch}")
    print()

    if args.vp6_baseline_root:
        baseline = Lane(args.vp6_baseline_root)
        btotals, _, _ = baseline.keep_rate_pairs()
        bsum = summarize_keeprate(btotals)
        bp = bsum["pooled"]
        print(f"-- recomputed vp6 baseline ({args.vp6_baseline_root}) --")
        print(f"pooled: {bp['kept']}/{bp['dealt']} = {bp['rate']:.6f}")
        z, pval = two_proportion_z(p["kept"], p["dealt"], bp["kept"], bp["dealt"])
        print(f"this arm vs vp6 baseline: z={z:.3f} p={pval:.4f}")
        print()

    if args.vp4_baseline_root:
        baseline4 = Lane(args.vp4_baseline_root)
        b4totals, _, _ = baseline4.keep_rate_pairs()
        b4sum = summarize_keeprate(b4totals)
        b4p = b4sum["pooled"]
        print(f"-- recomputed vp4 bar ({args.vp4_baseline_root}) --")
        print(f"pooled: {b4p['kept']}/{b4p['dealt']} = {b4p['rate']:.6f}")
        z, pval = two_proportion_z(p["kept"], p["dealt"], b4p["kept"], b4p["dealt"])
        print(f"this arm vs vp4 bar: z={z:.3f} p={pval:.4f}")
        bar = b4p["rate"]
        verdict = "H_ARTIFACT" if p["rate"] >= bar else "H_INTERIOR"
        print(f"SCORED CRITERION: pooled {p['rate']:.6f} vs bar {bar:.6f} -> {verdict}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
