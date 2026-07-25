#!/usr/bin/env python3
"""Factorial (2x2) re-analysis of the dmg16 composition arms from RAW ledgers.

The four corners of the ``covered_advance`` x ``spatial_r1`` factorial at the
x16 dose all exist as completed n=30 batteries (seeds 5001-5030, same arena
``foundry_60_asym_v1``, same loadouts):

===========  ==========================  ============================================
corner       state root                  levers
===========  ==========================  ============================================
P6           ``pair_p6_dmg16``           neither (red ``deck.movement.v1``, plain pilots)
CA           ``composition_ca_only_dmg16``  ``covered_advance`` only (red ``deck.movement.v2``)
R1           ``composition_r1_only_dmg16``  spatial R1 only (both seats' ``*_spatial_r1`` pilots)
COMP         ``composition_p6dmg16_covadv_r1``  both
===========  ==========================  ============================================

This script recomputes every number in
``docs/evidence/2026-07-25-composition-interaction-analysis.md`` from
``battery_raw.jsonl`` + ``events.sqlite3`` only. ``battery_summary.json`` is
never read (under per-seed invocation it describes one seed).

Usage::

    python scripts/analyze_composition_interaction.py \\
        --p6   <path-to>/pair_p6_dmg16 \\
        --ca   <path-to>/composition_ca_only_dmg16 \\
        --r1   <path-to>/composition_r1_only_dmg16 \\
        --comp <path-to>/composition_p6dmg16_covadv_r1

Each path is a battery state root containing ``battery_raw.jsonl`` and
``events.sqlite3``. Paths are supplied on the command line precisely so no
developer-machine absolute path is committed.

Method notes that matter for reading the output:

* Every aggregate is filtered to the ``match_id`` set present in
  ``battery_raw.jsonl`` (30 rows/arm). Orphan ``match_started`` rows left by
  transport retries are excluded, per the contamination class the sibling arm
  docs record.
* The factorial interaction term is ``COMP - CA - R1 + P6`` on whatever
  statistic is named. This is an OBSERVATIONAL decomposition of four
  independently-run arms, not a pre-registered factorial experiment.
* Bootstrap intervals resample each arm independently (matches are the
  resampling unit; for rate endpoints the numerator/denominator pair is
  resampled together, i.e. a cluster bootstrap over matches).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics as st
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

ARM_ORDER = ("P6", "CA", "R1", "COMP")
BOOT_SEED = 20260725
BOOT_N = 20000


def quantile(values: Sequence[float], p: float) -> float:
    """Linear-interpolation quantile (same convention as ``numpy.percentile``)."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return float(ordered[0])
    h = (n - 1) * p
    lo = int(h)
    hi = min(lo + 1, n - 1)
    return float(ordered[lo] + (h - lo) * (ordered[hi] - ordered[lo]))


