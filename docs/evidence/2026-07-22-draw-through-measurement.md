# Draw-Through Measurement — the Deckbuilder Kill-Gate, Measured

**Date:** 2026-07-22
**Status:** MEASURED — answers the make-or-break question flagged as unmeasured in
`docs/design/2026-07-22-heat-drafting-deckbuilder-design.md` §2.4 / §5 Phase B metric 1.
**Question:** if a card is acquired MID-MATCH (as heat-drafting would do, Dominion
semantics: acquired → discard pile → re-enters play at the next reshuffle), what is the
probability it is (a) drawn into a hand and (b) actually programmed before the match
reaches a terminal — under the CURRENT post-#117 mechanics (split decks, deal 8 =
4 movement + 4 weapon, program 5)?
**Kill-gate under test:** draw-through ≥ ~50% (design doc §5, Phase B metric 1).

**Verdict: CONDITIONAL.** Aggregate draw-through under current deck geometry is
**P(drawn) ≈ 0.62, P(played) ≈ 0.45** — *below* the ≥ ~50% played gate — but the failure
is entirely concentrated in mid/late-cycle acquisitions. A buy in phases 1–5 (before the
first reshuffle) clears the gate at **P(played) ≈ 0.70**; a buy in phases 6–10 fails at
≈ 0.36–0.43; phases 11+ collapse to ≈ 0.11–0.30. The design's own proposed lever — a
deliberately small starting deck — is quantitatively confirmed to rescue the gate
(halved pile: P(played) ≥ ~0.6 through phase 9). Details and levers in §5.

---

## 1. Method (honest labeling)

Preference order from the measurement brief: (1) recorded evidence, (2) deterministic
simulation on the actual engine code, (3) live battery. **Used: 1 + 2 combined.**
No new live battery was run.

- **Recorded evidence:** the `tactical_split_overdeal_v1_qwen` battery event ledger
  (`.onex_state/steel_onslaught/tactical_split_overdeal_v1_qwen/events.sqlite3`,
  recorded 2026-07-22 by the real runtime in an over-deal worktree battery) — 48 matches
  of the ACTUAL post-#117 mechanics: `hand_size=8`, `register_count=5` in **100 %** of
  1,162 `hand_dealt` events, split decks, Qwen3.6-35B pilots both seats. Extracted:
  match-length distribution, terminal reasons, observed reshuffle cadence, and empirical
  per-card P(programmed | dealt).
- **Deterministic simulation:** `scripts/measure_draw_through.py` (committed with this
  doc) drives the **actual engine dealer** — `steel_onslaught.cards.dealer.DealerCompute`,
  the same BLAKE2-seeded Fisher-Yates deal/reshuffle code the runtime executes (imported,
  not re-implemented) — over the real committed deck composition
  (`contracts_data/decks/weapon_v1.yaml`, 20 cards) with the over-deal quota
  (4/partition/phase) and the runtime's whole-hand discard rule
  (`match/card_adapter.py::_split_state_for_next_round`: played AND unplayed cards go to
  the partition discard pile every phase). A marker card is injected into the discard
  pile at phase k (k = 1..15), 1,000 seeds per k, and tracked to first deal.

Reproduce: `uv run python scripts/measure_draw_through.py --ledger <events.sqlite3>`.

### Acquisition semantics matched to the design

The design doc (§2.4) fixes Dominion semantics: an acquired card goes to the **discard
pile** and re-enters play only when the draw pile empties and reshuffles. The sim
injects the marker into the discard pile together with phase k's discarded hand —
i.e. "bought during phase k." One marker copy; single-partition sim (movement and
weapon partitions are mechanically identical: 20 cards, 4 dealt/phase, independent
piles and RNG scopes, so the acquiring partition does not matter).

---

## 2. Measured facts (recorded ledger, no modeling)

| Fact | Value |
|---|---|
| Matches | 48 started, 47 terminal events |
| Terminal reasons | 32 `last_mech_standing`, 3 `draw_max_ticks`, 11 `provider_semantic_failure`, 1 `aborted` |
| Hand shape | `hand_size=8`, `register_count=5` in 1,162/1,162 hands |
| Match length, clean terminals (n=35) | **median 13**, mean 13.8, min 7, max 24 programming phases |
| Match length, all matches (n=48) | median 12.5, mean 12.1 |
| Reshuffle cadence | reshuffles at phases **6, 11, 16, 21** in **every** eligible seat-partition hand (172/124/40/16 observations; zero at any other phase) → an exact **5-phase cycle** per 20-card partition |
| Mean cards programmed per 8-card hand | 5.00 |

Empirical per-card **P(programmed | dealt)** — real pilot selection behaviour on
over-dealt hands (multiset-clamped against heat-locked carry-forward):

