# Heat-Drafting Deckbuilder — Decision-Grade Design Review

**Date:** 2026-07-22
**Author:** design lead (hostile review + synthesis)
**Status:** DECISION DOC — docs only, no code, no tickets
**Inputs reviewed:** verified seam map; Design 1 (minimal-blast); Design 2 (full deckbuilder)
**Question:** does Steel Onslaught pivot its core loop to in-match heat-drafting, and if so, how?

---

## TL;DR recommendation

**Do not pivot the core loop yet. Run a gated two-phase probe that tests the *actual* thesis, keep the fixed-deck game as the shipping baseline, and only commit to the full deckbuilder if the probe clears explicit falsifiable gates.**

- **Adopt Design 1's minimal-blast surface and single-buy discipline** as the probe vehicle — but **upgrade it with two of Design 2's superior ideas** and **reject one of Design 2's regressions**:
  - Take Design 2's **%-of-headroom economy framing** (boiler-robust) over Design 1's absolute-number tiers (boiler-fragile — see §3.3).
  - Take Design 2's **"double heat tax" as the anti-dominance *principle*** (powered supply cards must also be hot to *operate*), enforced as a catalog authoring rule.
  - **Reject Design 2's unbounded 0..N buys per round** — it is a legibility regression against the top project risk. Keep Design 1's ≤1 buy/round for the probe.
- **Resolve the tension: drafting COSTS heat.** Both designs picked this; it is correct (§6). Endorsed.
- **Heat-drafting is *conditionally* worth pivoting to** — the viral thesis (watchable divergence) is real and the economic hook is elegant and cheap to test — **but it is not yet worth *building***. Three risks are unproven, one of which *neither design measures* (§2.4).
- **Fixed-deck balance work:** cap it at "shippable, fair baseline + well-characterized card pool," then redirect marginal balance effort into the draft probe. Do **not** run two deep balance-tuning programs in parallel (§4).

---

## 0. Verified ground truth (spot-checked against code this session)

The seam map was re-checked on the load-bearing claims. All confirmed except one economy fact both designs get subtly wrong.

| Claim | Verdict |
|---|---|
| `card.heat_cost` inert — 2 refs only (decl `contracts/card.py:71`, prompt `llm/programming.py:120`) | CONFIRMED (seam map said `:130`; actual `:120` — immaterial) |
| No supply/market/acquire/draft concept anywhere in card domain | CONFIRMED |
| Over-deal permitted by validators (`register_count <= hand_size` required, not `==`) | CONFIRMED — `deck.py:61-65`, `split_deck.py:70-71` |
| Split archetypes: red **berserker** (mv3/wp2), blue **sniper** (mv2/wp3), both hand=register=5, `card_cadence: paced` | CONFIRMED — `contracts_data/overlays/tactical_split_v1_qwen.yaml:44-59` |
| §27 ethos: "not optimized for … purchased dominance"; winner "knows exactly when the boiler can be abused without becoming shrapnel" | CONFIRMED verbatim — `docs/plans/2026-04-30-steel-onslaught-design.md` §27 |
| **Heat thresholds are per-chassis spec-data — there is NO single canonical redline/rupture** | CONFIRMED and consequential (below) |

**The economy fact both designs mishandle.** There are **three** boiler specs with **different** thresholds:

| Boiler | redline | rupture | vent/tick | capacity |
|---|---|---|---|---|
| `compact_v1` | 65 | 80 | 6 | 80 |
| `industrial_bessemer_90` | 80 | 100 | 4 | 120 |
| `volatile_v1` | 60 | 85 | 3 | 100 |

- **Design 1 hard-codes its economy against 80/100** ("canonically redline 80 / rupture 100"). That is the *bessemer* boiler, not a canon. Its worked example ("buy a 25-cost card from heat 55 → heat 80 → crosses redline") is **factually wrong on `compact_v1`, where 80 is *rupture*, not redline** — that same buy would kill the pilot on a compact boiler. Absolute-heat tiers cannot be correct across all three boilers simultaneously.
- **Design 2 anchors to `compact_v1` 65/80 but expresses costs as *% of redline budget*** — which *does* scale per boiler. This is the correct framing and is the single clearest technical advantage of Design 2 over Design 1.

