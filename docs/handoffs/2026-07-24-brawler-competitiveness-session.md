# Steel Onslaught — Brawler-Competitiveness Session Handoff (2026-07-24)

Repo `jonahgabriel/steel_onslaught`, default branch `main`. This is the **authoritative close-out for the brawler-competitiveness session** (2026-07-24, run alongside/after the cross-model-utility session). It **complements, does not supersede,** `docs/handoffs/2026-07-24-cross-model-utility-session.md` — that doc is still the record of the 4-model utility-suppression finding; this doc is the record of the separate program to make the brawler (red) win at all against the sniper (blue). Every number below is cited to a merged evidence doc on `main` (`docs/evidence/2026-07-24-*.md`) or a merged PR body; every PR number was independently re-verified live via `gh pr view` while writing this doc, not copied from an earlier draft.

---

## 0. North star (continuity with the cross-model handoff §0 — read that first)

Steel Onslaught is an **architecture-legibility demo**, not primarily an LLM-behavior study (contracts → events → replay → declarative config, walkable by a person). This session used the substrate as a high-throughput experiment rig in service of that demo: ~16 batteries, on the order of several hundred live-model matches, every one `all_replay_valid=true`, every reported number independently recomputed from the raw event ledger by an adversarial verifier — not implementer/runner self-report. The scientific yield (a real dose-response curve, a falsified prior null, a located contract gap) is a byproduct of exercising the machine hard, in public, and is itself evidence the platform holds up under load: no ledger corruption, no un-reproducible result, across every arm including the two that hit external provider quota walls.

---

## 1. The program and the baseline

**Question:** can the aggressive/brawler (red) seat be made competitive against the defensive/sniper (blue) seat, on qwen35, holding the LLM fixed?

**Baseline (asym v1 anchor):** red 0/30 (`docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md` — win-rate/keep-rate figure only; that doc does not contain hit-count or damage figures). Blue kills red in a mean **~2.04 hits** at **~29.47** mean damage-after-armor per hit; red, if sustained at its own observed per-hit output, needs an implied **~26.74 hits** to kill blue (red mean damage-after-armor **~5.98**/hit). **Citation correction (this handoff's own verification pass):** these four hit/damage figures are repeated verbatim as "historical baseline (context, cited)" across the three pair-sweep evidence docs (`docs/evidence/2026-07-24-pair_p1_dmg3-battery.md`, `-pair_p2_dmg55-battery.md`, `-pair_p3_armor8-battery.md`) but **none of those docs, nor the 2026-07-23 utility-surfacing-fix-remeasure doc, nor any other merged evidence doc, gives a primary source or re-derivation for them** — they are an inherited, uncited convention, not independently verified in this pass. Treat the ~13× kill-speed asymmetry as directionally credible (it is internally consistent with every pair-sweep arm's own recomputed numbers) but not yet traced to a primary ledger. That ~13× kill-speed asymmetry is the mechanical shape of the problem every arm below tried to close — mostly by changing sniper *positioning/range/cooldown/accuracy* (geometry-side levers) before this session finally isolated the *damage* axis.

---

## 2. Arm ledger (every arm this session, ordered as run)