class Arm:
    """One factorial corner, loaded from its raw ledger."""

    def __init__(self, name: str, root: Path) -> None:
        self.name = name
        self.root = root
        raw_path = root / "battery_raw.jsonl"
        db_path = root / "events.sqlite3"
        for path in (raw_path, db_path):
            if not path.exists():
                raise SystemExit(f"{name}: missing {path.name} under the supplied state root")
        self.rows = sorted(
            (json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()),
            key=lambda r: r["seed"],
        )
        self.match_ids = [r["match_id"] for r in self.rows]
        self.conn = sqlite3.connect(db_path)
        self.matches = {r["match_id"]: dict(r) for r in self.rows}
        self._load_events()

    # -- ledger extraction --------------------------------------------------
    def _q(self, sql: str) -> Iterable[tuple]:
        placeholders = ",".join("?" * len(self.match_ids))
        return self.conn.execute(sql.format(ph=placeholders), self.match_ids)

    def _load_events(self) -> None:
        for m in self.matches.values():
            m.setdefault("_counts", {})

        def bump(mid: str, key: str, n: int) -> None:
            if mid in self.matches:
                self.matches[mid]["_counts"][key] = self.matches[mid]["_counts"].get(key, 0) + n

        for mid, pid, n in self._q(
            'select match_id, json_extract(subject_json,"$.player_id"), count(*) from events '
            'where event_type="weapon_fired" and match_id in ({ph}) group by 1,2'
        ):
            bump(mid, f"fired_{seat(pid)}", n)
        for mid, pid, reason, n in self._q(
            'select match_id, json_extract(subject_json,"$.player_id"), '
            'json_extract(payload_json,"$.reason"), count(*) from events '
            'where event_type="weapon_fire_rejected" and match_id in ({ph}) group by 1,2,3'
        ):
            bump(mid, f"rej_{seat(pid)}_{reason}", n)
        for mid, pid, n in self._q(
            'select match_id, json_extract(subject_json,"$.player_id"), count(*) from events '
            'where event_type="weapon_fired" '
            'and json_extract(payload_json,"$.hit_probability")=0.0 '
            "and match_id in ({ph}) group by 1,2"
        ):
            bump(mid, f"zerop_{seat(pid)}", n)
        for mid, pid, n in self._q(
            'select match_id, json_extract(subject_json,"$.player_id"), count(*) from events '
            'where event_type="hit_resolved" and json_extract(payload_json,"$.result.hit")=1 '
            "and match_id in ({ph}) group by 1,2"
        ):
            bump(mid, f"hits_{seat(pid)}", n)
        for mid, t in self._q(
            'select match_id, min(tick) from events where event_type="hit_resolved" '
            'and json_extract(payload_json,"$.result.hit")=1 and match_id in ({ph}) group by 1'
        ):
            self.matches[mid]["first_hit_tick"] = t
        for mid, pid, payload in self._q(
            'select match_id, json_extract(subject_json,"$.player_id"), payload_json from events '
            'where event_type="plan_committed" and match_id in ({ph})'
        ):
            plan = json.loads(payload)
            s = seat(pid)
            bump(mid, f"plans_{s}", 1)
            bump(mid, f"registers_{s}", len(plan.get("registers", [])))
            bump(
                mid,
                f"covered_advance_{s}",
                sum(
                    1
                    for r in plan.get("registers", [])
                    if r.get("card_id") == "card.movement.covered_advance"
                ),
            )
            if plan.get("spatial_read") is not None:
                bump(mid, f"spatial_read_{s}", 1)
        self._load_close_ticks()

    def _load_close_ticks(self, threshold: float = 12.0) -> None:
        """First tick at which the two mechs are within ``threshold`` grid units."""
        for mid in self.match_ids:
            last: dict[str, tuple[int, int]] = {}
            close_tick: int | None = None
            for tick, pid, payload in self.conn.execute(
                'select tick, json_extract(subject_json,"$.player_id"), payload_json from events '
                'where match_id=? and event_type="movement_resolved" '
                "order by tick, sequence_in_tick",
                (mid,),
            ):
                to = json.loads(payload)["to"]
                last[pid] = (to["x"], to["y"])
                if len(last) == 2:
                    (ax, ay), (bx, by) = last["player.red"], last["player.blue"]
                    if math.hypot(ax - bx, ay - by) <= threshold:
                        close_tick = tick
                        break
            self.matches[mid]["close_tick"] = close_tick

    # -- accessors ----------------------------------------------------------
    def count(self, mid: str, key: str) -> int:
        return int(self.matches[mid]["_counts"].get(key, 0))

    @property
    def lengths(self) -> list[int]:
        return [int(m["duration_ticks"]) for m in self.matches.values()]

    def eliminations(self) -> list[dict]:
        return [m for m in self.matches.values() if m["terminal_class"] == "elimination"]

    def red_fire_pairs(self) -> list[tuple[int, int]]:
        """(out-of-range rejections, total fire attempts) per match, red seat."""
        out = []
        for mid in self.match_ids:
            oor = self.count(mid, "rej_red_target_out_of_range")
            attempts = (
                self.count(mid, "fired_red")
                + oor
                + sum(
                    v
                    for k, v in self.matches[mid]["_counts"].items()
                    if k.startswith("rej_red_") and k != "rej_red_target_out_of_range"
                )
            )
            out.append((oor, attempts))
        return out