**Balance-premise caveat (applies to BOTH, unverified).** Both designs assume an **archetype ambient-heat asymmetry** — "berserker runs hot, sniper runs cool" (Design 1 leans on this heavily for emergent balance). The current quota split gives the **sniper MORE weapon slots (3) than the berserker (2)**. Weapon fire is a primary heat source. So the *mechanical* asymmetry today does not obviously make the berserker hotter — if anything the slot count cuts the other way. The "berserker runs hot" story is an **authoring intent** (see the berserker persona: "rather risk rupture") **not a mechanically-guaranteed property** of the current split. The emergent-balance argument in both designs rests on this being real; it must be **measured, not assumed**.

---

## 1. What both designs get right (shared substrate)

Neither design is padded on the substrate; both correctly identify the same true seams, and both pick the same position. Credit where due:

1. **`card.heat_cost` is a ready-made, power-neutral hook** — wire it as the acquire price, no new game-data type.
2. **This requires the *first-ever* fold of card state.** Today `MatchStateFold.handle` folds 9 non-card events; card lifecycle events are recorded and replay-validated but never folded. A growing deck needs an event-sourced per-match owned-multiset + supply-depletion state. Both name this as the top determinism risk. Correct.
3. **Conservation invariants must rebase** from static `deck.card_multiset()` to `static ⊕ folded_acquisitions` (`round.py:198-204`, `replay/card_round.py:292-295`). A missed rebase silently breaks replay. Both flag it and both call for a cross-boundary fold-then-reshuffle replay regression test. Correct.
4. **The seeded BLAKE2b RNG already includes composition in its `material`**, so once composition is folded the reshuffle reproduces automatically — determinism is achievable, contingent purely on fold-before-shuffle + pinned causal ordering. Both get this right.
5. **Over-deal (hand > register_count) is a zero-code Stage 0.** Both correctly note it creates a real in-hand selection+discard decision with no engine change.
6. **Costs-heat, not points.** Both pick it; both justify it via the boiler-fold reuse + c11-as-dial + inert-field arguments. Endorsed (§6).

Because the substrate analysis is identical and sound, the decision is **not** "which analysis is right" — it is **"how much surface to commit before the hypothesis is proven,"** plus a few correctness upgrades.

---

## 2. Hostile review

Five questions, both designs, no boosting.

### 2.1 Does it add WATCHABLE depth, or complexity the LLM won't use well?

- **The viral thesis is real.** Deckbuilding *is* the deepest, most divergent, most watchable mechanic on the table. Design 2's "deck-DNA divergence strip" and per-pilot composition drift name the payoff precisely: two decks visibly pulling apart on screen.
- **But watchability depends on a fact neither design establishes** (see §2.4): if the acquired card is rarely *drawn and played* within the match, there is nothing to watch — the divergence is a number in a side panel, not a moment on the board.
- **LLM legibility is the round-3 risk and it is unproven for BOTH.** The draft decision is strictly harder than today's programming decision: it adds a supply pool, archetype gates, owned-deck composition, and a heat-budget-vs-lockout tradeoff. Design 1's **≤1-buy** framing is materially *more* legible than Design 2's **0..N** framing (§2.5). Neither design has evidence the model drafts *well*; both correctly flag it and both propose Stage 0 as the mitigation — but Stage 0 only de-risks *pruning*, not *drafting* (§2.4).

**Verdict:** watchable depth is plausible and is the right bet *if* two unproven things hold (draw-through + legibility). It is not yet demonstrated. Both designs are honest that it is a hypothesis.

### 2.2 Is the heat economy a meaningful tension or a fiddly tax?

