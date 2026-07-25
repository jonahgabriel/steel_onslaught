# SO-OBJ-DECOY Arm (objectives PRESENT, non-scoring — `objective_scoring: decoy`) Battery — 2026-07-25

**Verdict: CAPTURE-ATTRIBUTABLE.** The pre-registered statistic is `g_pooled = 0.2115`, inside the pre-registered `<= 0.35` band. With the payout removed and the goal context held byte-identical, **21% of the measured objectives effect survives; the payout accounts for the other 79%.**

**The comparison that carries it.** Pooled utility keep-rate is **46/708 = 0.064972** (95% Wilson `[0.0491, 0.0856]`). That is **distinguishable from the ASYM_OBJ corner** (80/724 = 0.110497; z = −3.041, p = 0.0024) and **indistinguishable from the ASYM_NOOBJ corner** (42/796 = 0.052764; z = +1.007, p = 0.314). An arm that merely showed objectives without paying for them landed statistically on top of the arm that never showed objectives at all.

**The result is strange on its own terms, and that is the finding.** ASYM_OBJ scored objectives **twice in thirty matches** and never won a match on VP — and this arm shows that removing that nearly-never-paid payout removes ~79% of the effect it produced. A capture reward that essentially never fired was still doing most of the work. §6 states what that can and cannot mean; the arm cannot separate "a payout that pays" from "a payout that *could* pay", because it removes both — the pre-registration's H_CAPTURE was defined to include both, so this is scored, not smuggled.

**Seat asymmetry, reported because the pooled number hides it.** `g_blue = 0.0316` — blue, the seat carrying two-thirds of the whole objectives effect, reproduces the no-objectives corner almost exactly (1.028×, p = 0.906) and is decisively below its own objectives corner (0.545×, p = 0.0026). `g_red = 0.5831` — red keeps most of its much smaller effect (2.249× ASYM_NOOBJ, p = 0.068; 0.716× ASYM_OBJ, p = 0.323). The pre-registered SEAT-SPLIT clause is **not** triggered (it requires one seat `>= 0.65` while the other is `<= 0.35`; red is 0.5831). The pooled verdict is supported by blue decisively and by red only weakly, and §1a says so rather than averaging it away.

**Ledger:** `.onex_state/steel_onslaught/ugate_objdecoy_scored/` (`events.sqlite3`, `battery_raw.jsonl`), assembled from the source lanes named in §0b, all retained on disk under `.onex_state/steel_onslaught/` with their logs in `.onex_state/steel_onslaught/logs/`.

**Change under test:** exactly ONE field versus `foundry_60_asym_v1` — `objective_scoring: decoy`. The three objective cells, their `vp_per_round`, and `vp_threshold: 15` are all still declared and still rendered to the pilot. Loadouts, decks, over-deal quotas, utility handler pack, provider, retry (`max_attempts: 1`) and timeout are inherited unchanged and are asserted field-by-field in CI (`tests/contracts/test_objdecoy_overlay.py`).

**Engine-layer confirmation, read from this arm's own ledger (not from the overlay file):** all 30 `match_started` events carry `arena_id = foundry_60_asym_v1_decoyobj`, one single `arena_contract_hash` (`5ee78bd24e786beb764a2fe55dc402f32b83db38e4d73a303a99a5cb76cdf4fe`), `objective_scoring = decoy`, `vp_threshold = 15`, and **3 declared objective cells**. `weapon_fired` carries only stock, un-suffixed ids — `weapon.siege.artillery_mortar` 120, `weapon.light.machine_gun` 79, `weapon.heavy.harpoon_gun` 47, `weapon.light.shrapnel_thrower` 41 (287 total). Zero dose-ladder, range-cap or damage-variant ids appear.

**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, per-seed isolated process invocation.

---

## 0. Pre-registration (committed and merged before this battery ran)

From the header of `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml`. **Not one character of the criterion, the corners, the decision bands, or the escapes was edited by this session.**