def seat(player_id: str) -> str:
    return player_id.split(".")[1]


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation (no tie correction; ties broken by input order)."""

    def ranks(v: Sequence[float]) -> list[int]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0] * len(v)
        for rank, idx in enumerate(order):
            out[idx] = rank + 1
        return out

    ra, rb = ranks(a), ranks(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p-value for the 2x2 table [[a,b],[c,d]]."""
    from math import comb

    n = a + b + c + d
    row1, col1, col2 = a + b, a + c, b + d

    def prob(x: int) -> float:
        return comb(col1, x) * comb(col2, row1 - x) / comb(n, row1)

    p_obs = prob(a)
    return sum(
        prob(x)
        for x in range(max(0, row1 - col2), min(row1, col1) + 1)
        if prob(x) <= p_obs * (1 + 1e-12)
    )


# -- factorial helpers ------------------------------------------------------
def factorial_terms(values: dict[str, float]) -> dict[str, float]:
    p6, ca, r1, comp = (values[k] for k in ARM_ORDER)
    return {
        "P6": p6,
        "CA": ca,
        "R1": r1,
        "COMP": comp,
        "main_ca": ca - p6,
        "main_r1": r1 - p6,
        "additive": ca + r1 - p6,
        "interaction": comp - ca - r1 + p6,
    }