- **Costs-heat is a genuine tension, not a tax** — *provided* the acquisition cost is priced in the same units as the penalty it triggers. Design 1's three-consequence chain (c11 register lockout + initiative penalty + rupture margin) and Design 2's double-bind (acquire spike + *permanent* operate-heat floor) both make buying a real tempo/risk decision, not a toll.
- **Design 2's "double heat tax" is the stronger economic idea in either document.** Powered cards cost heat to *acquire* AND are hot to *operate*, so accumulating power permanently raises your steady-state boiler floor → more redline time → self-throttling. This is anti-snowball *by construction*, which is exactly what §27 asks for. **Caveat: it is not a mechanical guarantee — it is a catalog authoring discipline.** If you author a cheap-to-operate powered card, the double-bind evaporates. So it must be an enforced supply-design rule ("power tier ⇒ high operate heat"), not an emergent property.
- **Design 1's economy risks being a *fiddly* tax specifically because of the absolute-number/boiler mismatch (§0).** 15/25/40 against one boiler is a different tension (or a rupture trap) on another. Fiddliness here is a symptom of the wrong units.

**Verdict:** meaningful tension under costs-heat, contingent on (a) %-of-headroom units (Design 2's framing) and (b) the double-tax being *enforced in the catalog* (Design 2's principle, made a rule).

### 2.3 Is it replay-deterministic?

- **Yes, conditionally, for both** — and the condition is identical: acquisitions are events; the fold runs before the shuffle; conservation rebases onto the folded composition; acquire-vs-deal ordering is pinned in the existing single causal chain; pile order stays out of payloads (reshuffle re-derived, never transmitted). The seeded RNG already keys on composition, so the new shuffle reproduces once the same acquisition sequence is folded.
- **The residual risk is engineering discipline, not a fundamental blocker:** a missed conservation rebase or an unfolded acquisition breaks replay *silently*. Both designs correctly demand a fold-then-reshuffle cross-boundary replay regression test as the gate. This is the highest-severity seam and must land *with* the feature, not after.

**Verdict:** determinism is achievable and both designs specify it correctly. It is not the reason to hesitate — it is a solved-in-principle engineering task with one mandatory regression test.

### 2.4 The risk NEITHER design measures: does an acquired card get PLAYED in-match?

This is the sharpest shared gap and it undercuts the entire viral thesis if it fails.

- An acquired card goes to the **discard pile** (correct Dominion semantics — no queue-jump). It only re-enters play when the **draw pile empties and reshuffles**. With a 30-card starting deck dealing 5–7/round, a pilot cycles the deck roughly every **~5–6 rounds**.
- **If matches are shorter than the reshuffle distance, an acquired card is *never drawn* — drafting has zero in-match payoff and the on-screen divergence is invisible.** The whole loop becomes cosmetic.
- Design 2 adds a "dilution horizon" prompt field acknowledging the timing but **neither design quantifies match length vs reshuffle distance**, and **neither treats draw-through as a gating metric.** This is the make-or-break question and it is unmeasured in both.
- **Corollary correction to a shared overclaim:** both say Stage 0 (over-deal) "de-risks the pivot." It de-risks *one half* — in-hand **selection/pruning** legibility. It does **not** test **cross-round deck growth**, draft decisions, or divergence. Over-deal with a *fixed* deck never grows anything. Stage 0 is necessary but **insufficient**; the probe must include a real deck-growth slice (§5 Phase B).

**Design fix this surfaces (resolve before building):** if draw-through is too low, the levers are (a) a **much smaller starting deck** (faster cycling — the deckbuilder-canonical answer), or (b) acquired card to **top of draw** for immediate payoff (jumps the queue, weakens the risk/tempo tension). Neither design picks; the probe must decide empirically.

### 2.5 Is the scope honest?

