#!/usr/bin/env python3
"""Measure DRAW-THROUGH for the heat-drafting deckbuilder kill-gate.

Question (docs/design/2026-07-22-heat-drafting-deckbuilder-design.md SS2.4):
if a card is acquired MID-MATCH (Dominion semantics -- the acquired card goes
to the DISCARD pile and only re-enters play at the next reshuffle), what is
the probability it is (a) drawn into a hand and (b) actually programmed
before the match reaches a terminal, under the CURRENT post-#117 mechanics
(split decks, over-deal: deal 4 movement + 4 weapon = 8, program 5)?

Two evidence sources, deliberately separated:

1. RECORDED LEDGER FACTS (``--ledger``): an events.sqlite3 battery ledger
   recorded by the real runtime (e.g. the ``tactical_split_overdeal_v1_qwen``
   battery).  Extracted: match-length distribution (programming phases per
   match), terminal reasons, observed reshuffle cadence, and the empirical
   per-card P(programmed | dealt) selection behaviour of real LLM pilots.

2. DETERMINISTIC INJECTION SIMULATION: drives the ACTUAL engine dealer
   (``steel_onslaught.cards.dealer.DealerCompute`` -- the same BLAKE2-seeded
   Fisher-Yates deal/reshuffle code the runtime uses; rules are imported, not
   re-implemented) over the real committed deck composition
   (``contracts_data/decks/weapon_v1.yaml``, 20 cards, quota 4/round, whole
   dealt hand discarded each round exactly as
   ``match/card_adapter.py::_split_state_for_next_round`` does).  A marker
   card is injected into the discard pile at round k (k = 1..N); the sim then
   records when the marker first reaches a dealt hand and how many times it is
   dealt.  Combining those mechanical curves with the measured match-length
   distribution yields P(drawn | acquired at k) and P(played | acquired at k).

Usage::

    uv run python scripts/measure_draw_through.py \
        --ledger path/to/events.sqlite3 [--seeds 1000] [--max-inject 15]

The ledger path is a runtime argument on purpose: battery ledgers live in
gitignored ``.onex_state`` trees and must never be hardcoded here.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from steel_onslaught.cards.dealer import (
    DealerCompute,
    ModelSODealerScope,
    ModelSODeckState,
)
from steel_onslaught.contracts.deck import ModelSODeck

MARKER = "card.marker.draft_probe"


# ---------------------------------------------------------------------------
# Part 1 -- recorded ledger facts
# ---------------------------------------------------------------------------


def extract_ledger_facts(ledger: Path) -> dict[str, object]:
    """Read match lengths, terminal reasons, reshuffle cadence and selection rates."""

    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    hand_rows = con.execute(
        """
        SELECT match_id, tick, sequence_in_tick, payload_json
        FROM events WHERE event_type = 'hand_dealt'
        ORDER BY match_id, tick, sequence_in_tick
        """
    ).fetchall()
    plan_rows = con.execute(
        """
        SELECT match_id, tick, sequence_in_tick, payload_json
        FROM events WHERE event_type = 'plan_committed'
        ORDER BY match_id, tick, sequence_in_tick
        """
    ).fetchall()
    end_rows = con.execute(
        """
        SELECT match_id, json_extract(payload_json, '$.reason') AS reason
        FROM events WHERE event_type = 'match_ended'
        """
    ).fetchall()
    con.close()

    end_reason = {row["match_id"]: row["reason"] for row in end_rows}

    hands: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in hand_rows:
        payload = json.loads(row["payload_json"])
        hands[(row["match_id"], payload["seat"])].append(payload)
    plans: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in plan_rows:
        payload = json.loads(row["payload_json"])
        plans[(row["match_id"], payload["seat"])].append(payload)

    # Match length in programming phases (per match; seats always deal together).
    rounds_by_match: dict[str, int] = {}
    hand_sizes: Counter[int] = Counter()
    reshuffle_rounds: Counter[int] = Counter()
    dealt_counter: Counter[str] = Counter()
    chosen_counter: Counter[str] = Counter()
    chosen_per_plan: list[int] = []

    for (match_id, _seat), seat_hands in hands.items():
        rounds_by_match[match_id] = max(rounds_by_match.get(match_id, 0), len(seat_hands))
        for round_index, payload in enumerate(seat_hands, start=1):
            hand_sizes[int(payload["hand_size"])] += 1
            partitions = payload.get("partitions") or {}
            for part in partitions.values():
                if part.get("reshuffled"):
                    reshuffle_rounds[round_index] += 1

    for key, seat_hands in hands.items():
        seat_plans = plans.get(key, [])
        for payload, plan in zip(seat_hands, seat_plans, strict=False):
            hand_cards = Counter(payload["card_ids"])
            plan_cards = Counter(reg["card_id"] for reg in plan["registers"])
            chosen_per_plan.append(sum(plan_cards.values()))
            dealt_counter.update(hand_cards)
            # A plan may repeat a card id more often than dealt only via
            # heat-locked carry-forward; clamp to the dealt multiset so the
            # selection rate stays P(programmed | dealt).
            for card_id, dealt_n in hand_cards.items():
                chosen_counter[card_id] += min(plan_cards.get(card_id, 0), dealt_n)

    lengths_all = sorted(rounds_by_match.values())
    clean_reasons = {"last_mech_standing", "draw_max_ticks"}
    lengths_clean = sorted(
        rounds
        for match_id, rounds in rounds_by_match.items()
        if end_reason.get(match_id) in clean_reasons
    )
    selection_rates = {
        card_id: chosen_counter[card_id] / dealt_counter[card_id]
        for card_id in sorted(dealt_counter)
    }
    return {
        "matches": len(rounds_by_match),
        "end_reasons": dict(Counter(end_reason.values())),
        "hand_sizes": dict(hand_sizes),
        "lengths_all": lengths_all,
        "lengths_clean": lengths_clean,
        "reshuffle_rounds": dict(sorted(reshuffle_rounds.items())),
        "selection_rates": selection_rates,
        "mean_programmed_per_hand": statistics.mean(chosen_per_plan) if chosen_per_plan else 0.0,
        "overall_selection_rate": (
            sum(chosen_counter.values()) / sum(dealt_counter.values()) if dealt_counter else 0.0
        ),
    }


# ---------------------------------------------------------------------------
# Part 2 -- injection simulation on the real dealer
# ---------------------------------------------------------------------------


def load_deck(repo_root: Path, name: str) -> ModelSODeck:
    data = yaml.safe_load((repo_root / "contracts_data" / "decks" / name).read_text())
    return ModelSODeck.model_validate(data)


def simulate_injection(
    deck: ModelSODeck,
    *,
    quota: int,
    inject_round: int,
    max_round: int,
    seed: int,
) -> tuple[int | None, list[int]]:
    """Simulate one partition's deal cycle with a marker acquired at ``inject_round``.

    Returns ``(first_draw_round, draw_rounds)`` -- the marker goes to the
    discard pile together with round ``inject_round``'s dealt hand (Dominion
    acquisition semantics) and is then tracked through the real dealer.
    """

    dealer = DealerCompute()
    scope0 = ModelSODealerScope(
        match_id=f"drawthrough_sim_{seed}_{inject_round}",
        match_seed=seed,
        tick=0,
        seat="probe",
    )
    state = dealer.open_deck_for_seat(deck=deck, scope=scope0)
    first_draw: int | None = None
    draw_rounds: list[int] = []
    for round_index in range(1, max_round + 1):
        scope = scope0.model_copy(update={"tick": round_index})
        result = dealer.deal_hand_for_seat(state=state, count=quota, scope=scope)
        if MARKER in result.hand:
            draw_rounds.append(round_index)
            if first_draw is None:
                first_draw = round_index
        # Whole-hand discard at end of round (match/card_adapter.py
        # _split_state_for_next_round): played and unplayed cards alike.
        discard = result.state.discard_pile + result.hand
        if round_index == inject_round:
            discard = (*discard, MARKER)
        state = ModelSODeckState(draw_pile=result.state.draw_pile, discard_pile=discard)
    return first_draw, draw_rounds


def run_simulation(
    deck: ModelSODeck,
    *,
    quota: int,
    seeds: int,
    max_inject: int,
    max_round: int,
) -> dict[int, list[tuple[int | None, list[int]]]]:
    results: dict[int, list[tuple[int | None, list[int]]]] = {}
    for inject_round in range(1, max_inject + 1):
        results[inject_round] = [
            simulate_injection(
                deck,
                quota=quota,
                inject_round=inject_round,
                max_round=max_round,
                seed=seed,
            )
            for seed in range(seeds)
        ]
    return results


# ---------------------------------------------------------------------------
# Part 3 -- combine mechanics with the measured match-length distribution
# ---------------------------------------------------------------------------


def combine(
    sim: dict[int, list[tuple[int | None, list[int]]]],
    lengths: list[int],
    selection_probabilities: dict[str, float],
) -> list[dict[str, object]]:
    """P(drawn) / P(played) per injection round against the length distribution.

    Conditioning: an acquisition at phase k can only happen in a match that
    reaches phase k, so each injection round conditions on lengths >= k.
    """

    rows: list[dict[str, object]] = []
    for inject_round, outcomes in sorted(sim.items()):
        eligible = [length for length in lengths if length >= inject_round]
        if not eligible:
            continue
        p_drawn_acc = 0.0
        played_acc = {label: 0.0 for label in selection_probabilities}
        delays: list[int] = []
        for length in eligible:
            drawn = 0
            for _first_draw, draw_rounds in outcomes:
                draws_before_end = [r for r in draw_rounds if r <= length]
                if draws_before_end:
                    drawn += 1
                    delays.append(draws_before_end[0] - inject_round)
                for label, prob in selection_probabilities.items():
                    played_acc[label] += 1.0 - (1.0 - prob) ** len(draws_before_end)
            p_drawn_acc += drawn / len(outcomes)
        n = len(eligible)
        rows.append(
            {
                "inject_round": inject_round,
                "eligible_matches": n,
                "p_drawn": p_drawn_acc / n,
                "p_played": {
                    label: played_acc[label] / (n * len(outcomes))
                    for label in selection_probabilities
                },
                "median_phases_to_first_draw": (statistics.median(delays) if delays else None),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True, help="events.sqlite3 battery ledger")
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--max-inject", type=int, default=15)
    parser.add_argument("--quota", type=int, default=4, help="cards dealt per partition per round")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    facts = extract_ledger_facts(args.ledger)
    lengths_clean: list[int] = list(facts["lengths_clean"])  # type: ignore[arg-type]
    lengths_all: list[int] = list(facts["lengths_all"])  # type: ignore[arg-type]
    max_round = max(lengths_all) if lengths_all else 24

    deck = load_deck(repo_root, "weapon_v1.yaml")
    sim = run_simulation(
        deck,
        quota=args.quota,
        seeds=args.seeds,
        max_inject=args.max_inject,
        max_round=max_round,
    )

    rates = facts["selection_rates"]
    assert isinstance(rates, dict)
    selection_probabilities = {
        "uniform_5_of_8": 5 / 8,
        "measured_mean": float(facts["overall_selection_rate"]),
        "measured_min_card": min(rates.values()) if rates else 0.0,
        "measured_max_card": max(rates.values()) if rates else 1.0,
    }

    report = {
        "ledger": str(args.ledger.name),
        "facts": facts,
        "selection_probabilities": selection_probabilities,
        "per_injection_clean_lengths": combine(sim, lengths_clean, selection_probabilities),
        "per_injection_all_lengths": combine(sim, lengths_all, selection_probabilities),
        "seeds": args.seeds,
    }
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(report, indent=2, default=str))

    print(f"matches={facts['matches']} end_reasons={facts['end_reasons']}")
    print(f"hand_sizes={facts['hand_sizes']}")
    if lengths_clean:
        print(
            "match length (clean terminals): "
            f"n={len(lengths_clean)} median={statistics.median(lengths_clean)} "
            f"mean={statistics.mean(lengths_clean):.1f} "
            f"min={min(lengths_clean)} max={max(lengths_clean)}"
        )
    else:
        print("no clean-terminal matches")
    print(
        "match length (all): "
        f"n={len(lengths_all)} median={statistics.median(lengths_all)} "
        f"mean={statistics.mean(lengths_all):.1f}"
    )
    print(f"observed reshuffle rounds: {facts['reshuffle_rounds']}")
    print(f"mean programmed per 8-card hand: {facts['mean_programmed_per_hand']:.2f}")
    print("per-card P(programmed|dealt):")
    for card_id, rate in sorted(rates.items(), key=lambda item: -item[1]):
        print(f"  {card_id}: {rate:.3f}")
    brackets = {k: round(v, 3) for k, v in selection_probabilities.items()}
    print(f"selection probability brackets: {brackets}")
    header = (
        f"{'k':>3} {'elig':>5} {'P(drawn)':>9} {'med dly':>8} "
        f"{'P(play|uni)':>11} {'P(play|mean)':>12} {'P(play|min)':>11} {'P(play|max)':>11}"
    )
    for label, rows in (
        ("clean-terminal length distribution", report["per_injection_clean_lengths"]),
        ("all-match length distribution", report["per_injection_all_lengths"]),
    ):
        print(f"\nP(drawn)/P(played) by acquisition round -- {label}:")
        print(header)
        assert isinstance(rows, list)
        for row in rows:
            played = row["p_played"]
            print(
                f"{row['inject_round']:>3} {row['eligible_matches']:>5} "
                f"{row['p_drawn']:>9.3f} {row['median_phases_to_first_draw']!s:>8} "
                f"{played['uniform_5_of_8']:>11.3f} {played['measured_mean']:>12.3f} "
                f"{played['measured_min_card']:>11.3f} {played['measured_max_card']:>11.3f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
