# LEARNINGS — living register of evidence-cited findings

**Maintenance contract.** This register is appended to every session; it is never
rewritten wholesale. Rules for every append:

- Add entries to the existing themed sections below; do not add dated per-session
  subheadings. Each entry is self-dating via its trailing `(YYYY-MM-DD, evidence)`.
- Every entry MUST carry an evidence citation — a PR number, merge SHA, or an
  evidence/design/plan document path. No entry without evidence.
- Negative and falsified results are first-class entries, not footnotes. A
  hypothesis this project killed with measurement belongs here as much as one it
  confirmed.
- Entry format: **bold one-line finding** — 1–3 sentences of what/why it matters —
  `(date, citations)`. Match the repo's factual register: no hype, no filler.
- If a later session falsifies or narrows an existing entry, append a new entry
  that cites and corrects it; do not silently edit the old one.

---

## LLM pilot behavior

- **Prompt consumption is not behavioral control.** Policy guidance provably
  reaches the wire prompt (byte-verified per promotion), yet across two independent
  live batteries (n=10+10 @ step 0.25; n=30+30 @ step 0.5) no selection metric
  moved in the parameterized direction, and the only detectable effect — a
  vent-keep RISE after an aggression-up promotion — replicated across both
  batteries against the declared semantics (d=+0.51 in the second; post-hoc Fisher
  combined p≈0.003). The L-GATE-2 behavioral half is FAILED at the tested
  operating points. (2026-07-22, #126, #128,
  `docs/evidence/2026-07-22-lgate2-adaptation-battery.md`,
  `docs/evidence/2026-07-22-lgate2-significance-battery.md`)