- **Design 1: honest and genuinely minimal.** §11 accounts the surface accurately (1 contract, 1 event+payload, 1 fold case + 1 state field, 2 invariant rebases, 1 LLM call, 1 UI overlay), all behind the existing opt-in card gate, zero change to the default runner. §9 ("what it does NOT do") is a real scope fence. No padding detected.
- **Design 2: honest that it is large, but the honesty does not shrink the risk.** It correctly self-labels a "core-loop rewrite of the CARD subsystem … the largest single feature in the card subsystem's history" (8 stages + a large new UI). The problem is not dishonesty — it is **committing rewrite-scale surface to an unproven hypothesis.** Stage 0 gates it, but stages 1–8 remain a big up-front bet for a thesis with two unproven legs (§2.1, §2.4).
- **Design 2's unbounded 0..N buys is a scope/legibility regression masquerading as elegance.** "The heat budget is the buy limit" multiplies the model's decision space (which *subset* of affordable piles) exactly where legibility is the top risk — and Design 2 itself concedes "a single strong buy already eats most of the redline budget," which is an argument *for* a 1-buy cap, not against it. Design 1's ≤1/round is the defensible choice for a first proof.

**Verdict:** Design 1's scope is honest and right-sized for a probe. Design 2's scope is honestly *stated* but wrong-*sized* for an unproven hypothesis, and its multi-buy is a legibility regression.

---

## 3. Recommendation: staged, gated, hybrid

### 3.1 Is heat-drafting worth pivoting to AT ALL?

**Worth *probing*: yes. Worth *building* (committing the core-loop pivot): not yet — conditional on the probe.**

The alternative on the table is "fixed-deck game + utility cards." Honest comparison:

- The fixed-deck game is the **known-shippable baseline** and must stand on its own regardless of the pivot. It is not obsolete and is not a fallback to be embarrassed about.
- Heat-drafting's *upside* (divergent, watchable, self-balancing via one currency) is strictly larger and is the stated viral goal — **but its two load-bearing legs (draw-through payoff, LLM draft legibility) are unproven, and its emergent-balance story rests on an archetype asymmetry that may not be mechanically real (§0).**
- The probe to resolve all of this is **cheap** (hours for Phase A, a small vertical slice for Phase B) relative to the payoff. That asymmetry — cheap test, large upside — is what justifies probing rather than dismissing.

So: **do not pivot on faith; probe with kill-gates.** Keep the fixed-deck game shipping.

### 3.2 The recommended vehicle — Design 1 core, two Design 2 upgrades

Build the probe as **Design 1's minimal-blast** (single-buy, acquired-to-discard, fail-closed no-self-rupture, opt-in overlay, each stage independently landable), with these amendments:

1. **Economy in %-of-headroom units, not absolute heat** (adopt Design 2's framing; fixes §0). Price every card as a fraction of `(rupture − current)` or as a per-boiler-scaled cost, so the tier means the same thing on compact/bessemer/volatile.
2. **Enforce the double-tax as a catalog rule** (adopt Design 2's principle): any powered supply card must also carry high *operate* heat. Make it an authoring invariant of the supply catalog, not a hoped-for emergent property. This is the real anti-purchased-dominance mechanism.
3. **Keep ≤1 buy per round** (reject Design 2's 0..N) for the probe — legibility first. Revisit multi-buy only after the model demonstrates good single-buy drafting.
4. **Decide draw-through up front** (§2.4): probe with a *small* starting deck so acquired cards actually cycle in, and measure it as a hard gate before any UI work.

### 3.3 When (if ever) to escalate to Design 2's full deckbuilder

Escalate to the full build — finite shared piles / pile-out denial, deck-DNA UI, optional scrap/thin, richer supply — **only if** the Phase-B battery (§5) clears all gates. Design 2 is the *right target state* if the hypothesis proves out; it is the *wrong first commitment*. Its best ideas (double-tax, %-budget economy, divergence UI, pile-out counterplay) are individually adoptable and several are folded into the probe above.

---

## 4. Interaction with the in-flight fixed-deck balance work

The operator chose to run both in parallel. Concrete guidance on the split:

**What heat-drafting KEEPS (reused wholesale, do not stop):**
- **All card content, categories, and heat-generation values.** The closed card model and its `heat_generated`/`costs.heat` are the substrate the supply draws from.
- **The split archetype identities** (berserker/sniper) — they become the archetype *access gates* on the supply, the primary asymmetry lever.
- **The fixed decks themselves** — they become the **starting decks**. Nothing is thrown away.
- **The measured balance battery / eval + leaderboard harness** — reused *directly* to measure draft balance. This is the biggest reuse: the draft experiment (§5) rides the existing measurement infrastructure.

**What heat-drafting would OBSOLETE (only if it proves out):**
- **Fine-grained per-matchup fixed-deck *balance tuning* as the primary balance surface.** Under drafting, balance is authored in the supply catalog + archetype access, not in the 30-card list.
- **`hand_quota` as the asymmetry lever** — replaced by supply access gates.
- **Per-matchup deck *selection* as the strategic surface** — replaced by in-match drafting.

**How much fixed-deck investment is still worth it:**
- **Invest to "shippable + fair baseline + well-characterized card pool," then stop.** The fixed-deck game must ship on its own merits (it is the baseline product and the pivot's fallback), and its cards must be individually well-understood (heat cost to operate, role, power) because the supply reuses them.
- **Do NOT pursue a deep, indefinite per-matchup fixed-deck balance-tuning program in parallel with the draft probe.** That is precisely the surface the pivot intends to replace; polishing it beyond "fair enough to ship" is effort you plan to discard.
- **Rule of thumb:** any fixed-deck balance work that *also* improves card characterization (heat values, roles, power tiers) is dual-use — keep it. Any work that only tunes a *specific 30-card matchup* to a fine equilibrium is single-use and should be capped at "shippable."

Net: one deep balance program (measured battery), pointed first at "ship the fixed-deck baseline + characterize cards," then re-pointed at the draft probe. Not two.

---

## 5. Smallest experiment that proves/disproves this (the deckbuilding "measured balance battery")

Two phases with kill-gates. Phase A is hours and zero-code; Phase B is a small vertical slice. **Do not build any UI, multi-buy, or full supply until Phase B clears.**

### Phase A — "Can the model prune?" (zero code, hours)

Ship the **over-deal overlay** on the existing fixed split-deck (deal 7, program 5). Run the existing eval battery. This uses only validators that already permit it.

**Gates (all must pass to proceed):**
- **A1 Legality:** over-dealt plans are legal (`chosen ⊆ hand`) at ~100%.
- **A2 Non-random pruning:** the model discards lower-priority cards at a rate **> chance** (measurable — card priorities are known). If discards are random, the model cannot select, and it certainly cannot draft.
- **A3 No coherence regression:** win-rate/behavior does not degrade vs the hand=register baseline.

*Fail A ⇒ stop. The legibility floor for any deck decision is absent; fix prompt legibility or abandon the pivot for hours of cost.*

**Explicitly: passing A is necessary but NOT sufficient — it tests pruning, not deck growth.** Proceed to B.

### Phase B — "Does drafting produce visible, skillful, non-dominant divergence *with in-match payoff*?" (small slice)

Minimal vertical slice, logs only, **no UI**: ONE supply pile of ~4–6 cards; single-buy/round; costs-heat in %-of-headroom units; event-sourced `CARD_ACQUIRED` + fold + composition-derived shuffle; the three prompt fields (available supply, owned-deck composition, heat headroom + projected lock_depth); **a deliberately small starting deck** so acquisitions cycle in. Run a measured draft battery (reuse the eval/leaderboard harness) with five **falsifiable** metrics:

1. **Draw-through rate (make-or-break — neither design measures this).** Fraction of acquired cards actually **drawn and played** before match end. **Gate: ≥ ~50%.** Below that, drafting has no in-match payoff (reshuffle/match-length mismatch) — shrink the starting deck or move acquisitions closer to draw, and re-measure *before anything else*.
2. **Draft legibility / decision quality.** Compare win rate of **model-drafted vs random-drafted vs no-draft** decks. **Gate: model-draft > random-draft** (the model must add value over a coin-flip buyer). If not, the model isn't drafting skillfully — round-3 legibility fail.
3. **Divergence.** Composition distance between the two pilots' decks at match end, across N matches. **Gate: meaningfully > 0** (near-zero = the watchable payoff isn't materializing).
4. **Anti-purchased-dominance.** Correlation between total heat spent drafting and win rate. **Gate: NOT monotonically increasing** — want a flat or inverted-U (over-drafters self-destruct via lockout/rupture). A monotonic "more buying ⇒ more winning" means purchased dominance leaked in and the double-tax/lockout isn't throttling. This is the §27 test, made falsifiable.
5. **Determinism.** Replay a drafted match; assert identical composition + register resolution + heat trace. **Binary gate.**

**Escalate to Design 2's full build only if:** draw-through ≥ gate, model-draft > random-draft, divergence > 0, buy-vs-win non-monotonic, and replay identical. **Any gate fails ⇒ iterate the slice or abandon — do not build the UI/multi-buy/full-rewrite on an unproven leg.**

This is the deckbuilding analog of the measured balance battery: cheap slice, falsifiable metrics, kill-gates before the expensive surface — and it is the only path that tests the *actual* thesis rather than the pruning proxy.

---

## 6. Resolving the heat-cost-vs-heat-points tension

**Recommendation: drafting COSTS heat.** Endorse the operator lean and both designs. Justified on code + ethos, not preference:

1. **Minimal new surface, maximal coupling.** Costs-heat is one `CARD_ACQUIRED` case on the existing boiler fold, reusing the `WEAPON_FIRED` rupture-cap path — and c11 lockout/rupture/initiative become the risk dial for free. The points model ("combat heat → draft points spent at vent") needs a **new accumulator field on runtime state, a vent-station concept, and a second spend path** — net-new state + events — and reintroduces the exact two-currency split the operator wants gone.
2. **One ready-made field.** `card.heat_cost` already exists and is inert (`card.py:71`). Costs-heat wires it directly; a points economy leaves it unused or duplicates it.
3. **Ethos alignment (§27).** Costs-heat makes acquisition *boiler abuse-to-build*: buying power raises rupture risk and can lock your own registers, so drafting is a tempo/risk decision, never raw power-buying. Points decouple buying from risk and drift toward the purchased-dominance §27 forbids.

**One honest caveat on costs-heat** (not a reason to switch): because acquisition and combat compete for the same headroom, **drafting will cluster in cool moments / early rounds** and be impossible mid-brawl. That is *intended* — it is the tempo dial — but it means the draft cadence is uneven, and the probe should confirm the model still finds meaningful draft windows rather than being permanently heat-starved. A points economy would smooth this out at the cost of the unified-currency tension; that trade is not worth it.

---

## 7. Decision summary

| Question | Answer |
|---|---|
| Pivot the core loop to heat-drafting now? | **No.** Probe first with kill-gates. |
| Worth probing at all? | **Yes** — cheap test, large viral upside, elegant one-currency hook. |
| Which design? | **Design 1 core** (minimal, single-buy, opt-in) **+ Design 2's %-budget economy + double-tax principle**; **reject Design 2's 0..N multi-buy and its full-rewrite-first scope**. |
| Costs-heat or points? | **Costs-heat.** One currency, reuses boiler fold, c11 becomes the dial, inert field wires directly. |
| Replay-deterministic? | **Yes, conditionally** — fold-before-shuffle + rebased conservation + pinned ordering + a mandatory fold-then-reshuffle replay regression test. |
| Respects "not purchased dominance"? | **Yes if the double-tax is enforced as a catalog rule** (powered ⇒ hot to operate); redline/lockout alone is weaker. |
| Biggest unmeasured risk? | **Draw-through** — does an acquired card get played in-match at all? Neither design measures it; it is the Phase-B make-or-break gate. |
| Fixed-deck balance work? | Cap at "shippable baseline + card characterization," then redirect to the draft probe. One deep balance program, not two. Battery + cards + archetypes + starting decks are all reused. |

**Bottom line:** heat-drafting is the right *ambition* and costs-heat is the right *mechanism*, but it is an unproven hypothesis with a make-or-break metric (draw-through) that neither source design measures. Buy the option cheaply — Phase A (hours) then a Phase-B vertical slice with five falsifiable gates — and let the numbers, not the appeal of the idea, decide whether to commit the core-loop pivot.
