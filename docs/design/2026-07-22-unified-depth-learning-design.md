# Unified Depth + Learning Design

**Date:** 2026-07-22
**Status:** DESIGN — docs only, no code. P1 from the 2026-07-22 session handoff. Gated on operator review.
**Rev 2 (2026-07-22, post-build reconciliation):** Phase 1 learning spine SHIPPED (#123 @ `7dc970e`); D-GATE-0 MEASURED (#122 @ `830dc0b`, CONDITIONAL); Phase 0 preconditions DONE (#119/#120/#121/#124); reviewed and amended by the operator gate this session. Rev 2 facts are OBSERVED, cited to PR numbers + merge SHAs.
**Scope:** ONE design covering the depth decision space (over-deal → utility cards → drafting → objectives/keywords/arena) AND the live learning loop wired over that space. Deliberately not two documents: the learning loop's efficacy rides on the depth decision space, so their seams are designed together.
**Inputs:** `docs/design/2026-07-22-heat-drafting-deckbuilder-design.md` and `docs/plans/2026-07-21-steel-onslaught-finish-plan.md` (both currently ride the `docs/so-finish-plan` branch, PR #108 — not yet on `main`); the 2026-07-22 session handoff (same branch); PR #117 (merged); source readback of the learning modules cited below.

**Evidence convention.** Every load-bearing claim is labeled either **OBSERVED** (cited to `file:line` read this session, or to the handoff/plan) or **DESIGN** (a decision this document proposes, not yet true in code). Anything unverifiable is flagged as such. No claim below relies on a sweep or a self-report.

---

## 0. Ground truth (all OBSERVED, cited)

1. **The over-deal foundation is MERGED on `main`.** PR #117 (`feat(cards): over-deal the hand so pilots select which cards to program`) merged as `2e6a31e` (read live via `gh pr view 117` this session). It consists of: a new overlay `contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml` (deal 8 = 4 movement + 4 weapon, program 5, deliberately balanced 4/4 so identity emerges from SELECTION, not the deal), an over-deal prompt block plus an explicit `selection` observation field (`hand_size` / `program_count` / `discard_unprogrammed` / `over_dealt`) in `src/steel_onslaught/llm/programming.py`, and `tests/match/test_overdeal_card_selection.py`. Zero engine changes — `hand_quota` was already the declarative deal count, and the validators already permit `register_count <= hand_size` (`src/steel_onslaught/contracts/split_deck.py:70-71`, `src/steel_onslaught/contracts/deck.py:61-65`).
2. **The over-deal thesis is empirically validated** (handoff §3, measured on live Qwen): on the same balanced 4/4 hand, brawler keeps ADVANCE 0.94 vs sniper 0.30, and dumps dead VENT cards at 0.11 vs random 0.62. Selection is intentful and archetype-divergent. This is the Phase-A gate of the heat-drafting design, cleared.
3. **The balance stop is final** (finish plan, `## 2026-07-21 session update`): four measured live-Qwen single-lever rounds on the 60-vs-160 fixed-deck duel — r1 heat-lockout, r2 ×5.5 brawler damage, r3 moves-scaled evasion sweep, r4/r4b sniper range-band + carbine throttle — moved brawler median DMG-OUT ~2 → ~50 and survival ~4×, but win-rate pooled ~5% (1/43). Pre-agreed decision triggered: **no fifth single-lever round.** Balance re-emerges from depth or it does not; the fixed-deck knob program is closed.
4. **The live learning path was dead code — three specific blockers, ALL CLOSED by #123 @ `7dc970e` (OBSERVED, Rev 2).** Historical diagnosis preserved below (`learning-adaptation-01/02/03` in the finish-plan audit register):
   - **01 — never instantiated, never admitted. CLOSED by #123 (`7dc970e`).** `LiveLearningCoordinator` is defined at `src/steel_onslaught/learning/live.py:65`; `begin_match` at `live.py:82` had **no production caller**. The production composition constructed the after-match handler WITHOUT a promotion port: `src/steel_onslaught/match/composition.py:2066-2069` passed only `ledger=` and `artifacts=`, so `AfterMatchLearningHandler.promotion` stayed at its `None` default (`src/steel_onslaught/learning/after_match.py:42`) and the `if self.promotion is not None:` branch at `after_match.py:61-62` never executed. **CORRECTION (Rev 2):** the claim "no concrete `LiveLearningEvaluator` exists anywhere — zero implementations in `src/` or `tests/`" was **refuted** — `tests/learning/test_live.py:88` (`_Evaluator`) and `:188` (`_FlakyEvaluator`) implemented the live protocol all along; the name-grep was blind to Protocol structural typing. `src/` now has `WinDamageDifferentialEvaluator` (#123). (`learning/duel_evaluator.py` and `learning/fake_evaluator.py` do implement the *offline* evaluator protocol with a different signature: `evaluate(candidate_params, parent_params, seeds)` — that part stands.)
   - **02 — no promotion event. CLOSED by #123 (`7dc970e`).** `SOEventType` (`src/steel_onslaught/events/envelope.py:15-62`) had no `POLICY_PROMOTED` member. Where promotion happened at all it was the in-memory mutation `self.current_policy = next_policy` (`live.py:162`) plus YAML lineage files — not durable, not replayable, ordering recorded nowhere.
   - **03 — the admission↔terminal seam was broken as-typed. CLOSED by #123 (`7dc970e`).** `LiveLearningPromotionPort` (`live.py:37-42`) exposed ONLY `handle_after_match`, but the concrete coordinator raises `"match ... must be admitted before terminal evidence"` for any match not admitted via `begin_match` (`live.py:104-109`). Wiring the coordinator into `AfterMatchLearningHandler.promotion` as-was would therefore have **raised on every scored match**.
5. **The offline evidence path works.** `AfterMatchLearningHandler.handle` (`after_match.py:46-63`) fires on `MATCH_SCORED`, reprojects the full ledger stream through `project_match_learning_evidence` (`src/steel_onslaught/learning/post_match.py:36`), and persists a strict evidence artifact. The projector is **fail-closed on event vocabulary**: an event type absent from its payload map raises `"no payload contract registered"` (`post_match.py:64-65` — Rev 2 corrects the earlier off-by-two `66-67` citation). This is a live trap for any new event type — see §4.2.
6. **`ModelSOCard.heat_cost` exists and is inert**: declared at `src/steel_onslaught/contracts/card.py:71`; its only other reference is the prompt serializer (`src/steel_onslaught/llm/programming.py`, ~line 120). Heat-as-card-currency was designed in and never wired (heat-drafting design §0, re-confirmed by grep this session).
7. **Card state has never been folded.** The canonical match fold handles non-card events; the card lifecycle members (`HAND_DEALT`, `PLAN_COMMITTED`, `REGISTER_RESOLVED`, `CARDS_DISCARDED`, `envelope.py:59-62`) are recorded and replay-validated but are fold no-ops (comment at `envelope.py:56-58`; heat-drafting design §1.2). Drafting requires the first-ever fold of card composition state.
8. **Terrain premise, corrected** (finish plan): obstacles DO block movement and weapon LOS today (88% of shots blocked). The defect is layout quality — 336 symmetric-scatter cells that help nobody. The fix is asymmetric cover in a NEW versioned arena, never an edit to `foundry_60` (old replays must stay valid).
9. **Residual abort: CLOSED (OBSERVED, Rev 2).** Historical diagnosis: with the sniper JSON fix proven on #116, a RED brawler `invalid_action_parameters` abort was the dominant abort class (handoff §3); this design treated it as a precondition for clean batteries, not a deliverable. Closure: #120 (`8f9f0e7`) root-caused it — doctrine overrode the dealt-hand multiset; #121 (`f1fd18e`) made the protection seat-generic (all 4 personas + a dynamic registry matrix + a synthetic adversarial persona); #124 (`fd05bb9`) battery: **0 aborts of any class in 840/840 completions, 30/30 real gameplay terminals** (vs the 33.9% non-gameplay baseline). The clean-battery precondition for every gate in §5 is met.

---

## 1. Thesis: why one design

**DESIGN.** Depth and learning are the same bet expressed at two altitudes:

- **Depth** gives the pilots a real decision space. Over-deal proved (OBSERVED, §0.2) that selection over a wider-than-needed hand produces intentful, archetype-divergent play. Drafting, utility cards, objectives, and keywords each widen that space further.
- **Learning** only means something over a decision space where policies can differ. A learning loop over the pre-#117 game (deal == program, single lever = deck numbers) can only learn deck knobs — exactly the surface the balance stop closed. A learning loop over the depth space learns *selection and drafting behavior* — measurable with the same instruments that validated #117.
- **The pairing is the platform-proof thesis (RSD).** Every match is already an event-sourced, deterministically replayable ledger. If promotion itself becomes an event folded from that ledger (§4.2), then a promoted policy is **auditable**: "here is the policy that got promoted; replay the match that promoted it and the evaluator decision that gated it." That property — policy evolution as a hash-linked, replayable event chain rather than an in-memory flag — is the demonstrable claim, and it only exists if the learning seams are designed against the event vocabulary now, not bolted on after the depth events ship.

Designing them separately would fix the event vocabulary twice and match the seams never. One document, one seam table (§6).

---

## 2. Standing constraint: balance re-emerges from depth, not knobs

**OBSERVED** (§0.3) and restated here as a binding constraint on every phase below:

- No phase may open a fifth single-lever tuning round on the 60-vs-160 fixed-deck duel. The stop decision is final.
- PR #116's balance numbers (×5.5 damage, evasion sweep, range-band, carbine throttle) are measured evidence, not merge candidates; only the standalone sniper-JSON robustness fix is being split out (separate lane, in flight).
- Brawler win-rate is a **reported observable** in every battery below (winner-side distribution, per finish-plan action 7), never a per-phase tuning target. The depth hypothesis is precisely that this number moves without anyone tuning it directly. If it does not move by Phase 4, that is a finding, not a license to reopen the knob program.

---

## 3. The depth decision space

Ordered by dependency, not preference. Each increment names its go/no-go gate in §5.

### 3.1 Foundation — over-deal (DONE, merged)

**OBSERVED:** merged `2e6a31e` (§0.1). Everything below composes with the over-deal overlay as the baseline: identity from SELECTION, deal stays balanced, `hand_quota` remains the declarative deal-shape lever.

### 3.2 Utility cards — chaff / flares / smoke as active counterplay

**DESIGN.** Three utility cards enter the deal so pilots can spend a register on counterplay instead of movement/attack:

- **smoke** — LOS-blocking cloud, area + duration; degrades the mortar/harpoon aimed core (the actual killer per r4b, OBSERVED §0.3) without touching its numbers.
- **chaff** — targeting debuff aura on the deploying mech; counterplay to aimed fire.
- **flares** — decoy that breaks/spoils a lock for N ticks; counterplay to the harpoon.

Mechanically these are the first cards whose resolution *changes the battlefield*, so they need engine handlers and folded state (seams in §6, Phase 2). They are also the natural first *draftable* goods for Phase 3 and the first policy-visible choice class for learning ("does the brawler learn to smoke before closing?").

Deal shape: extend the split-deck quota with a third pile rather than diluting movement/weapon piles — `hand_quota.utility` (field-by-field in §6). Over-deal stays the mechanism: utility cards compete for the same 5 registers.

### 3.3 Heat-drafting — probe, gated on DRAW-THROUGH

**DESIGN**, governed by the heat-drafting decision doc, which this design adopts wholesale: Design-1 minimal-blast vehicle, ≤1 buy/round, costs-heat in %-of-headroom units (three boilers with different redlines — `compact_v1` 65/80, `industrial_bessemer_90` 80/100, `volatile_v1` 60/85 — so absolute-heat tiers are wrong by construction), double-tax as a catalog authoring rule, acquired-to-discard.

**The make-or-break unmeasured risk is DRAW-THROUGH** (heat design §2.4): an acquired card only re-enters play when the draw pile empties and reshuffles; if matches are shorter than the reshuffle distance, drafting is cosmetic. Neither source design measured it. Therefore: **D-GATE-0 (§5) runs before any drafting code** — a zero-code measurement over existing ledgers (`HAND_DEALT` events per round vs match `duration_ticks`) of how many deck cycles a real match contains, and hence what starting-deck size makes ≥~50% draw-through plausible. Build nothing until that number exists.

`heat_cost` (inert today, §0.6) is the acquire price. Wiring it is the intended activation of a field that was designed for exactly this.

### 3.4 Asymmetric matchups + objective-based victory

**DESIGN.** The 60-vs-160 duel is not a fair fight and is no longer required to be one (§2). Instead:

- **Objective-based victory:** contested objective cells award VP per controlled round; a match ends when a side reaches the VP threshold. The tick cap (1000) becomes a **failsafe only** — a match ending on the clock is an anomaly to report, not a normal terminal. This gives the brawler a *reason and a way to close* that is not "out-damage a 160 HP ironclad": board control converts mobility into points.
- **Asymmetric matchups become legitimate:** with VP victory, archetypes stop needing symmetric kill-power. The sniper defends zones at range; the brawler contests them up close. Balance is then a property of the objective layout + card pool, which is exactly where the depth program tunes.

**OBSERVED (Rev 2):** BLUE won 30/30 terminals on merged-main over-deal balance (#124 @ `fd05bb9`, n=30 battery). That is the strongest measured motivation for objective-based victory yet recorded, and it feeds the §6 sequencing-note option to pull Phase 4 ahead.

### 3.5 Heavy / Assault keywords (Phase 2.5, 40K-derived)

**DESIGN.** Two closed card/loadout keywords modifying resolution:

- **Heavy** — full effect only when the firer did not move this round (mortar-class identity: devastating when planted, degraded on the move).
- **Assault** — may fire after advancing without penalty (brawler-class identity: closing is not self-taxing).

These are asymmetry levers expressed as *rules*, not stat knobs — they change what a policy can learn ("plant vs relocate" becomes a real decision). Per the repo's operating rule, they must be allowlisted resolution handlers selected by a typed overlay, with keyword handler IDs visible in replay (finish-plan finish-line table requires exactly this).

### 3.6 Asymmetric cover — NEW versioned arena

**DESIGN.** A new arena contract (working id `foundry_60_asym_v1`), never an edit to `foundry_60` (**OBSERVED** constraint §0.8: old replays must stay valid; blocking already works, layout is the defect). Layout intent: cover corridors that favor approach on one axis and sightlines on another, co-designed with the objective cells of §3.4 (cover and objectives are one layout problem). Ships with geometry/LOS fixtures like the existing arena.

---

## 4. The learning loop, wired over that space

### 4.1 What closes each blocker

**Rev 2:** all three closures below shipped in #123 @ `7dc970e` substantially as specified — deviations and dispositions in §4.6.

| Blocker | Closure (DESIGN) |
|---|---|
| `learning-adaptation-01` (dead code) | Composition instantiates one `LiveLearningCoordinator` per live stack, seeded from a genesis policy; a first concrete `LiveLearningEvaluator` ships (§4.4); the coordinator is passed as `promotion=` at `match/composition.py:2066-2069`. |
| `learning-adaptation-02` (no event) | `POLICY_PROMOTED` member added to `SOEventType`; promotion appends a payload-validated event to the promoting match's ledger stream (§4.2). Promotion state is thereafter re-derivable from events + lineage chain, not process memory. |
| `learning-adaptation-03` (seam raises) | `LiveLearningPromotionPort` widens to expose `begin_match` AND `handle_after_match`; composition calls `begin_match(match_id)` at match admission on the SAME instance that receives the terminal (§4.3). The existing raise at `live.py:107-109` then becomes the intended fail-closed guard against seam regressions instead of a guaranteed crash. |

### 4.2 `POLICY_PROMOTED` — event, payload, and the four fail-closed registration sites

**DESIGN — payload, field-by-field** (`extra="forbid"`, frozen, like every payload):

```
ModelSOPolicyPromotedPayload:
  kind: Literal["steel_onslaught.policy_promoted"]  # discriminator (Rev 2 — shipped in #123, accepted §4.6a)
  match_id: str                    # must equal envelope.match_id (validator)
  policy_id: str                   # new policy id (ModelSOLiveLearningPolicy.policy_id shape)
  archetype: str                   # promoted archetype; matches admitted policy archetype
  generation: int  (ge=1)          # new generation = admitted generation + 1
  spec_hash: str                   # new policy spec hash
  parent_spec_hash: str            # admitted policy spec hash — the chain link
  source_lineage_digest: str       # digest of the promoted ModelSOLineageRecord
  evidence_scored_event_id: str    # ULID of the MATCH_SCORED event whose evidence was evaluated
```

Deliberately **hash-carrying, not parameter-carrying**: raw `parameters` live in the lineage record; the event carries the digests that make the chain verifiable. Audit path: `POLICY_PROMOTED` → `source_lineage_digest` → lineage record (params + duel evidence) → `evidence_scored_event_id` → replay the promoting match. That chain is the "replay why" claim in §1, made concrete.

**Envelope placement (DESIGN):** appended to the **promoting match's** stream — `match_id` = promoting match, `tick` = terminal tick, `sequence_in_tick` after `MATCH_SCORED`, `subject` = the seat whose policy promoted, constructed via `caused_by(<MATCH_SCORED envelope>, ...)` (`events/envelope.py:194`) so causation is `MATCH_SCORED → POLICY_PROMOTED`. Cross-match ordering authority is **`generation` + the `parent_spec_hash` chain**, NOT wall clock (`emitted_at` is explicitly excluded from ordering, `envelope.py:80-84`); the coordinator's existing no-rollback stale check (`live.py:143-149`) already enforces monotonic generations in-process.

**Four registration sites, all fail-closed if missed (first three OBSERVED as mechanisms, the fourth must be probed at build):**

1. `SOEventType` member — **append-only** to preserve protocol ordering (the card-lifecycle members document exactly this discipline, `envelope.py:56-58`).
2. **Payload authority census.** `project_match_learning_evidence` raises `"no payload contract registered"` for any unregistered event type (`post_match.py:64-65` — Rev 2 corrects the earlier off-by-two `66-67` citation). Trap: the FIRST projection of a promoting match happens at `MATCH_SCORED` delivery, *before* `POLICY_PROMOTED` is appended — it passes. Any later reprojection of that stream (process restart, idempotence re-entry, offline analysis) then fails closed. The payload model MUST land in the census (`events/payloads.py` / the projector map at `post_match.py:30-33`) **in the same PR** that adds the member.
3. **Canonical match fold:** `POLICY_PROMOTED` is a fold no-op for match state (like the card lifecycle members) — it is cross-match policy state, folded by the learning boot path, not by `MatchStateFold`.
4. **Post-terminal append legality. RESOLVED (OBSERVED, Rev 2 — #123 @ `7dc970e`): post-terminal append is LEGAL.** Historical framing: whether any ledger/replay validator asserted `MATCH_SCORED` is stream-final was UNVERIFIED at Rev 1; a build-time probe was required. Resolution: #123's E2E proved reprojection passes the fail-closed census and `verify_replay_validity` is TRUE with the `POLICY_PROMOTED` appendix.

### 4.3 The admission↔terminal seam contract

**DESIGN, field-by-field:**

- `LiveLearningPromotionPort` gains `begin_match(match_id: str) -> ModelSOLiveMatchPolicySnapshot` alongside `handle_after_match` (today it exposes only the latter — `live.py:37-42` — which is blocker 03).
- **Admission site:** the composition path that assembles the live stack (`match/composition.py`, the same function that constructs `MatchRuntime` at `:2047-2056` and subscribes the learning handler at `:2064-2073`) calls `begin_match(match_id)` before the runner starts, and passes the same coordinator instance as `promotion=`. One instance spans admission and terminal for the process lifetime.
- **Terminal site:** unchanged — `AfterMatchLearningHandler.handle` already orders evidence-write BEFORE promotion (`after_match.py:59-62`), so a promotion failure never loses the evidence artifact, and the match stays unmarked-processed (retryable). Keep that ordering.
- **Snapshot semantics:** unchanged from `live.py` — immutable per-match snapshot at admission; overlapping matches resolve via the existing stale check (no rollback).
- **Cross-process continuity (honest gap):** each `so play` process builds a fresh stack, so `current_policy` must be **rehydrated at composition time** from the durable chain (highest-generation promoted record for the archetype, verified against the `POLICY_PROMOTED` chain), with a genesis policy when the chain is empty. Without this, learning resets every process and the event is decorative.

### 4.4 First concrete evaluator

**DESIGN.** `LiveLearningEvaluator.evaluate(evidence, policy) -> ModelSOLineageRecord | None` (`live.py:29-34`). Two-stage rollout:

1. **Scripted evaluator (test/battery double)** to prove the seam end-to-end — promotion on demand, `POLICY_PROMOTED` in the ledger, replay green — before any learning judgment exists. (The existing `FakeEvaluator` is the *offline* protocol; a live-protocol double is new but trivial.)
2. **`SelectionOutcomeEvaluator` (first real one):** consumes the after-match evidence the projector already produces (decision/action/reason counters, card learning metrics via `project_card_learning_metrics`), proposes a candidate parameter perturbation via the existing search machinery (`learning/search.py`), and gates it through the **existing, working offline duel path** (`learning/duel_evaluator.py` + `match/duel.py` + `learning/promotion.py`) with the injected duel capability. Returns the promoted lineage record or `None`. This reuses the only learning judgment that has ever run rather than inventing a second one.

### 4.5 What the policy actually controls (the honest gap that pairs learning with depth)

**OBSERVED:** `ModelSOLiveLearningPolicy.parameters` has **no live-match consumer today** — nothing on the live path reads a policy to change a decision. **DESIGN:** the consumption point is the depth decision space itself:

- Policy parameters are **selection/draft biases** — category weights, heat-risk tolerance, utility propensity, (later) draft aggressiveness — rendered into the programming/draft prompt as a policy-guidance block, exactly parallel to persona instructions.
- `MATCH_STARTED` gains per-seat **policy provenance**: `{policy_id, spec_hash, generation, source_lineage_digest}` (closed-model extension, registered in the payload census like §4.2 item 2). This binds every decision in a match's ledger to the policy that shaped it — without it, "a promotion changed a later decision" is unfalsifiable.
- Efficacy is measured with the SAME instruments that validated #117: keep-rates vs random, category selection distributions, and later the Phase-B draft metrics. That is the concrete sense in which learning "rides on" the depth space.

### 4.6 Build reconciliation — #123 deviations, dispositions (Rev 2, OBSERVED @ `7dc970e`)

Phase 1 shipped in #123. Each deviation from the design as written, with the operator-gate disposition:

- **(a) Payload discriminator.** The payload carries a `kind` discriminator `Literal["steel_onslaught.policy_promoted"]` — **ACCEPTED**; the §4.2 payload block is updated to include it (9 fields).
- **(b) Envelope subject.** The envelope subject is the wildcard `*/*`, not per-seat — **ACCEPTED interim**; per-seat subject folds into the L-GATE-2 scope.
- **(c) First concrete evaluator.** `WinDamageDifferentialEvaluator` (deterministic damage-differential + decisive-win, bounded) is the first concrete evaluator, superseding the "scripted double" as stage 1 of §4.4 — `SelectionOutcomeEvaluator` remains the L-GATE-2 real evaluator.
- **(d) Lineage evidence seeds.** Live lineage evidence seeds are match-digest sample identifiers with `p_value=1.0` / `decisive_n=1` (no significance claim) — **ACCEPTED for the spine**; significance discipline lands with `SelectionOutcomeEvaluator`.
- **(e) Provenance + consumption still OPEN.** `MATCH_STARTED` policy provenance was NOT shipped, and policy parameters still have NO live consumer — this **remains OPEN** and is exactly the L-GATE-2 work package (§4.5 unchanged and still the honest gap).
- **(f) Genesis invariant.** Genesis-change-after-promotions fails closed — **ACCEPTED as invariant**.

---

## 5. Kill-gates and probes

Every increment gets a measured go/no-go, mirroring the four-round balance discipline (measure → decide → stop is a legal outcome). No gate may be certified by CI-green alone; each names live evidence.

| Gate | Before | Question | Go threshold | Evidence surface |
|---|---|---|---|---|
| **L-GATE-1** wiring proof — **PASSED (Rev 2, #123 @ `7dc970e`)** | Phase 1 exit | Does the spine work without judgment? | Scored match with coordinator wired does NOT raise; scripted promotion yields `POLICY_PROMOTED` in the ledger; **reprojection** of the promoting stream passes; replay validity green. **Result:** scored match no raise; `POLICY_PROMOTED` in ledger ordered after + caused-by `MATCH_SCORED`; double-fold + fresh-composition rehydration identical; live keyless smoke promoted `generation=1` for real | ledger readback + reprojection run + replay assert |
| **L-GATE-2** policy efficacy — **audit half PASSED (#126); behavioral half FAILED (significance battery, `docs/evidence/2026-07-22-lgate2-significance-battery.md`: no parameterized-direction shift in two batteries, replicated anti-directional vent-keep signal)** | Phase 1 done | Does a promotion change a later decision, auditably? | Next-match selection metrics shift in the parameterized direction vs pre-promotion baseline; `MATCH_STARTED` provenance cites the new `policy_id`; chain verifies event→lineage→replay | before/after adaptation battery on live Qwen |
| **U-GATE** utility counterplay | Phase 2 exit | Is counterplay used intentfully and does it bite? | Utility keep-rate > chance (per #117 methodology); measurable engagement effect (e.g. sniper aimed hit-rate under smoke drops; flare breaks lock in replay); no coherence regression; **no balance knob touched** | utility battery, winner-side distribution reported |
| **D-GATE-0** draw-through pre-measure — **MEASURED, CONDITIONAL (Rev 2, #122 @ `830dc0b`)** | ANY drafting code | Do acquired cards even get drawn? | Zero-code ledger measurement of rounds/match vs deck-cycle length projects ≥~50% draw-through at the chosen starting-deck size. **Result:** P(drawn)=0.62, P(played)=0.45 aggregate vs the ≥~50% bar; first-cycle buys clear at 0.69–0.70; two quantified rescues — ~10-card small starting deck → P(played)≥~0.6 through phase 9, or acquired-to-top-of-draw → P(drawn)~1.0 | measured via `scripts/measure_draw_through.py` over existing ledgers (#122) |
| **D-GATE-1..5** drafting Phase B | Phase 3 exit | The five falsifiable heat-design gates | draw-through ≥~50% measured; model-draft > random-draft; composition divergence > 0; buy-vs-win NOT monotonic; drafted-match replay identical | draft battery + replay assert (heat design §5) |
| **O-GATE** objectives | Phase 4 exit | Do matches end on play, not clock? | ≥95% of battery matches end on VP threshold or elimination; tick-cap failsafe is reported as anomaly; winner-side distribution reported; brawler win-rate **observed** (hypothesis: moves off ~5% floor without knob tuning) | objective battery + terminal-class scorecard |

**Fail semantics:** a failed gate stops its phase (iterate or abandon), exactly as Phase-A failure would have stopped the pivot. D-GATE-0 failing means shrink the starting deck or move acquisitions closer to draw and re-measure — not "build the UI anyway" (heat design §2.4). O-GATE's brawler observable failing to move is a recorded finding that forces a design review, not a knob round (§2).

---

## 6. Phased build plan with per-phase seams

Seams are named field-by-field per the define-and-match discipline; every phase lands its cross-boundary regression test WITH the feature, not after.

### Phase 0 — preconditions (other lanes; not this design's deliverables) — **DONE (Rev 2, OBSERVED)**

- **DONE (OBSERVED):** #117 merged (`2e6a31e`).
- **DONE (Rev 2, OBSERVED):** sniper-JSON strict-output fix merged as #119 (`b3a5377`); RED brawler `invalid_action_parameters` abort root-caused and fixed as #120 (`8f9f0e7`, dealt-hand clamp), made seat-generic by #121 (`f1fd18e`); batteries proven clean by #124 (`fd05bb9`): 0 aborts in 840/840 completions, 30/30 real gameplay terminals (§0.9). The clean-battery precondition for Phase 1+ gates is met.

### Phase 1 — learning spine (starts immediately; independent of new depth mechanics)

Runs over the EXISTING over-deal space — no new game mechanics required, which is why it can start first.

| Seam | Contract | Rev 2 status |
|---|---|---|
| Event | `SOEventType.POLICY_PROMOTED = "policy_promoted"` (append-only) | **DONE @ `7dc970e`** (#123) |
| Payload | `ModelSOPolicyPromotedPayload` — 9 fields as specified in §4.2 (incl. `kind` discriminator, §4.6a), `extra="forbid"`, frozen | **DONE @ `7dc970e`** (#123) |
| Census | payload registered in the authority census + projector map (same PR — §4.2 trap) | **DONE @ `7dc970e`** (#123) |
| Fold | canonical fold no-op; learning boot path folds the chain (generation ordering) | **DONE @ `7dc970e`** (#123) |
| Port | `LiveLearningPromotionPort` = `begin_match` + `handle_after_match` | **DONE @ `7dc970e`** (#123) |
| Composition | admission call + `promotion=` injection at `composition.py:2066-2069`; boot-time policy rehydration (genesis when chain empty) | **DONE @ `7dc970e`** (#123) |
| Provenance | `MATCH_STARTED` payload + per-seat `policy_provenance {policy_id, spec_hash, generation, source_lineage_digest}` | **OPEN — L-GATE-2 package** (parallel lane this session; §4.6e) |
| Evaluator | first concrete evaluator (`WinDamageDifferentialEvaluator` shipped, superseding the scripted double — §4.6c); then `SelectionOutcomeEvaluator` over search + duel + promotion machinery | stage 1 **DONE @ `7dc970e`** (#123); `SelectionOutcomeEvaluator` **OPEN — L-GATE-2 package** |
| Regression | cross-boundary test driving admission → live match → terminal → promotion → ledger append → REPROJECTION → replay; plus the post-terminal-append legality probe (§4.2 item 4, now RESOLVED) | **DONE @ `7dc970e`** (#123) |

**Acceptance evidence (live-measured):** L-GATE-1 **PASSED (Rev 2, #123)**; L-GATE-2 remaining.

**Rev 2 residual:** the frontend transport carve-out branches (accept-once-after-scored / reject-before-scored / reject-repeat) shipped untested in #123 — covered by a parallel lane this session.

### Phase 2 — utility cards (parallel-eligible with Phase 1 after seam review)

| Seam | Contract |
|---|---|
| Quota | `ModelSODeckHandQuota.utility: StrictInt (ge=0, default=0)` — default 0 keeps every existing overlay valid byte-for-byte |
| Cards | 3 utility card contracts (smoke/chaff/flares) in `contracts_data/cards`; `category: utility`; `heat_cost` authored now (inert until Phase 3 — dual-use per heat design §4) |
| Event | `SOEventType.UTILITY_DEPLOYED` — payload: `card_id, utility_kind ∈ {smoke, chaff, flares}, origin {x,y}, radius (ge=0), duration_ticks (ge=1)` |
| Fold | active-utility-effects state folded into match state (expiry by tick); hit/LOS resolution consults it — the first battlefield-affecting card fold |
| Handlers | resolution effects as allowlisted handlers selected by typed overlay (repo operating rule; same discipline Phase 2.5 needs) |
| Census | payload registered (same trap as §4.2) |
| Regression | fixture: smoke cell blocks a previously-clear LOS; flare breaks a lock; effects expire on schedule; replay identical |

**Acceptance evidence:** U-GATE battery.

### Phase 2.5 — Heavy/Assault keywords

| Seam | Contract |
|---|---|
| Contract | closed `keywords: tuple[Literal["heavy","assault"], ...]` on the card (or loadout weapon) contract — additive, default empty |
| Handlers | two allowlisted resolution handlers; handler IDs visible in replay (finish-line requirement) |
| Fold | no new events — keywords modify existing `WEAPON_FIRED`/accuracy resolution; moved-this-round is already derivable from folded movement |
| Regression | keyword fixtures: Heavy degraded after move, Assault clean after advance; replay identical |

**Acceptance evidence:** fixture battery + a live battery demonstrating behavioral difference (planted-sniper vs relocating-sniper distributions).

### Phase 3 — heat-drafting Phase B slice (BLOCKED on D-GATE-0)

Per the heat-drafting design §5, adopted unchanged; seams restated for the match table:

| Seam | Contract |
|---|---|
| Event | `SOEventType.CARD_ACQUIRED` — payload: `card_id, supply_pile_id, heat_spent (ge=0), heat_after (ge=0), pile_remaining (ge=0)` |
| Pricing | %-of-headroom units (per-boiler scaled — §3.3); `heat_cost` becomes live |
| Fold | first fold of card composition: owned-multiset ⊕ acquisitions; supply depletion state |
| Invariants | conservation rebase from static `deck.card_multiset()` to `static ⊕ folded_acquisitions` (loci per heat design: `round.py:198-204`, `replay/card_round.py:292-295`) |
| Shuffle | composition-keyed seeded RNG reproduces automatically once composition is folded (heat design §1.4) — contingent on fold-before-shuffle ordering, pinned |
| Discipline | ≤1 buy/round; acquired-to-discard; **small starting deck (~10 cards) is a HARD requirement per D-GATE-0 (Rev 2 — P(played)≥~0.6 through phase 9 at that size), with acquired-to-top-of-draw as the fallback dial (P(drawn)~1.0)**; double-tax as catalog authoring invariant |
| Census | payload registered |
| Regression | the mandatory fold-then-reshuffle cross-boundary replay test (heat design §2.3) |

**Acceptance evidence:** D-GATE-1..5. Any failure ⇒ iterate the slice or abandon; no UI, no multi-buy, no full supply until all five pass.

### Phase 4 — objectives + VP victory + new versioned arena

| Seam | Contract |
|---|---|
| Arena | new versioned contract `foundry_60_asym_v1`: asymmetric cover + `objectives: tuple[{objective_id, cell {x,y}, vp_per_round (ge=1)}]`; `foundry_60` untouched |
| Event | `SOEventType.OBJECTIVE_SCORED` — payload: `objective_id, controlling_player_id, vp_awarded (ge=1), cumulative_vp {player_id: int}, round_index` |
| Victory | `VICTORY_DECLARED` payload gains `victory_kind ∈ {elimination, vp_threshold, tick_cap_failsafe}`; VP threshold in the objective contract; 1000-tick cap failsafe-only |
| Fold | per-player VP folded into match state; control determination from folded positions |
| Census | payloads registered; evidence projector picks up `victory_kind` so learning sees HOW matches end |
| Regression | mutual-contest, threshold-exact, and failsafe fixtures; replay identical; objective contract hash in `MATCH_STARTED` (finish-line table) |

**Acceptance evidence:** O-GATE battery on the new arena, brawler-vs-sniper, winner-side distribution + terminal-class scorecard.

**Sequencing note (DESIGN):** 1 → 2 → 2.5 → 3 → 4 is the dependency-honest default, and Phase 1 must land first so every later phase's batteries are learning-instrumented (policy provenance in every ledger). If U-GATE passes but the brawler observable stays flat, Phase 4 may be pulled ahead of Phase 3 — objectives are the strongest "reason to close" lever (finish-plan action 7) and D-GATE-0 might force a drafting redesign anyway. That reorder is a gate-driven decision, not a preference. **Rev 2:** the BLUE 30/30 terminal sweep on merged-main balance (#124, §3.4) is fresh measured weight behind the pull-Phase-4-ahead option, and D-GATE-0's CONDITIONAL result (§5) confirms drafting carries a hard precondition (small starting deck or top-of-draw) either way.

---

## 7. Speculation register (explicitly NOT established)

1. That utility cards produce measurable counterplay at current model capability — U-GATE exists because this is unproven.
2. That draw-through clears ~50% at any acceptable starting-deck size — **resolved CONDITIONAL by #122 (`830dc0b`)**: aggregate P(drawn)=0.62 / P(played)=0.45 vs the ≥~50% bar; first-cycle buys clear at 0.69–0.70; it clears only under a rescue (~10-card small starting deck → P(played)≥~0.6 through phase 9, or acquired-to-top-of-draw → P(drawn)~1.0). The conditional discipline is now a HARD Phase 3 requirement (§6).
3. That prompt-rendered policy parameters shift live-Qwen selection behavior measurably — L-GATE-2 exists because no live policy consumer has ever run.
4. That objective play moves brawler win-rate off the ~5% floor — the O-GATE observable; the depth thesis's falsifiable core.
5. That post-terminal ledger appends are legal today — **RESOLVED by #123 (`7dc970e`)**: legal; reprojection passes the fail-closed census and `verify_replay_validity` is TRUE with the `POLICY_PROMOTED` appendix (§4.2 item 4).
6. The "berserker runs hot / sniper runs cool" ambient-heat asymmetry both heat-design sources assumed — flagged unverified there (heat design §0), still unverified; Phase 3 pricing must not depend on it.

Each item above is paired with the gate or probe that resolves it. Nothing in this design asks for trust in an unmeasured claim.