| # | Arm | Lever | Result | Code PR | Evidence PR |
|---|---|---|---|---|---|
| 1 | Brawler re-cut v2 | Sightline-breaking cover rects + heat-lance weapon refit + headroom | **FAILED** 0/30 | #157 | #158 |
| 2a | Tournament arm 1 | Sniper mortar range 50→30 | **FAILED** 0/30 | #159 | #161 |
| 2b | Tournament arm 13 | Leapfrog cover (5 staggered N/S blocks in sniper lane) | **FAILED** 0/30 | #159 | #162 |
| 2c | Tournament arm 3 | Sniper mortar cooldown 5→9 | **FAILED** 0/29 (1 abort) | #159 | #164 |
| 2d | Tournament arm 11 | Corridor spawn (brawler spawns in covered corridor mouth) | **FAILED** 0/30 | #159 | #166 |
| 2e | Tournament arm 4 | Sniper mortar far-band accuracy nerf (conditional on arm 1) | **FAILED** 0/30 | #159 | #168 |
| 3 | `covered_advance` movement card | New deterministic LOS-preferring advance primitive | **FAILED** outcome 0/29 (card works: see §3) | #165 | #169 |
| 4 | ARM S — prompt surfacing | Surface cover cells + enemy weapon threat as facts, both seats | **FAILED** 0/29 + utility-suppression side effect | #160 | #163 |
| 5 | ARM G — prompt steering | ARM S + brawler-seat tactical guidance | **FAILED** outcome 0/29 (steering works behaviorally: see §4) | #160 | #175 |
| 6 | Spatial R1 | ASCII map + resolver-backed consequence previews + in-range flags | **FAILED** outcome 0/30 (cognition moves: see §5) | #167 | #172 |
| 7 | Spatial R2 | R1 + forced `spatial_read` scaffold field | **FAILED** outcome 0/24, trust gate missed (0.80) | #167 | #180 |
| 8a | Vision V-TEXT | Screenshot renderer + image adapter, text-only control | **VACUOUS** — free-tier quota (20 req/day) | #171 | #176 |
| 8b | Vision V-IMG | Same, image attachment | **VACUOUS** — same quota, 1/30 seeds attempted | #171 | #178 |
| 9a | Pair-sweep P1 | mortar_r30 (approach fix) + red raw dmg ×3 | **FAILED-but-nonzero** 1/29 = 3.4% | #170 | #177 |
| 9b | Pair-sweep P2 | mortar_r30 + red raw dmg ×5.5 | **DIRECTIONAL** 5/29 = 17.2% | #170 | #179 |
| 9c | Pair-sweep P3 | mortar_r30 + blue armor 16→8 | **FAILED** 0/28 — lever mechanically dead | #170 | #181 |

Every FAILED result above cleared its own trust gate (`play_terminal_fraction ≥ 0.9`) except spatial R2 (0.80, flagged, root-caused to a pre-existing sniper-seat JSON-malformation abort driver, not the scaffold) and the two vision arms (catastrophic quota failure, no trust gate applies because zero matches terminated). Nothing in this ledger is a self-report: every figure was independently recomputed from `events.sqlite3`/`battery_raw.jsonl` by an adversarial verifier per doc.

---

## 3. Route-audit forensics and the contract gap it found

Before the `covered_advance` build, an arm-zero route audit (against the re-cut v2 ledger, `docs/evidence/2026-07-24-brawler-recut-v2-battery.md`) established the actual blocker was not geometry:

- **Cover is unused at the decision layer:** 0/209 red plan rationales mention terrain, cover, or LOS in any form. The re-cut v2 doc's own verdict recommends exactly this instrumentation ("does it actually path through the new cover, or does the planner ignore terrain-relative reasoning entirely?") — the audit answered it: ignored, entirely.
- **The movement-card vocabulary had a real contract gap:** cards were relative-direction only (`toward_enemy`/`away_from_enemy`/left/right) — no cell-targeted or LOS-aware movement primitive existed, so cover was **unusable by construction**, independent of whether the model "wanted" to use it (PR #165 body, citing the same 0/209 figure).
- **Heat-lance (the weapon swapped in under the v2 re-cut) was used but insufficient**, not ignored: **PR #167's** pilot-spec header comment (`contracts_data/pilots/fire_dense_qwen/llm_qwen35_berserker_spatial_r1.yaml` — corrected from an earlier draft's "PR #165"; `git log` on that file shows it was introduced by PR #167, not #165) cites **85/107 red fire attempts out of range** in that prior battery, and the `covered_advance` card's deck-weight was sized against a **77.5% heat-lance-analog deal-rate bar** (hypergeometric target, `contracts_data/decks/movement_v2.yaml`, pinned by `test_deck_v2_deal_rate_clears_the_heat_lance_analog_bar`, PR #165).

**Verification caveat (do not overclaim):** the 0/209 and 85/107 figures are corroborated by two independent merged sources (the re-cut v2 evidence doc and PR #165's body/pilot-spec comments) but are not re-derived from a raw ledger inside a dedicated forensics evidence doc — the spatial R1 evidence doc explicitly flags 85/107 as "documented context, not independently re-derived" in that session's pass. Two figures referenced in this session's own verbal narration of the forensics pass — a ~89% heat-lance programming rate and a ~65.5% "opener" rate — could **not** be located in any merged evidence doc, PR body, or contract-file comment during this handoff's cross-check. Treat those two specific numbers as unconfirmed; do not cite them without locating the source.

---

## 3b. `covered_advance`: the card works, the outcome didn't move

PR #165 closed the contract gap with a new **movement-class** (deliberately not utility-class — aggressive-seat pilots suppress utility below chance across 4 model lineages, per the cross-model finding) deterministic card: pure function of `(from_pos, enemy_pos, budget)`, no bus/RNG/clock, enumerates the reachable Chebyshev disk, keeps only cells that both reduce distance to the enemy and sit outside the enemy's LOS, picks the fixed lexicographic minimum, degrades to plain `toward_enemy` when nothing helps. Proven deterministic (pure-function unit test) and proven to replay-fold byte-identically (`test_replay_reproduces_covered_advance_movement`).

Battery result (`docs/evidence/2026-07-24-covered-advance-battery.md`, PR #169): **0/29 red wins** (1 abort, transport instability, unrelated to the card) — but the card is **not inert**:

- **Programming rate 95.9%** (324/338 dealt occurrences programmed) — more than 2× any other movement card (`advance` 46.4%, `flank_left` 42.4%, `flank_right` 40.4%, `reposition` 3.7%). Movement-class placement avoided the utility-suppression trap by design, and the avoidance held: it worked.
- **Blue's zero-hit-probability shot fraction rose monotonically across all three brawler interventions:** 24.7% (v1) → 41.1% (arm zero / v2 re-cut) → **51.95%** (`covered_advance`) — the largest single jump of the three, and mechanically real (LOS-shadow resolver denying blue more of its attempted shots).
- That did **not** suppress blue's actual damage: hits landed per match rose slightly (2.533 → 2.733), and per-tick hit rate fell 17% (0.0767 → 0.0635) as matches simply ran longer (median ticks 31 → 33 → 43) rather than ending in red's favor. The card is a working-but-underpowered lever, not an inert one — a materially different failure mode from every geometry-only tournament arm above, all of which showed *zero* behavioral movement at all.

---

## 4. Prompt surfacing and steering: behavior moves, outcome doesn't, and a prior null gets overturned

**ARM S — factual surfacing only** (`docs/evidence/2026-07-24-prompt_surfacing_v2-battery.md`, PR #160/#163): 0/29, no routing change (red's movement occupies **0.0% cover cells** in both the surfaced and unsurfaced arm) — but with a real, unreported side effect: utility keep-rate dropped sharply on **both** seats relative to both baselines — red −64% relative (0.0552/0.0526 → 0.0188, z≈−3.1, p<0.002), blue −57% relative (0.1657/0.1794 → 0.0775, z≈−5.3). Surfacing more facts is not a free intervention; it measurably crowds out other card-selection behavior even with zero instructional content added.

**ARM G — surfacing + brawler-seat-only tactical steering** (`docs/evidence/2026-07-24-prompt_guidance_v2-battery.md`, PR #175): 0/29 outcome, identical to every other arm — but this is the single largest behavioral shift measured in the program: red's exposed-band (y=28–32) dwell time drops from ~41.9%/40.5% (arm-zero/ARM-S baselines) to **27.3%** (z≈−5 against both comparators), first-shot timing shifts substantially later, and median match length **nearly doubles** (30.5–33.0 → **54.0 ticks**). Literal cover-cell occupancy stays at exactly 0.0%, identical to ARM S and to `covered_advance`'s own baseline. This is a **band-avoidance** effect, not cover-seeking.

**This overturns the prior L-GATE-2 generalization** that prompt guidance does not steer qwen35 routing — that null was specific to *utility-card drafting* (a card-selection behavior), not routing/movement behavior generally. Guidance demonstrably does steer this model's spatial behavior; it's just not (yet) steering it into a win.

---

## 5. Spatial representation: cognition moves, outcome doesn't, R2 adds nothing over R1

**R1 — ASCII grid + resolver-backed consequence previews + in-range flags** (`docs/evidence/2026-07-24-spatial_r1-battery.md`, PR #167/#172): 0/30 outcome, but **directional cognition change**: clean-attribution spatial-vocabulary rationales (cover/LOS-blocking language, excluding persona-doctrine confounds) jumped from the **0/209** pre-representation baseline to **77/272 = 28.3%**; out-of-range fire fraction dropped **79.4% → 47.4%**; blue's zero-hit-probability shot fraction rose **41.1% → 55.8%**. Representation (show, not tell) demonstrably reaches the model's stated reasoning — vindicating the design bet at the cognition level even though outcome doesn't move.

**R2 — R1 + a required one-line `spatial_read` field before register selection** (`docs/evidence/2026-07-24-spatial_r2-battery.md`, PR #180): adds **nothing** measurable over R1 — cognition (22.8% vs R1's 28.3%), out-of-range fire (46.1% vs 47.4%), blue zero-probability fraction (55.0% vs 55.8%) all replicate within noise. 0/24 decided matches, **6/30 aborts, `play_terminal_fraction=0.80` — misses the ≥0.9 trust gate.** All 6 aborts independently traced to a pre-existing blue/sniper-seat JSON-malformation failure mode (`programming.py:244`), not the scaffold itself, so the 24-decided-match cognition/outcome read is not invalidated, but the battery as a whole does not clear trust threshold and a backfill re-run is recommended before treating R2 as closed. **Representation-only (grid, no forced field) is the keeper design.**

**Bug found, not yet fixed:** `spatial_read` is parsed off the model's response (`LLMProgrammingPilot._parse_response`, `programming.py:783`) but never persisted onto `ModelSOPlanCommittedPayload` — confirmed by querying all 264 `plan_committed` payloads in the R2 battery: zero carry a `spatial_read` key. The content of the model's spatial-read sentences is unrecoverable from the ledger; only the fact that the field was requested is verifiable.

---

## 6. Vision pilot: machinery sound, experiment vacuous, and a merged PR claim was false

PR #171 built a deterministic PNG arena renderer (sha256-in-ledger) and an image-capable adapter for a V-TEXT/V-IMG within-model comparison on `gemini-2.5-flash-lite`. Both arms are **VACUOUS**:

- **V-TEXT** (`docs/evidence/2026-07-24-vl_text-battery.md`, PR #176): 0/22 attempted matches terminated; live-reprobed `GEMINI_API_KEY` returns HTTP 429, `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20` — a **daily** cap, not a transient rate limit.
- **V-IMG** (`docs/evidence/2026-07-24-vl_img-battery.md`, PR #178): 1/30 seeds attempted, aborted on the very first call — V-TEXT had already exhausted the shared daily quota.
- **PR #171's merge-report claim that this was an "own-billed API key, not the shared OpenRouter `:free` pool" is FALSE**, independently disproven by the live quota-metric name itself (`generate_content_free_tier_requests`). Both evidence docs flag this as a factual misstatement in the merged PR body, not an environmental flake.
- The render/ledger machinery itself checks out cleanly at the component level: byte-identical deterministic PNG render tests pass (9/9), the persisted PNG's sha256 matches the ledger's `image_sha256` field exactly, and `image_attachment` wiring fired correctly before the provider call failed.
- **Gap found:** the battery driver (`scripts/run_ogate_objectives_battery.py`) has no exception handling around `_run_match` — a single unhandled provider error (one 429) kills the whole battery process rather than skipping the seed and continuing.
- **Operator note carried into this handoff:** a **Vertex API key exists** and was not tried this session — rerun via the Vertex path next session; other vision-language models are also candidates.

---

## 7. Pair-sweep: the decisive experiment — dose-response found on the damage axis

Every geometry-side lever (arms 1/3/4/11/13, `covered_advance`, prompt surfacing/steering, spatial representation) held the mortar_r30 approach-fix constant and moved *something else* — cover, cadence, cognition, behavior. None of them moved outcome. The pair-sweep held mortar_r30 constant and finally moved **lethality dose** directly:

| Arm | Lever (on top of mortar_r30) | Result | Wilson 95% CI (decided) |
|---|---|---:|---|
| P1 | red raw damage ×3 | **1/29 = 3.4%** — first red win of the entire program | [0.0061, 0.1718] (all-30 basis; upper bound overlaps low end of DIRECTIONAL, but point estimate classifies FAILED per program convention) |
| P2 | red raw damage ×5.5 | **5/29 = 17.2%** — DIRECTIONAL, best result to date | [0.076, 0.345] |
| P3 | blue armor 16→8 | **0/28 = 0.0%** — indistinguishable from double-null | [0, 0.1206] |

**P1/P2 dose-response is monotonic and accelerating, not linear:** x1 (mortar_r30 alone, prior arm) → 0%, x3 → 3.4%, x5.5 → 17.2% — a **1.83× larger dose produced a ~5× jump in win count**, both mechanically verified at the contract layer (exact multiplier diffs) and the engine layer (deterministic per-hit raw-damage reconstruction, zero variance across 93–101 hits). Kill-speed evidence is internally consistent: P2's damage-after-armor multiplier (26.68/5.98 = 4.46×) predicts red's mean hits-to-kill at 26.74/4.46 ≈ 6.0 — observed **6.40** (tight 6–7 range across all 5 wins). P1's single kill needed 12 hits vs. the ~26.74 baseline.

**P3 is a genuine, correctly-landed, mechanically dead lever — not a bug.** The engine's degrading-pool capped-fraction armor model (`absorbed = min(armor_value, ceil(damage_raw × 0.75))`) means armor's exact value only binds when it is smaller than 75% of incoming raw damage. Against red's weak stock weapons (raw 5/7 vs. blue's `heavy` class → caps of 4/6), the mitigation **cap**, not the armor pool, was already the limiting factor on **62/96 = 65%** of red-on-blue hits — halving `base_armor` changed nothing on those. **Mechanism-level conclusion:** under this armor model, lethality must be dosed on the attacker's raw damage, not the defender's armor pool, to move win rate — a flat-subtraction armor model would not show this asymmetry.

**Honest limit on the extrapolation:** the P2 evidence doc explicitly cautions that n=30/arm across three points is enough to establish *direction*, not enough to *fit* a real dose-response curve. Any specific higher-dose prediction (e.g., a particular multiplier expected to cross the 0.35 COMPETITIVE band or the 0.50 midpoint) is a back-of-envelope extrapolation from three points, not a number independently verified in a merged evidence doc — treat it as a hypothesis to test, not a forecast to trust. The qualitative signal — monotonic, accelerating, raw-damage-axis-specific — is solid; the exact multiplier where red becomes competitive is not yet known and is exactly what the next arm should establish.

---

## 8. Operational learnings

- **Per-seed isolated battery invocation** (`--n 1` per seed, own state root) defeats shared-endpoint transport flakes that crash `--n 30` runs (the pair-sweep P3 battery crashed twice mid-run on `LlmTransportError` and had to be resumed in segments; per-seed isolation avoided this in `covered_advance`).
- `battery_summary.json` can go stale after a resume-append — recompute from `battery_raw.jsonl` + `events.sqlite3`, never trust the on-disk summary after a segmented run (confirmed necessary in the P3 doc's own provenance section).
- `--fresh` unlinks the redirected `run.log` — treat `battery_raw.jsonl`/`events.sqlite3` as the durable record, not the log file.
- Match cadence on qwen35 (`omninode-pc.tail75df5e.ts.net:8000`, Qwen3.6-35B-A3B) is roughly 17–20s/match.

---

## 9. Housekeeping / open threads

- **Worktree GC:** ~6 stale worktrees were removed this session (~1.2GB reclaimed) per the session's own account; all data-bearing baselines and active lanes were preserved. Live `git worktree list` at doc-writing time still shows ~30 entries under `omni_worktrees/`, including one `SO-EVIDENCE-*` worktree per merged evidence PR this session (expected — each evidence PR was authored from its own worktree) plus the long-lived cross-model baselines (`SO-B-DEEPSEEK*`, `SO-B-GEMMA`, `SO-B-GLM`/`SO-B-GLM2`, `SO-UGATE-ASYM`, `SO-L2SIG`, `lgate2`, `so-ogate`, `exp1`). A further GC pass to retire the merged evidence-authoring worktrees is still pending.
- **`SO-B-GLM` vs `SO-B-GLM2`:** `SO-B-GLM2` holds a unique `ugate_glm_battery_smoke2` ledger not present in `SO-B-GLM` — disposition (keep both / merge / prune the smoke2 lane) is an **operator decision, pending**.
- **PR #156** (prior session's cross-model handoff) — **live-verified MERGED** (`gh pr view 156`: state MERGED, mergedAt 2026-07-24T17:10:52Z, merge SHA `9d59561`). This session's brief flagged it as possibly still open after a pair-sweep step attempted a merge-if-green; live state confirms it landed cleanly. No action needed.
- **Do not touch PRs #116 / #108** — left open intentionally per operator instruction, carried over from the cross-model session.

---

## 10. Next-session queue (ordered, operator decides direction)

1. **P4 — red raw damage ×8, holding mortar_r30 constant.** The single highest-information next battery: continues the only lever that has moved outcome at all, at a dose beyond the confirmed 0%→3.4%→17.2% curve. No specific win-rate prediction from this doc should be treated as calibrated (see §7's caveat) — run it and read the number.
2. **If P4 lands in a useful band:** a composition check (dose + `covered_advance` + spatial R1 representation stacked) and the design question this whole program was chasing — is a flat damage multiplier the shippable form, or should base stats/RoF/heat be re-cut to an equivalent effect? This is an operator call against the legibility north star (§0), not a default next build.
3. **Vision rerun via the Vertex API key** (operator-held, not yet tried) — machinery (renderer, adapter, ledger wiring) is proven sound; only the credential blocked V-TEXT/V-IMG this session.
4. **Fix the sniper-seat JSON-malformation abort driver** (`programming.py:244`) that caused all 6 R2 aborts; persist `spatial_read` onto `ModelSOPlanCommittedPayload` (currently parsed-but-dropped); add exception handling around `_run_match` in the battery driver so one provider error doesn't kill an entire 30-seed run. R2 backfill to n=30 decided matches is optional after the abort driver is fixed.
5. **`SO-B-GLM` smoke2 ledger disposition** (§9) — operator call.

---

## 11. Session close state (2026-07-24)

Nothing running. Sixteen batteries executed and independently verified across geometry, movement-contract, prompt, spatial-representation, vision, and damage-axis levers. The brawler is still 0-for-every-arm on outcome except the pair-sweep, which found the first two nonzero results of the entire program (P1 1/29, P2 5/29) and one dead lever (P3 0/28) — a real, mechanism-explained dose-response on the one axis (attacker raw damage) that had not previously been tried in isolation. Every other axis (approach geometry, movement-contract gap, prompt surfacing/steering, spatial representation) produced real, independently-verified behavioral or cognitive movement without moving outcome — a consistent pattern across six independent interventions, not a fluke on any one of them.