| Card | P(programmed \| dealt) |
|---|---|
| card.attack.fire_primary | 0.791 |
| card.attack.fire_secondary | 0.748 |
| card.special.mode_assault | 0.721 |
| card.movement.flank_left | 0.664 |
| card.movement.advance | 0.633 |
| card.special.mode_evasion | 0.561 |
| card.movement.flank_right | 0.525 |
| card.movement.reposition | 0.481 |
| card.vent.emergency_vent | 0.288 |
| **mean over all dealt cards** | **0.625** (= 5/8 exactly) |

Two structural facts fall out of the ledger + code before any simulation:

1. **The whole dealt hand is discarded every phase** (unplayed over-dealt cards
   included), so each 20-card partition cycles in exactly 5 phases. The design doc's
   estimate ("~5–6 rounds" for a 30-card deck at 5–7/round) matches: actual is 5.
2. **A median match sees only 2 reshuffles** (phases 6 and 11). A discard-pile
   acquisition needs one reshuffle to become drawable — so the reachable window is
   narrow by construction.

---

## 3. Simulation results — P(drawn), P(played) by acquisition phase

Real dealer, 1,000 seeds/phase, combined with the **clean-terminal** match-length
distribution (n=35; provider-failure truncations excluded — those are being fixed in
separate lanes and understate true match length). Conditioning: a buy at phase k can
only occur in a match that reaches phase k (L ≥ k).

P(played) = 1 − Π(1 − p_sel) over the marker's dealt appearances before terminal, with
p_sel bracketed: **uniform = 5/8** (a new card the model is indifferent to), and the
measured per-card extremes **0.288 (min, vent-like)** / **0.791 (max, attack-like)**.

| Buy phase k | P(drawn) | median phases→first draw | P(played) uniform | P(played) min-card | P(played) max-card |
|---|---|---|---|---|---|
| 1 | 0.928 | 7 | 0.700 | 0.382 | 0.815 |
| 2 | 0.924 | 7 | 0.693 | 0.377 | 0.809 |
| 3 | 0.923 | 6 | 0.687 | 0.372 | 0.805 |
| 4 | 0.929 | 4 | 0.700 | 0.382 | 0.815 |
| 5 | 0.927 | 3 | 0.698 | 0.381 | 0.813 |
| 6 | 0.520 | 7 | 0.355 | 0.178 | 0.432 |
| 7 | 0.534 | 6 | 0.363 | 0.182 | 0.442 |
| 8 | 0.537 | 5 | 0.367 | 0.185 | 0.446 |
| 9 | 0.559 | 4 | 0.382 | 0.193 | 0.464 |
| 10 | 0.631 | 3 | 0.431 | 0.218 | 0.524 |
| 11 | 0.160 | 7 | 0.114 | 0.058 | 0.137 |
| 12 | 0.169 | 6 | 0.120 | 0.061 | 0.144 |
| 13 | 0.210 | 5 | 0.150 | 0.076 | 0.179 |
| 14 | 0.289 | 4 | 0.205 | 0.104 | 0.246 |
| 15 | 0.419 | 3 | 0.297 | 0.151 | 0.356 |

**Aggregate over one uniform buy opportunity per phase** (446 of 484 phase-opportunities
covered at k ≤ 15): **P(drawn) = 0.62; P(played) = 0.45** uniform (0.24 min-card / 0.53
max-card). Using the all-match length distribution instead shifts these down slightly
(P(played) ≈ 0.42 uniform).

The sawtooth is the 5-phase reshuffle cycle: a buy lands in the discard pile and waits
for the next reshuffle boundary (phase 6, 11, 16, 21), then sits uniformly in a 21-card
shuffled pile dealt at 4/phase. Median delay to first draw is therefore 3–8 phases —
against a median match of only 13 phases.

---

## 4. Gate read: CONDITIONAL

The gate as written — "fraction of acquired cards actually drawn and played before match
end ≥ ~50%" — **fails in aggregate under current geometry** (0.45 uniform; only the
max-card bracket scrapes 0.53). It is NOT a flat fail:

- **First-cycle buys (phases 1–5) clear the gate**: P(drawn) ≈ 0.93, P(played) ≈ 0.70.
- **Everything after the first reshuffle fails**: phases 6–10 ≈ 0.36–0.43; phases 11+
  ≈ 0.11–0.30. A card bought in the second half of a median match is essentially
  cosmetic — exactly the §2.4 failure mode ("a number in a side panel, not a moment on
  the board").

One honest mitigation of the read: under costs-heat, the design itself predicts buys
cluster in cool early phases (§6 caveat). If live draft timing concentrates in phases
1–5, the effective draw-through of real matches would sit near 0.70 and pass. But the
gate must hold for mid-match drafting — the watchable-divergence thesis needs buys to
keep mattering as the match develops — so the current geometry does not clear it.

---

## 5. What CONDITIONAL implies for the design (levers, quantified)

The design doc §2.4 names the levers; here is what each is now *measured/modeled* to buy:

1. **Small starting deck (design's preferred, deckbuilder-canonical lever) — RESCUES
   THE GATE.** Modeled with a halved 10-card weapon pile (hypothetical composition,
   same real dealer, 1,000 seeds, clean lengths): P(drawn) = 1.00 through phase 4 and
   ≥ 0.78 through phase 10; P(played, uniform) ≈ 0.96/0.93/0.85/0.71/0.60/0.68 at
   phases 1–10, staying ≥ ~0.6 through phase 9 and ≈ 0.3–0.44 only in the last cycle.
   Median phases-to-first-draw drops from 3–8 to 2–3. **Phase B must ship with a
   deliberately small starting deck** (~10–12/partition), as §3.2.4 already leans —
   this measurement converts that lean into a requirement.
2. **Acquired-to-top-of-draw** (queue-jump): P(drawn) ≈ 1.0 for k ≤ 10 (0.69–0.97 near
   terminal), P(played) ≈ p_sel ≈ 0.55–0.63 per the single guaranteed next-phase draw.
   Clears the gate mechanically but weakens the risk/tempo tension the design wants
   (§2.4 explicitly flags this trade); use only if small-deck alone proves insufficient.
3. **Acquired-directly-to-hand**: P(drawn) = 1 by construction; the draft becomes an
   immediate-play decision. Strongest payoff visibility, weakest deck-building identity.
   Not needed if lever 1 holds.
4. **Do nothing (current 20-card partitions)**: mid-match drafting is cosmetic. Rejected
   by the numbers above.

Recommendation for the Phase-B slice: lever 1 (small starting deck) as the default,
lever 2 held in reserve as the fallback dial, and re-measure draw-through with this
same script + the Phase-B battery ledger before any UI work — the gate is now cheap to
re-check on every geometry change.

---

## 6. Measured fact vs modeling assumption (explicit separation)

**Measured (recorded ledger / committed code):** match-length distribution; terminal
reasons; hand shape 8/5; exact 5-phase reshuffle cadence (phases 6/11/16/21, 100 % of
eligible hands); whole-hand discard rule (code-confirmed in
`match/card_adapter.py::_split_state_for_next_round`); per-card P(programmed | dealt);
mean 5.00 programmed per hand; 20-card partition compositions.

**Modeled (assumptions, labeled):**
- The marker card is **inert**: it does not change match length, heat, pilot behaviour,
  or win probability, and exactly one copy is acquired. Real drafted cards are chosen
  *because* they matter, which could shift both selection probability and match length.
- Dominion acquisition semantics (buy → discard pile at end of the buy phase), per the
  design doc's own §2.4 framing. Buy timing is treated as uniform across phases for the
  aggregate number; real costs-heat drafting will skew early (§6 of the design doc).
- Selection probability of a *new* card is unknown; bracketed by uniform 5/8 and the
  measured per-card extremes (0.288–0.791), each dealt appearance treated as an
  independent Bernoulli trial.
- Match lengths come from one battery (Qwen3.6-35B both seats, over-deal overlay,
  n=35 clean). Other pilot models may fight longer or shorter matches.
- The small-deck variant composition (10 cards) is hypothetical — no such deck is
  committed; its numbers are directional, to be confirmed by the Phase-B battery.
- Simulation seeds are synthetic match seeds; the dealer's per-seed determinism is the
  runtime's own (BLAKE2-scoped RNG), so the curves are exact for the mechanics and
  Monte-Carlo-approximate (n=1,000/phase, ±~1.5 pp) over seed space.

---

## 7. Data provenance

- Ledger: `tactical_split_overdeal_v1_qwen` battery, `events.sqlite3` (append-only
  canonical event schema), recorded 2026-07-22 against post-#117 code; 48 matches,
  1,162 `hand_dealt` / `plan_committed` / `cards_discarded` triples, 47 `match_ended`.
  Battery ledgers live under gitignored `.onex_state/` trees and are not committed;
  the extraction is re-runnable against any battery ledger via
  `scripts/measure_draw_through.py --ledger`.
- Engine code measured: `src/steel_onslaught/cards/dealer.py` (deal/reshuffle),
  `src/steel_onslaught/match/card_adapter.py` (whole-hand discard threading),
  `contracts_data/decks/{movement_v1,weapon_v1}.yaml` (20-card partitions),
  `contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml` (deal-8/program-5
  quotas), at main `8f9f0e7`.