- **Doctrine overrides legality.** When a persona's doctrine conflicts with the
  dealt hand (preferred card short-dealt), qwen35 emits structurally perfect but
  multiset-illegal plans and repeats the identical violation across the whole
  bounded repair budget (live repro 6/6). The fix is at the source — explicit
  doctrine subordination plus a code-owned copy clamp in the shared instructions —
  made seat-generic by construction via a dynamic registry matrix plus a synthetic
  maximally-tempting adversarial persona. (2026-07-22, #120, #121)

- **Strict output contracts kill whole abort classes.** Reasoning-wrapper leakage
  (`<think>` spans, code fences) defeated first-`{`/last-`}` JSON extraction and
  drove invalid-JSON aborts; the strict-output persona contract + parser strip cut
  blue `malformed_json` aborts 3→0 across 56 matches (measured on the #116 branch
  content that #119 split out and landed). The post-fix battery on merged main:
  0 aborts of any class in 840/840 completions, 30/30 real gameplay terminals vs
  a 33.9% (19/56) non-gameplay-terminal baseline. (2026-07-22, #119, #124,
  `docs/evidence/2026-07-22-post-fix-abort-battery.md`)

- **Selection reveals identity.** On the same balanced 4/4 over-dealt hand,
  brawler keeps ADVANCE at 0.94 vs sniper 0.30, and dumps dead VENT cards at 0.11
  vs random 0.62 — archetype identity emerges from what a model PRUNES, not what
  it is dealt. This is the empirical green light for the whole depth program.
  (2026-07-22, #117; design doc §0.2, #118)

- **You cannot measure steering on a saturated axis.** Attack keep-rate was
  ceilinged before learning started (blue 0.997 baseline; red 1.0 in every match)
  and vent keep-rate sat at the 0.0 floor — the aggression axis had almost no live
  decision surface. Behavioral experiments need parameters with headroom, chosen
  from measured baselines, or the result is uninformative by construction.
  (2026-07-22, #126, #128,
  `docs/evidence/2026-07-22-lgate2-significance-battery.md`)

## Game & mechanics design

- **Structural imbalance resists parametric tuning.** Four measured single-lever
  rounds on the 60-vs-160 fixed-deck duel (heat-lockout; ×5.5 brawler damage;
  moves-scaled evasion sweep; range-band + carbine throttle) each moved their
  local metric — brawler median DMG-OUT ~2→~50, survival ~4× — yet win-rate stayed
  pinned ~5% (pooled 1/43). The pre-agreed stop fired: no fifth knob round;
  balance must re-emerge from depth (objectives, drafting, utility), not knobs.
  (2026-07-22, design doc §0.3/§2, #118; finish plan 2026-07-21 session update,
  PR #108 branch)

- **Falsified: the carbine was never the killer.** Round 4b throttled the sniper's
  close-in carbine (cooldown 1→3) and sniper DMG-OUT stayed flat (62→64)
  regardless of carbine rate — the harpoon + mortar aimed core is the real killer.
  A whole intervention lever was aimed at the wrong weapon until measurement said
  so. (2026-07-21, finish plan 2026-07-21 session update, PR #108 branch; design
  doc §3.2, #118)

- **Corrected premise: terrain was never inert.** "Obstacles do nothing" was
  false — they block movement AND weapon LOS today (88% of shots blocked in the
  probe). The actual defect is layout quality: 336 symmetric-scatter cells that
  help nobody. The fix is asymmetric cover in a NEW versioned arena, never an
  in-place edit of `foundry_60` (old replays must stay valid). (2026-07-21,
  design doc §0.8, #118; finish plan, PR #108 branch)

- **Deck geometry gates drafting.** 20-card piles + whole-hand discard of an
  8-card deal give an exact 5-phase reshuffle cycle (reshuffles at phases
  6/11/16/21 in 100% of eligible hands), so a mid-match acquisition waits a median
  3–8 phases against a median 13-phase match: aggregate P(played)=0.45, below the
  ~50% kill-gate. First-cycle buys clear it (P(played) 0.69–0.70); the quantified
  rescues are a ~10-card starting deck (P(played)≥~0.6 through phase 9) or
  acquired-to-top-of-draw (P(drawn)≈1.0). (2026-07-22, #122,
  `docs/evidence/2026-07-22-draw-through-measurement.md`)

- **Seat dominance blocks learning, not just fairness.** BLUE won 30/30 in the
  post-fix battery and the red berserker went 0/35 in the significance battery —
  so the win-gated `win_damage_differential_v1` evaluator can NEVER fire a
  promotion on the dominated seat (it requires a decisive learner win). Balance
  defects are learning-infrastructure defects. (2026-07-22, #124, #128,
  `docs/evidence/2026-07-22-lgate2-significance-battery.md`)

## Engineering & platform

- **Event-sourced promotion delivers real auditability.** The chain
  `POLICY_PROMOTED` → lineage digest → per-seat `MATCH_STARTED` provenance
  (byte-equality asserted per match) → replay validity held machine-checked at
  21/21 matches, then at n=30 post-promotion matches, including fresh-process
  rehydration of the promoted policy purely from the durable chain. Policy
  evolution as a hash-linked replayable event chain, not an in-memory flag.
  (2026-07-22, #123, #126, #128)

- **Validate-then-commit.** The frontend transport gate threw AFTER
  `buf.events.push`, and since the rAF pump keeps running after a fail-fast ingest
  throw, a rejected `policy_promoted` envelope still flowed downstream on the next
  animation frame. Found by writing the missing tests for the three gating
  branches (shipped untested in #123); fixed by hoisting validation above the
  commit point. (2026-07-22, #125)

- **Auxiliary subsystems must not share fate with the primary.** The duel-gate
  evaluator runs its entire LLM duel battery synchronously inside the live match's
  `MATCH_SCORED` bus publish (F1), and one retryable `LlmTransportError` in one
  duel propagated uncontained and killed the live match and process (F2).
  Containment fix in flight at time of writing. (2026-07-22, #128 RUN B attempt 1,
  `docs/evidence/2026-07-22-lgate2-significance-battery.md`)

- **Fail-closed vocabularies catch same-PR traps.** The evidence projector raises
  on any unregistered event type — but only on REPROJECTION, because the first
  projection of a promoting match runs before `POLICY_PROMOTED` is appended. The
  design doc named this trap ("payload must land in the census in the same PR")
  and the build avoided it because it was named. (2026-07-22, design doc §4.2,
  #118; #123)

- **Name-greps are blind to structural typing.** A "zero `LiveLearningEvaluator`
  implementations anywhere" claim was refuted: two test doubles
  (`tests/learning/test_live.py` `_Evaluator`/`_FlakyEvaluator`) implemented the
  Protocol structurally all along. Grep for the protocol name finds subclasses,
  not implementers. (2026-07-22, design doc §0.4 Rev 2 correction, #118)

- **Detection without enforcement recurs.** Four full-typecheck errors
  accumulated silently on main because CI type-checked only the build tsconfig,
  which excludes `src/__tests__`. Fixed (#127), then gated in the same existing
  `frontend-test` CI job (#129) — keeping the 4-check contract stable instead of
  adding a fifth context. (2026-07-22, #127, #129)

## Method & process

- **Pre-registration makes negative results trustworthy.** The significance
  battery committed its directional predictions, primary endpoints, and fallback
  plans before either run; when both primary endpoints came back null or
  wrong-signed, the FAILED verdict stood without suspicion of post-hoc framing —
  including the honest labeling of the Fisher-combined replication as post-hoc.
  (2026-07-22, #128, `docs/evidence/2026-07-22-lgate2-significance-battery.md`)

- **Adversarial verification pays for itself.** Independent verification refuted
  the "zero Protocol implementations" claim and an off-by-two source citation in
  the design doc (both corrected in Rev 2), and found a real shipped defect —
  #123's untested transport carve-out releasing poisoned projections downstream
  (fixed in #125). Implementer green is not evidence. (2026-07-22, design doc
  Rev 2 corrections, #118; #125)