| Event | Commit | Author timestamp (UTC) |
|---|---|---|
| Pre-registration authored (arm branch, pre-squash) | `7ab351b` | **2026-07-25T21:48:20Z** |
| Pre-registration on `main` (squash of PR #210, the commit the checker reads) | **`caf798b`** | **2026-07-25T22:02:58Z** |
| **First `match_started` of the scored battery** | — | **2026-07-25T22:12:08.947918Z** |
| Last `match_started` of the scored battery | — | 2026-07-25T22:26:47.733704Z |

`scripts/check_preregistration_timing.py` (merged in #207), run against the scored lane — quoted verbatim, exit 0:

```
Overlay:                    contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml
Pre-registration commit:    caf798bd0bce4e8d67078e8a5d2fa9122fea081e
  author timestamp:         2026-07-25T18:02:58-04:00   (load-bearing)
  committer timestamp:      2026-07-25T18:02:58-04:00
First match_started:        2026-07-25T22:12:08.947918+00:00
Gap (match_started - author date): 0:09:10.947918

OK: pre-registration commit's author timestamp precedes the first match_started.
```

The margin is **9 min 10.9 s** against the merged commit and **23 min 48.6 s** against the original authoring commit. Both orderings are checkable from two sources that cannot be back-dated together: the commit timestamps on the remote, and the ledger's own `emitted_at`.

> **PRE-REGISTERED CRITERION (quoted, not paraphrased).**
> `g_pooled = [(DECOY_red - 0.017588) + (DECOY_blue - 0.087940)] / 0.115467`
> `g_pooled >= 0.65` → GOAL-CONTEXT-ATTRIBUTABLE · `g_pooled <= 0.35` → CAPTURE-ATTRIBUTABLE · between → BOTH-CONTRIBUTE.
> Out-of-interval escapes, pre-declared and **unclamped**: `g_pooled < 0` → SUB-NOOBJ; `g_pooled > 1` → SUPER-OBJ.

### 0a. Fixed corners — independently recomputed from their own ledgers before scoring

Recomputed by this session's code from each corner's own `events.sqlite3`, and matching the pre-registration's quoted constants **exactly**, digit for digit:

| Corner | Ledger | red | blue |
|---|---|---|---|
| ASYM_OBJ | `ugate_surfacing_fix_battery` (SO-PROMPT-SURFACING worktree) | 20/362 = 0.055249 | 60/362 = 0.165746 |
| ASYM_NOOBJ | `ugate_scenobj_asym_noobj_battery_r3` (SO-SCEN-OBJ worktree) | 7/398 = 0.017588 | 35/398 = 0.087940 |

The same recompute reports `objective_scored = 2` on ASYM_OBJ and `0` on ASYM_NOOBJ, confirming the pre-registration's account of the corner it is reasoning from. The measurement applied to this arm is the corners' own measurement, not a new one.

### 0b. How the scored ledger was assembled, and what was discarded

The endpoint killed roughly one seed in ten during this run (`LlmTransportError` / `provider_error`, thrown mid-match at varying rounds — twice consecutively on seed 5012 at *different* match progress, so intermittent transport, not a seed-deterministic fault). Under the originally declared harness (one 30-seed lane, abandoned whole on any kill) the chance of ever producing a clean 30/30 lane was ~3%.

**Amendment 1** (`.onex_state/steel_onslaught/OBJDECOY_RUN_PLAN.md`, recorded **2026-07-25T22:20:16Z** — before any decoy keep-rate, per-seat rate or `g_pooled` had been computed from any decoy ledger) changed **the seeds-to-lanes mapping only**. Seeds run in batches of the still-missing seeds; when a lane dies, its completed seeds are kept and the remainder moves to a fresh `--state-root`. The scored ledger imports, mechanically:

> a match IF AND ONLY IF it produced a COMPLETED row in its lane's `battery_raw.jsonl`; where a seed completed in more than one lane, the LOWEST lane index wins.

No match was selected, dropped or re-run on the basis of any result it produced. Provenance of all 30:

| Source lane | Seeds contributed |
|---|---|
| `ugate_objdecoy_battery` | 5001–5009 (9) |
| `objdecoy_L1` | 5010, 5011 (2) |
| `objdecoy_L2` | none — killed on its only seed (5012) |
| `objdecoy_L3` | 5012–5030 (19) |

**This is stricter than the program's established practice, not looser.** SO-COMP-CA scored a lane holding 34 `match_started` for 30 completed rows, and `scripts/check_contamination_gate.py` was merged in #207 precisely to treat those 4 orphans as retry residue. This arm's scored ledger carries **zero** orphans: 30 `match_started`, 30 `match_ended`, 30 rows, bijective.

**Discarded, in full.** Three abandoned attempts left no completed row and contribute no event: seed 5010 in `ugate_objdecoy_battery`, seed 5012 in `objdecoy_L1`, seed 5012 in `objdecoy_L2`. Additionally, two lanes were created and deleted before any match completed, by a harness bug that put the run log *inside* the state-root the driver's `--fresh` wipes (destroying the first seed's error output); zero completed rows existed in either, and nothing from them reaches any number in this document. Lane `ugate_objdecoy_battery_r2`, started under the pre-amendment rule, only re-ran seeds already completed in lane 1 and contributes nothing; it is retained as residue.

---

## Method

Keep-rate is the method the pre-registration names and both corners use: for each seat, **dealt** = utility-partition card count summed over that seat's `hand_dealt` events; **programmed** = `plan_committed` register slots whose `card_id` starts `card.utility.`. This is *programmed*, not *deployed*; both are reported (§4).

A paired variant (each `hand_dealt` matched to the following `plan_committed` for the same `(match_id, seat)`) returns **identical** counts here — 14/354 red, 32/354 blue, **0 unpaired hands** — so the choice of variant is not load-bearing for this arm.

Statistics: two-proportion z-tests, 95% Wilson intervals. Card-level proportions are **clustered within matches**, so any p-value on the nominal denominator is anti-conservative; read them as a rank ordering of effect strength, never as calibrated evidence.

---

## 1. PRIMARY — the scored criterion

| Quantity | red | blue | pooled |
|---|---:|---:|---:|
| programmed / dealt | **14 / 354** | **32 / 354** | **46 / 708** |
| keep-rate | **0.039548** | **0.090395** | **0.064972** |
| 95% Wilson | [0.0237, 0.0653] | [0.0648, 0.1248] | [0.0491, 0.0856] |
| ASYM_OBJ corner | 0.055249 | 0.165746 | 0.110497 |
| ASYM_NOOBJ corner | 0.017588 | 0.087940 | 0.052764 |
| **g (fraction of the objectives effect surviving)** | **0.5831** | **0.0316** | **0.2115** |

```
numerator = (0.039548 - 0.017588) + (0.090395 - 0.087940) = 0.024416
g_pooled  = 0.024416 / 0.115467 = 0.2115
```

**Scoring.** `0.2115 <= 0.35` → **CAPTURE-ATTRIBUTABLE**. That is the pre-registered rule applied mechanically. `g_pooled` is inside `[0, 1]`, so neither out-of-interval escape (SUB-NOOBJ, SUPER-OBJ) fires and no clamping was needed or applied.

**All-card mechanical control:** 1770/3540 = **0.500000 exactly** (5 registers programmed from 10 cards dealt, every hand). The measurement's denominator machinery is behaving.

### 1a. Seat split (pre-declared, reported, not a second criterion)

| Comparison | ratio | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---|
| **blue** vs ASYM_OBJ | 0.545× | **−3.012** | **0.0026** | **Yes** |
| **blue** vs ASYM_NOOBJ | 1.028× | +0.118 | 0.906 | No |
| **red** vs ASYM_OBJ | 0.716× | −0.988 | 0.323 | No |
| **red** vs ASYM_NOOBJ | 2.249× | +1.824 | 0.068 | No |
| **pooled** vs ASYM_OBJ | 0.588× | **−3.041** | **0.0024** | **Yes** |
| **pooled** vs ASYM_NOOBJ | 1.231× | +1.007 | 0.314 | No |

**Blue is the whole pooled story.** Blue carries `d_obj_blue = 0.077806` of the total `0.115467` effect (67%), and blue's decoy rate is inside a hair of its no-objectives rate. Red keeps 58% of its own (much smaller, 0.037661) effect at p = 0.068 — suggestive, not significant at n = 30. The SEAT-SPLIT clause is **not** triggered (red 0.5831 is below the 0.65 boundary), so the pooled verdict stands as written; it is nonetheless supported *decisively* by only one of the two seats, and that is the honest reading.

---

## 2. MANIPULATION-LANDED GATE (pre-registered; passed before any scoring)

Every clause, read from this arm's own scored ledger:

| Pre-registered clause | Observed | Pass |
|---|---|---|
| `objective_scored` event count == 0 | **0** | yes |
| `vp_threshold` terminal count == 0 | **0** (all 30 terminals `elimination`) | yes |
| every `match_started` carries `arena_id foundry_60_asym_v1_decoyobj` | 30/30 | yes |
| arena_contract_hash recomputed from that contract | single hash `5ee78bd2…f4fe` on 30/30, asserted inline by the driver on every match | yes |
| the objectives block IS present in the pilot's prompt | see below | yes |

**Zero `objective_scored` is the runtime proof the flag landed** — it is the expected and required observation for this arm, not a null result. The engine emitted the event 2× in the ASYM_OBJ corner under identical geometry and identical seeds; here the same geometry emits it 0×.

**Objectives are visible to the pilot — three independent runtime readings:**

1. **The rendered observation, produced now through the real runner** on the shipped decoy arena (`steel_onslaught.llm.pilot._serialize_observation`, the same call site the live battery drives). Verbatim, from `foundry_60_asym_v1_decoyobj`:

   ```
   --- OBJECTIVES (hold a cell within 1, uncontested, to score; first to 15 VP wins) ---
   victory_points: you 0 vs enemy 0
     - objective.east_gate: cell=(42,36) vp_per_round=1 control=unclaimed your_distance=38
     - objective.north_works: cell=(30,22) vp_per_round=1 control=unclaimed your_distance=26
     - objective.west_yard: cell=(18,30) vp_per_round=1 control=unclaimed your_distance=14
   ```

   The same run reports the decoy prompt stream **byte-identical to the `foundry_60_asym_v1` (scoring) stream: True**, **byte-identical to the `foundry_60_asym_v1_noobj` stream: False**, and the decoy observation **385 characters longer** than the no-objectives observation at the identical match state. The no-objectives arena renders no such block at all.

2. **The pilots acted on it.** **266 of 354** `plan_committed` rationales in the scored ledger name an objective cell or the word "objective" (`objective` 213, `east gate` 95, `west_yard` 31, `north_works` 18, `west yard` 12, `vp` 12). Samples, verbatim from the ledger: *"Advance to secure east gate while maintaining fire capability."*, *"Storm west_yard objective with assault mode and advance, firing secondary weapon immediately."*, *"Advance to east gate while firing both weapons to secure objective VP."*

3. **Prompt size.** `user_prompt_length` over 382 completions: min 8227, mean 9207.0, max 10182 — carrying the block on every call.

The decoy is visible, believed, and acted upon. It simply never pays.

---

## 3. CONTAMINATION GATE (pre-registered)

`scripts/check_contamination_gate.py` (merged in #207), run against the scored lane — quoted verbatim, exit 0:

```
State root:                  .onex_state/steel_onslaught/ugate_objdecoy_scored
Expected seeds:               5001..5030 (n=30)
battery_raw.jsonl rows:       30
Distinct seeds:               30
Duplicate seeds:              0
Missing seeds (gaps):         0
Out-of-range seeds:           0
Duplicate match_id collisions: 0
Unfiltered ledger match_started: 30
Unfiltered ledger match_ended:   30
INFO -- orphaned match_started (retry residue, no match_ended): 0
Ledger match_ended vs battery_raw match_id sets bijective: yes

OK: battery_raw.jsonl holds exactly the 30 expected COMPLETED rows (seeds 5001..5030), no dupes, no gaps, and the ledger's completed-match set agrees with it.
```

(The `State root` line is shown repo-relative; the tool prints an absolute path.) The pre-registration's own stricter wording — "EXACTLY 30 `match_started` rows, 30 distinct `match_ids`, and seeds 5001-5030 each exactly once" — is satisfied literally: 30, 30, and each seed once.

---

## 4. Secondary — utility deployment, terminal mix, health (pre-declared, NOT scored)

| Measure | DECOY (this arm) | ASYM_OBJ | ASYM_NOOBJ |
|---|---:|---:|---:|
| `utility_deploy_intent` → `utility_deployed` | 40 → **40** | 72 → 72 | 36 → 36 |
| `objective_scored` | **0** | 2 | 0 |
| terminals | 30 `elimination` | 29 `elimination` | 29 `elimination` |
| winners | **blue 30/30** | blue 29/29 | blue 29/29 |
| `weapon_fired` total | 287 | 304 | 348 |
| `llm_completion_failed` | 28 / 382 requested | 18 / 380 | 23 / 421 |

Every programmed utility card that reached resolution deployed (40/40). Programmed utility mix: smoke 34, chaff 10, flares 2; deployed: smoke 30, chaff 9, flares 1. The deployment counts track the keep-rate ordering (72 > 40 > 36) rather than contradicting it.

**O-GATE:** `play_terminal_fraction = 1.0000` (30/30 terminals on play, threshold 0.95) — **passes**. Zero aborts, zero timeouts, zero tick-cap terminals. Match length: min 9, median 29.0, mean 27.63, max 51 ticks. In-match `invalid_response` retries: 9 matches with 0, 16 with 1, 3 with 2, 2 with 3 — the same class and comparable rate as both corners.

---

## 5. Verdict

**CAPTURE-ATTRIBUTABLE.** `g_pooled = 0.2115`, inside the pre-registered `<= 0.35` band. Between the two rival mechanisms the pre-registration named:

- **H_CAPTURE is supported.** Removing the payout while holding the goal context byte-identical removed ~79% of the measured objectives effect, and left the arm statistically indistinguishable from the no-objectives corner (p = 0.314) while distinguishable from the objectives corner (p = 0.0024).
- **H_GOALCTX is not refuted to zero.** ~21% survives pooled, and red's 58% survival (p = 0.068) is the part of the effect that a stated goal alone appears to carry. The arm places the split at roughly one-fifth goal context, four-fifths payout — it does not license "goal context does nothing".

---

## 6. Limitations

- **The arm removes the payout's *realization* and its *reachability* together, and cannot separate them.** No VP accrues, no scoreboard moves, and no VP victory is attainable. The pre-registration defined H_CAPTURE to include both ("VP actually accruing … and the ever-present possibility of more"), so this is inside the scored hypothesis — but the finding must not be narrated as "realized capture caused it". The stronger and stranger reading is the live one: **the corner it is compared against realized capture only twice in thirty matches, so what this arm mostly removed was a possibility, not an income stream.** Separating "a reachable but unrealized payout" from "a realized payout" needs a further arm (e.g. objectives that pay but are placed out of reach), and is not asserted here.
- **The pooled verdict rests on one seat.** Blue reproduces ASYM_NOOBJ (1.028×, p = 0.906); red retains 2.249× ASYM_NOOBJ at p = 0.068. The formal SEAT-SPLIT clause did not trigger, but a reader who wants the mechanism rather than the label should read §1a, not the headline.
- **The blue standoff (OMN-15119 disclosure class) is inherited unchanged and deliberately.** Blue's stock `qwen35/sniper_ironclad.yaml` carries `weapon.siege.artillery_mortar` (range 50) and `weapon.heavy.harpoon_gun` (range 30) against red's range-12 machine gun and range-8 shrapnel thrower — an uncontrolled ~18–38 cell range advantage. Blue won **30/30** here, 29/29 in ASYM_NOOBJ and 29/29 in ASYM_OBJ. All three corners carry the identical loadout pairing, so the standoff is constant and cannot generate the measured difference; it is disclosed so no reader assumes it was controlled, and every win-rate and terminal figure in §4 must be read against it.
- **`objective_scored = 0` is expected by construction and is not evidence of pilot blindness.** It is the runtime proof that the flag landed. The evidence that the pilots were *not* blind is separate and is in §2 (rendered observation, 266/354 rationales, prompt length).
- **The prompt is byte-identical to ASYM_OBJ's except for a ≤2-event tail**, exactly as the pre-registration disclosed: ASYM_OBJ recorded 2 `objective_scored` events, so in at most 2 of its 30 matches the VP scoreboard moved off 0-0 and this arm's never did.
- **The scored ledger is assembled from three lanes** under Amendment 1 (§0b). Every match in it ran the same overlay, arena and expected-hash assertion, and each seed appears exactly once, but the matches were not all produced by a single uninterrupted driver process. The amendment was recorded before any decoy keep-rate was computed and changes no scored quantity; a reader who rejects assembly on principle should read this as three lanes' worth of the same arm rather than as one.
- **n = 30 does not support a claim stronger than the pre-registered label.** `red` vs ASYM_NOOBJ at p = 0.068 is the load-bearing sub-comparison for the surviving 21%, and it is not significant. Card-level proportions are clustered within matches, so the quoted p-values are anti-conservative.
- **One model, one arena, one seed set.** Qwen3.6-35B-A3B on both seats, `foundry_60_asym_v1_decoyobj`, seeds 5001–5030. The corners share the model, the seeds and the geometry, which is what makes the single-lever comparison clean — and equally what limits it to this configuration.
- **Endpoint kills were frequent during this run** (~1 seed in 10) and are disclosed in §0b with their per-seed provenance. They are outcome-blind by construction: a killed seed produced no row, and every kill was recorded before any keep-rate existed.

---

## Citations (all relative paths)

- This arm's scored ledger: `.onex_state/steel_onslaught/ugate_objdecoy_scored/events.sqlite3`, `.onex_state/steel_onslaught/ugate_objdecoy_scored/battery_raw.jsonl` (30 rows, seeds 5001–5030).
- Source lanes and logs: `.onex_state/steel_onslaught/ugate_objdecoy_battery/`, `.onex_state/steel_onslaught/objdecoy_L1/`, `.onex_state/steel_onslaught/objdecoy_L2/`, `.onex_state/steel_onslaught/objdecoy_L3/`, logs under `.onex_state/steel_onslaught/logs/`; run plan and Amendment 1: `.onex_state/steel_onslaught/OBJDECOY_RUN_PLAN.md`.
- Pre-registration: `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml`, authored `7ab351b` (2026-07-25T21:48:20Z), merged as `caf798b` (2026-07-25T22:02:58Z, PR #210), both preceding the first `match_started` at 2026-07-25T22:12:08.947918Z.
- Method gates, both run against the scored lane and quoted above at exit 0: `scripts/check_preregistration_timing.py`, `scripts/check_contamination_gate.py` (merged in #207).
- Arena under test: `contracts_data/arenas/foundry_60_asym_v1_decoyobj.yaml`; comparison arenas `contracts_data/arenas/foundry_60_asym_v1.yaml`, `contracts_data/arenas/foundry_60_asym_v1_noobj.yaml`.
- Mechanism: `src/steel_onslaught/contracts/arena.py` (`objective_scoring`), `src/steel_onslaught/match/fold.py` (payout suppression), `src/steel_onslaught/match/composition.py`, `src/steel_onslaught/events/payloads.py`. Mechanism tests: `tests/contracts/test_objdecoy_overlay.py`, `tests/match/test_objective_scoring_decoy.py` (36 tests, green locally and in CI on PR #210).
- Objectives corner (ASYM_OBJ): `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`, ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` (SO-PROMPT-SURFACING worktree), independently recomputed here.
- No-objectives corner (ASYM_NOOBJ): `docs/evidence/2026-07-25-scenobj-asym-noobj-battery.md`, ledger `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r3/events.sqlite3` (SO-SCEN-OBJ worktree), independently recomputed here.
- Battery driver: `scripts/run_ogate_objectives_battery.py` (non-zero exit on any skipped seed, #204).
- No secrets, keys, or absolute paths included.