def bootstrap_interaction(
    samples: dict[str, list], statistic: Callable[[list], float], n: int = BOOT_N
) -> tuple[float, float, float, float]:
    rng = random.Random(BOOT_SEED)
    draws = []
    for _ in range(n):
        vals = {
            k: statistic([rng.choice(samples[k]) for _ in range(len(samples[k]))])
            for k in ARM_ORDER
        }
        draws.append(vals["COMP"] - vals["CA"] - vals["R1"] + vals["P6"])
    draws.sort()
    return (
        draws[int(0.025 * n)],
        draws[n // 2],
        draws[int(0.975 * n)],
        sum(1 for d in draws if d <= 0) / n,
    )


def report(arms: dict[str, Arm]) -> None:
    lengths = {k: [float(x) for x in arms[k].lengths] for k in ARM_ORDER}

    print("=" * 78)
    print("1. MATCH-LENGTH DISTRIBUTIONS (all matches, aborts included)")
    for k in ARM_ORDER:
        v = lengths[k]
        print(
            f"  {k:5} n={len(v):2}  min={min(v):5.1f} median={quantile(v, 0.5):6.2f} "
            f"mean={st.mean(v):6.2f} p75={quantile(v, 0.75):6.2f} p90={quantile(v, 0.9):6.2f} "
            f"max={max(v):6.1f} sd={st.pstdev(v):6.2f}"
        )
        print(f"        sorted: {[int(x) for x in sorted(v)]}")

    print("\n2. FACTORIAL DECOMPOSITION OF MATCH LENGTH (interaction = COMP - CA - R1 + P6)")
    print(
        f"  {'stat':8}{'P6':>8}{'CA':>8}{'R1':>8}{'COMP':>8}"
        f"{'ME_CA':>9}{'ME_R1':>9}{'additive':>10}{'INTER':>9}"
    )
    stats: dict[str, Callable[[list], float]] = {
        "median": lambda v: quantile(v, 0.5),
        "mean": st.mean,
        "p75": lambda v: quantile(v, 0.75),
        "p90": lambda v: quantile(v, 0.9),
        "max": max,
        "sd": st.pstdev,
    }
    for name, fn in stats.items():
        t = factorial_terms({k: fn(lengths[k]) for k in ARM_ORDER})
        print(
            f"  {name:8}{t['P6']:8.2f}{t['CA']:8.2f}{t['R1']:8.2f}{t['COMP']:8.2f}"
            f"{t['main_ca']:+9.2f}{t['main_r1']:+9.2f}{t['additive']:10.2f}{t['interaction']:+9.2f}"
        )

    print("\n3. LOG-SCALE (MULTIPLICATIVE) DECOMPOSITION")
    logs = {k: [math.log(x) for x in lengths[k]] for k in ARM_ORDER}
    t = factorial_terms({k: st.mean(logs[k]) for k in ARM_ORDER})
    se = math.sqrt(sum((st.stdev(logs[k]) / math.sqrt(len(logs[k]))) ** 2 for k in ARM_ORDER))
    lo, hi = t["interaction"] - 1.96 * se, t["interaction"] + 1.96 * se
    for k in ARM_ORDER:
        print(
            f"  {k:5} geo-mean={math.exp(st.mean(logs[k])):6.2f}  sd(log)={st.pstdev(logs[k]):.4f}"
        )
    print(
        f"  ME_CA=x{math.exp(t['main_ca']):.3f}  ME_R1=x{math.exp(t['main_r1']):.3f}  "
        f"additive-in-log geo-mean={math.exp(t['additive']):.2f}  "
        f"observed={math.exp(t['COMP']):.2f}"
    )
    print(
        f"  INTERACTION(log)={t['interaction']:+.4f} (x{math.exp(t['interaction']):.3f}), "
        f"SE={se:.4f}, 95% CI [x{math.exp(lo):.3f}, x{math.exp(hi):.3f}], "
        f"z={t['interaction'] / se:+.2f}"
    )

    print("\n4. BOOTSTRAP 95% CI ON THE LENGTH INTERACTION (independent per-arm resample)")
    for name in ("median", "mean", "p75", "p90"):
        lo_b, med_b, hi_b, share = bootstrap_interaction(lengths, stats[name])
        print(
            f"  {name:7}: interaction 95% CI [{lo_b:+7.2f}, {hi_b:+7.2f}] "
            f"boot-median {med_b:+6.2f}  share<=0 {share:.3f}"
        )

    print("\n5. OUT-OF-RANGE FIRE FRACTION (red seat)")
    pairs = {k: arms[k].red_fire_pairs() for k in ARM_ORDER}
    agg = {k: (sum(a for a, _ in v), sum(b for _, b in v)) for k, v in pairs.items()}
    for k in ARM_ORDER:
        a, b = agg[k]
        print(f"  {k:5} {a}/{b} = {a / b:.4f}")
    t = factorial_terms({k: agg[k][0] / agg[k][1] for k in ARM_ORDER})
    print(
        f"  ME_CA={t['main_ca']:+.4f}  ME_R1={t['main_r1']:+.4f}  "
        f"additive={t['additive']:.4f}  INTERACTION={t['interaction']:+.4f}"
    )
    lo_b, med_b, hi_b, share = bootstrap_interaction(
        pairs, lambda s: sum(a for a, _ in s) / max(sum(b for _, b in s), 1), n=BOOT_N // 4
    )
    print(
        f"  cluster bootstrap: interaction 95% CI [{lo_b:+.4f}, {hi_b:+.4f}] "
        f"boot-median {med_b:+.4f} share<=0 {share:.3f}"
    )

    print("\n6. PHASE DECOMPOSITION (elimination matches that both close and land a hit)")
    phases: dict[str, list[tuple[float, float, float]]] = {}
    for k in ARM_ORDER:
        rows = []
        for m in arms[k].eliminations():
            close, hit = m.get("close_tick"), m.get("first_hit_tick")
            if close is None or hit is None:
                continue
            rows.append((float(close), float(hit - close), float(m["duration_ticks"] - hit)))
        phases[k] = rows
    print(f"  {'arm':6}{'n':>4}{'close':>9}{'convert':>9}{'finish':>9}")
    for k in ARM_ORDER:
        rows = phases[k]
        print(
            f"  {k:6}{len(rows):>4}{st.mean(r[0] for r in rows):>9.2f}"
            f"{st.mean(r[1] for r in rows):>9.2f}{st.mean(r[2] for r in rows):>9.2f}"
        )
    for idx, label in enumerate(("close", "convert", "finish")):
        t = factorial_terms({k: st.mean(r[idx] for r in phases[k]) for k in ARM_ORDER})
        print(
            f"  {label:8} ME_CA={t['main_ca']:+7.2f} ME_R1={t['main_r1']:+7.2f} "
            f"INTERACTION={t['interaction']:+7.2f}"
        )
    elim_len = {k: [r[0] + r[1] + r[2] for r in phases[k]] for k in ARM_ORDER}
    pre = {k: [r[0] + r[1] for r in phases[k]] for k in ARM_ORDER}
    post = {k: [r[2] for r in phases[k]] for k in ARM_ORDER}
    for label, sample in (("length", elim_len), ("pre-contact", pre), ("post-contact", post)):
        lo_b, med_b, hi_b, share = bootstrap_interaction(sample, st.mean)
        print(
            f"  bootstrap {label:13}: interaction 95% CI [{lo_b:+.2f}, {hi_b:+.2f}] "
            f"boot-median {med_b:+.2f} share<=0 {share:.3f}"
        )

    print("\n7. COMPOSITION TAIL vs REST (tail = longer than any single-lever arm ever produced)")
    cutoff = max(max(lengths["CA"]), max(lengths["R1"]), max(lengths["P6"]))
    comp = arms["COMP"]
    tail = [m for m in comp.matches.values() if m["duration_ticks"] > cutoff]
    rest = [m for m in comp.matches.values() if m["duration_ticks"] <= cutoff]
    print(f"  cutoff = {cutoff:.0f} ticks (max over P6/CA/R1)")
    for label, group in (("TAIL", tail), ("REST", rest)):
        n_group = len(group)

        def avg(fn: Callable[[dict], float], rows: list[dict] = group) -> float:
            return st.mean(fn(m) for m in rows)

        def hits(m: dict) -> int:
            mid = m["match_id"]
            return comp.count(mid, "hits_red") + comp.count(mid, "hits_blue")

        def attempts(m: dict) -> int:
            mid = m["match_id"]
            return (
                comp.count(mid, "fired_red")
                + comp.count(mid, "rej_red_target_out_of_range")
                + comp.count(mid, "rej_red_weapon_on_cooldown")
            )

        def cov_adv_share(m: dict) -> float:
            mid = m["match_id"]
            return comp.count(mid, "covered_advance_red") / max(comp.count(mid, "registers_red"), 1)

        ticks = avg(lambda m: m["duration_ticks"])
        first_hit = avg(lambda m: m.get("first_hit_tick") or m["duration_ticks"])
        close = st.mean(m["close_tick"] for m in group if m["close_tick"])
        print(
            f"  {label} n={n_group}: ticks={ticks:6.1f} first_hit={first_hit:6.1f} "
            f"close_tick={close:6.1f} red_attempts={avg(attempts):5.1f}"
        )
        print(
            f"        total_hits={avg(hits):5.2f} "
            f"hits/tick={avg(lambda m: hits(m) / m['duration_ticks']):.4f} "
            f"blue_zero_p={avg(lambda m: comp.count(m['match_id'], 'zerop_blue')):5.2f} "
            f"cov_adv_share={avg(cov_adv_share):.3f}"
        )
        if label == "TAIL":
            print(f"        seeds={sorted(m['seed'] for m in group)}")

    print("\n8. TAIL-COUNT CONTRAST AND THRESHOLD SWEEP")
    pooled = lengths["P6"] + lengths["CA"] + lengths["R1"]
    for thresh in (40, 45, 50, 55, 60, 65, 70, 80):
        a = sum(1 for x in lengths["COMP"] if x > thresh)
        c = sum(1 for x in pooled if x > thresh)
        print(f"  > {thresh:3} ticks: COMP {a:2}/30  pooled single-lever+floor {c:2}/90")
    a = sum(1 for x in lengths["COMP"] if x > cutoff)
    print(
        f"  Fisher exact (two-sided), COMP {a}/30 vs pooled 0/90 above {cutoff:.0f}: "
        f"p={fisher_exact(a, 30 - a, 0, 90):.5f}"
    )

    print("\n9. NO-INTERACTION PREDICTIVE CHECKS FOR THE TAIL")
    print("   (a) nonparametric surrogate: resample a single-lever arm, scale by the other")
    print("       lever's log main effect. NOTE this surrogate CANNOT emit a value above")
    print("       base_max x scale, so its 'max' p-value is structurally optimistic.")
    rng = random.Random(BOOT_SEED)
    logs = {k: [math.log(x) for x in lengths[k]] for k in ARM_ORDER}
    observed = {
        "median": quantile(lengths["COMP"], 0.5),
        "mean": st.mean(lengths["COMP"]),
        "p90": quantile(lengths["COMP"], 0.9),
        "max": max(lengths["COMP"]),
        "sd(log)": st.pstdev(logs["COMP"]),
        f"n>{cutoff:.0f}": float(sum(1 for x in lengths["COMP"] if x > cutoff)),
    }
    for base, donor in (("CA", "R1"), ("R1", "CA")):
        acc: dict[str, list[float]] = {k: [] for k in observed}
        for _ in range(BOOT_N // 4):
            scale = math.exp(
                st.mean(rng.choice(logs[donor]) for _ in range(30))
                - st.mean(rng.choice(logs["P6"]) for _ in range(30))
            )
            sample = [rng.choice(lengths[base]) * scale for _ in range(30)]
            acc["median"].append(quantile(sample, 0.5))
            acc["mean"].append(st.mean(sample))
            acc["p90"].append(quantile(sample, 0.9))
            acc["max"].append(max(sample))
            acc["sd(log)"].append(st.pstdev([math.log(x) for x in sample]))
            acc[f"n>{cutoff:.0f}"].append(float(sum(1 for x in sample if x > cutoff)))
        print(f"     surrogate = {base} resample x exp(ME_{donor})")
        for key, draws in acc.items():
            draws.sort()
            n = len(draws)
            p = sum(1 for d in draws if d >= observed[key]) / n
            print(
                f"       {key:8}: null 95% "
                f"[{draws[int(0.025 * n)]:7.2f},{draws[int(0.975 * n)]:7.2f}] "
                f"median {draws[n // 2]:7.2f} | observed {observed[key]:7.2f} | "
                f"P(null>=obs)={p:.4f}"
            )
    print("   (b) parametric lognormal null with unbounded support (mu and variance both")
    print("       additive across levers) — the check the surrogate above cannot do.")
    mu_pred = st.mean(logs["CA"]) + st.mean(logs["R1"]) - st.mean(logs["P6"])
    var_pred = st.variance(logs["CA"]) + st.variance(logs["R1"]) - st.variance(logs["P6"])
    sigma = math.sqrt(var_pred)
    print(f"     mu_pred={mu_pred:.4f} (geo-mean {math.exp(mu_pred):.2f}), sigma_pred={sigma:.4f}")
    acc = {k: [] for k in observed}
    for _ in range(BOOT_N * 2):
        sample = [math.exp(rng.gauss(mu_pred, sigma)) for _ in range(30)]
        acc["median"].append(quantile(sample, 0.5))
        acc["mean"].append(st.mean(sample))
        acc["p90"].append(quantile(sample, 0.9))
        acc["max"].append(max(sample))
        acc["sd(log)"].append(st.pstdev([math.log(x) for x in sample]))
        acc[f"n>{cutoff:.0f}"].append(float(sum(1 for x in sample if x > cutoff)))
    for key, draws in acc.items():
        draws.sort()
        n = len(draws)
        p = sum(1 for d in draws if d >= observed[key]) / n
        print(
            f"       {key:8}: null 95% [{draws[int(0.025 * n)]:7.2f},{draws[int(0.975 * n)]:7.2f}] "
            f"median {draws[n // 2]:7.2f} | observed {observed[key]:7.2f} | P(null>=obs)={p:.4f}"
        )
    ordered = sorted(lengths["COMP"])
    print("   (c) sensitivity of the composition's sd(log) to its longest matches")
    for drop in (0, 1, 2):
        kept = ordered[: len(ordered) - drop] if drop else ordered
        print(
            f"       drop top {drop}: n={len(kept)} "
            f"sd(log)={st.pstdev([math.log(x) for x in kept]):.4f}"
        )

    print("\n10. WIN RATE (decided matches only) AND CROSS-ARM SEED CORRESPONDENCE")
    wins = {}
    for k in ARM_ORDER:
        decided = [m for m in arms[k].matches.values() if m["winner_player_id"] is not None]
        red = sum(1 for m in decided if m["winner_player_id"] == "player.red")
        wins[k] = (red, len(decided))
        print(f"  {k:5} red {red}/{len(decided)} = {red / len(decided):.4f}")
    t = factorial_terms({k: wins[k][0] / wins[k][1] for k in ARM_ORDER})
    print(
        f"  ME_CA={t['main_ca']:+.4f} ME_R1={t['main_r1']:+.4f} "
        f"additive={t['additive']:.4f} INTERACTION={t['interaction']:+.4f}"
    )
    rng2 = random.Random(BOOT_SEED)
    draws = []
    for _ in range(BOOT_N):
        sim = {
            k: sum(rng2.random() < wins[k][0] / wins[k][1] for _ in range(wins[k][1])) / wins[k][1]
            for k in ARM_ORDER
        }
        draws.append(sim["COMP"] - sim["CA"] - sim["R1"] + sim["P6"])
    draws.sort()
    print(
        f"  parametric bootstrap 95% CI [{draws[int(0.025 * BOOT_N)]:+.4f}, "
        f"{draws[int(0.975 * BOOT_N)]:+.4f}] median {draws[BOOT_N // 2]:+.4f}"
    )
    by_seed = {
        k: {m["seed"]: m["duration_ticks"] for m in arms[k].matches.values()} for k in ARM_ORDER
    }
    seeds = sorted(by_seed["COMP"])
    print("  Spearman rho of match length between arms (seed pairing sanity check):")
    for i, a_name in enumerate(ARM_ORDER):
        for b_name in ARM_ORDER[i + 1 :]:
            xs = [by_seed[a_name][s] for s in seeds]
            ys = [by_seed[b_name][s] for s in seeds]
            print(f"    rho({a_name},{b_name}) = {spearman(xs, ys):+.3f}")

    print("\n11. TELEMETRY CHECK — spatial_read population by arm (plan_committed)")
    for k in ARM_ORDER:
        a_arm = arms[k]
        pop = sum(
            a_arm.count(mid, "spatial_read_red") + a_arm.count(mid, "spatial_read_blue")
            for mid in a_arm.match_ids
        )
        plans = sum(
            a_arm.count(mid, "plans_red") + a_arm.count(mid, "plans_blue")
            for mid in a_arm.match_ids
        )
        print(f"  {k:5} spatial_read non-null {pop}/{plans} plans")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("p6", "ca", "r1", "comp"):
        ap.add_argument(
            f"--{flag}", required=True, type=Path, help=f"{flag.upper()} battery state root"
        )
    args = ap.parse_args()
    arms = {
        "P6": Arm("P6", args.p6),
        "CA": Arm("CA", args.ca),
        "R1": Arm("R1", args.r1),
        "COMP": Arm("COMP", args.comp),
    }
    report(arms)


if __name__ == "__main__":
    main()
