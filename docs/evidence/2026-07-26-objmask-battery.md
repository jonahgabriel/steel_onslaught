# SO-OBJ-MASK Arm (objectives SCORED, display masked — `objective_display: masked`) Battery — 2026-07-26

**Verdict: DISPLAY-NECESSARY**, with an out-of-interval **SUB-NOOBJ** technical reading that is, on its own numbers, statistically indistinguishable from zero. The pre-registered statistic is `m_pooled = -0.0218` — below the pre-registered `0` floor by a margin the data cannot support (`z = -0.11`, `p = 0.91` vs the no-objectives corner). With the DISPLAY removed and the payout held byte-identical to the paying-visible corner, **~0% of the measured objectives effect survives; masking the view removes the effect entirely, regardless of what the engine is doing behind the scenes.**

**The comparison that carries it.** Pooled utility keep-rate is **41/796 = 0.051508** (95% Wilson `[0.0382, 0.0691]`). That is **decisively distinguishable from the ASYM_OBJ corner** (80/724 = 0.110497; z = -4.24, p < 0.0001) and **statistically indistinguishable from the ASYM_NOOBJ corner** (42/796 = 0.052764; z = -0.11, p = 0.910). This is the live-stakes complement to SO-OBJ-DECOY (PR #210/#212, `docs/evidence/2026-07-25-objdecoy-asym-battery.md`): DECOY held the pilot's VIEW fixed and removed the payout, landing at 21% of the objectives effect surviving (CAPTURE-ATTRIBUTABLE). This arm holds the PAYOUT fixed — the engine paid real VP, 14 `OBJECTIVE_SCORED` events fired in this battery's own ledger, more than the paying corner's own 2 — and removes only the DISPLAY. It lands at ~0% surviving. The two arms together bracket the effect from both directions: display alone (DECOY) carries ~21% of it; payout alone, invisible (this arm), carries ~0% of it.

**The result completes the finding cleanly, and it is the boring outcome the pre-registration predicted.** Unlike DECOY (where either hypothesis was a live, physically plausible outcome), this arm's own pre-registration named the mechanically expected result before the battery ran: an LLM pilot's policy is a pure function of its prompt, there is no in-context reward channel from a VP total it is never told, and `objective_display: masked` makes the observation structurally identical to an objective-free arena's for the whole match. `m_pooled ≈ 0` is not a surprising finding here — it is what the engineering predicted, now measured. What is worth reporting is *how* prompted the result is: not a rough collapse toward zero but an almost exact reproduction of ASYM_NOOBJ's own numbers — blue's masked rate (35/398) is the identical fraction to blue's no-objectives rate (35/398), digit for digit.

**Ledger:** `.onex_state/steel_onslaught/ugate_objmask_battery/` (`events.sqlite3`, `battery_raw.jsonl`), single uninterrupted lane, no amendment, no lane assembly — unlike DECOY's three-lane assembly (§0b of that doc), this battery ran end to end in one `--fresh` invocation with 0 skipped seeds.

**Change under test:** exactly ONE field versus `foundry_60_asym_v1` — `objective_display: masked`. The three objective cells, their `vp_per_round`, and `vp_threshold: 15` are all still declared and the fold still scores them exactly as on the source arena (`objective_scoring` left at its shipped default, `"scoring"`). Loadouts, decks, over-deal quotas, utility handler pack, provider, retry (`max_attempts: 1`) and timeout are inherited unchanged and are asserted field-by-field in CI (`tests/contracts/test_objmask_overlay.py`).

**Engine-layer confirmation, read from this arm's own ledger:** all 30 `match_started` events carry `arena_id = foundry_60_asym_v1_objmask`, one single `arena_contract_hash` (`c579ffc91e11685c8ed5cb2b03234ae96bb011e4fa748fbccad3a2c10c9dfa3a`), `objective_display = masked`, `vp_threshold = 15`, 3 declared objective cells, and **`objective_scoring` absent from the recorded snapshot** (its default, "scoring" — the engine paid). **14 `OBJECTIVE_SCORED` events fired across 5 matches** — real VP genuinely accrued (see §2). `weapon_fired` carries only stock, un-suffixed ids — `weapon.siege.artillery_mortar` 145, `weapon.light.machine_gun` 86, `weapon.heavy.harpoon_gun` 55, `weapon.light.shrapnel_thrower` 30 (316 total). Zero dose-ladder, range-cap or damage-variant ids appear.

**Model:** live Qwen3.6-35B-A3B, both seats, keyless. n = 30, seeds 5001–5030, single-lane run (`--fresh`, 0 skipped seeds — the driver's own non-zero-exit-on-skip gate, #204, was not triggered).

---

## 0. Pre-registration (committed before this battery ran)

From the header of `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_objmask_qwen.yaml`. Not one character of the criterion, the corners, the decision bands, or the escapes was edited by this session after the pre-registration commit.

| Event | Commit | Author timestamp |
|---|---|---|
| Pre-registration commit (`feat(SO-OBJ-MASK)`, this branch) | `18c3d0e7c9fc89f1d05e0ce6cab8d7d03e0dad65` | **2026-07-25T19:52:49-07:00** (2026-07-26T02:52:49Z) |
| **First `match_started` of the battery** | — | **2026-07-26T02:53:08.636315Z** |

`scripts/check_preregistration_timing.py` (merged in #207), run against this lane — quoted verbatim, exit 0:

```
Overlay:                    contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_objmask_qwen.yaml
Pre-registration commit:    18c3d0e7c9fc89f1d05e0ce6cab8d7d03e0dad65
  author timestamp:         2026-07-25T19:52:49-07:00   (load-bearing)
  committer timestamp:      2026-07-25T19:52:49-07:00
First match_started:        2026-07-26T02:53:08.636315+00:00
Gap (match_started - author date): 0:00:19.636315

OK: pre-registration commit's author timestamp precedes the first match_started.
```

The margin is **19.6 seconds** — tighter than DECOY's own margins because this arm's mechanism required no live-endpoint queueing wait before launch (the endpoint was probed healthy and the battery was launched immediately after the commit landed). Both the commit hash and the ledger's own `emitted_at` are independently checkable from sources that cannot be back-dated together.

> **PRE-REGISTERED CRITERION (quoted, not paraphrased).**
> `m_pooled = [(MASK_red - 0.017588) + (MASK_blue - 0.087940)] / 0.115467`
> `m_pooled >= 0.65` → HIDDEN-INCENTIVE-ATTRIBUTABLE · `m_pooled <= 0.35` → DISPLAY-ATTRIBUTABLE · between → BOTH-CONTRIBUTE.
> Out-of-interval escapes, pre-declared and **unclamped**: `m_pooled < 0` → SUB-NOOBJ; `m_pooled > 1` → SUPER-OBJ.

### 0a. Fixed corners — reused verbatim from the DECOY pre-registration, not re-derived

Quoted from `docs/evidence/2026-07-25-objdecoy-asym-battery.md` §0a, itself independently recomputed from each corner's own ledger and matching prior publication exactly:

| Corner | Ledger | red | blue |
|---|---|---|---|
| ASYM_OBJ | `ugate_surfacing_fix_battery` | 20/362 = 0.055249 | 60/362 = 0.165746 |
| ASYM_NOOBJ | `ugate_scenobj_asym_noobj_battery_r3` | 7/398 = 0.017588 | 35/398 = 0.087940 |

`d_obj_red = 0.037661`, `d_obj_blue = 0.077806`, `d_obj_pooled = 0.115467` — unchanged from DECOY's own arithmetic. This session did not re-open either corner's ledger; the constants are cited, not re-measured, exactly as the pre-registration commits to.

### 0b. No lane assembly — a genuine difference from DECOY's own §0b

DECOY's battery lost seeds to endpoint kills and required a three-lane assembly under a recorded amendment (`docs/evidence/2026-07-25-objdecoy-asym-battery.md` §0b). This battery's single `--fresh` invocation completed all 30 seeds without a kill: `battery_summary.json` reports `"skipped_seeds": []`, `"requested_n": 30`, `"n": 30`. No amendment was needed and none was recorded.

---

## Method

Keep-rate is the method the pre-registration names and every corner in this family uses: for each seat, **dealt** = utility-partition card count summed over that seat's `hand_dealt` events; **programmed** = `plan_committed` register slots whose `card_id` starts `card.utility.`.

A paired variant (each `hand_dealt` matched to the following `plan_committed` for the same `(match_id, seat)`) returns **identical** counts here — 6/398 red, 35/398 blue, **0 unpaired hands** — so the choice of variant is not load-bearing.

Statistics: two-proportion z-tests, 95% Wilson intervals. Card-level proportions are **clustered within matches**, so any p-value on the nominal denominator is anti-conservative; read them as a rank ordering of effect strength, never as calibrated evidence.

---

## 1. PRIMARY — the scored criterion

| Quantity | red | blue | pooled |
|---|---:|---:|---:|
| programmed / dealt | **6 / 398** | **35 / 398** | **41 / 796** |
| keep-rate | **0.015075** | **0.087940** | **0.051508** |
| 95% Wilson | [0.0069, 0.0325] | [0.0639, 0.1198] | [0.0382, 0.0691] |
| ASYM_OBJ corner | 0.055249 | 0.165746 | 0.110497 |
| ASYM_NOOBJ corner | 0.017588 | 0.087940 | 0.052764 |
| **m (fraction of the objectives effect surviving)** | **-0.0667** | **0.0000** | **-0.0218** |

```
numerator = (0.015075 - 0.017588) + (0.087940 - 0.087940) = -0.002513
m_pooled  = -0.002513 / 0.115467 = -0.0218
```

**Scoring, applied mechanically.** `m_pooled = -0.0218 < 0` triggers the pre-registered **out-of-interval escape → SUB-NOOBJ**, not the ordinary `<= 0.35` band, per the disjunctive rule's own priority (the escape is written to handle exactly this case — a component landing outside the ordinary interpretive frame — and is reported qualitatively rather than folded into the 0–1 scale). Read honestly rather than mechanically: the excursion is a single card's worth of signal at n=398 (`6` programmed vs `7` on the reference NOOBJ ledger) and blue's own rate is not merely close to its NOOBJ counterpart but **numerically identical** (35/398 both). `MASK pooled vs ASYM_NOOBJ pooled`: z = -0.11, p = 0.910 — indistinguishable from zero at any sane reading. **SUB-NOOBJ is the technically correct label under the pre-registered rule; DISPLAY-NECESSARY is the honest qualitative one, and the two do not disagree about what happened** — masking the display removed the entire measured effect, with no directional residual big enough to read as anything.

**All-card mechanical control:** 1990/3980 = **0.500000 exactly** (5 registers programmed from 10 cards dealt, every hand). The measurement's denominator machinery is behaving.

### 1a. Seat split (pre-declared, reported, not a second criterion)

| Comparison | ratio | z | p (two-sided) | Significant at α=0.05? |
|---|---:|---:|---:|---|
| **red** vs ASYM_OBJ | 0.273× | **-3.043** | **0.0023** | **Yes** |
| **red** vs ASYM_NOOBJ | 0.857× | -0.280 | 0.780 | No |
| **blue** vs ASYM_OBJ | 0.531× | **-3.239** | **0.0012** | **Yes** |
| **blue** vs ASYM_NOOBJ | 1.000× | 0.000 | 1.000 | No |
| **pooled** vs ASYM_OBJ | 0.466× | **-4.244** | **<0.0001** | **Yes** |
| **pooled** vs ASYM_NOOBJ | 0.976× | -0.113 | 0.910 | No |
| **pooled vs DECOY pooled** (46/708 = 0.064972) | 0.793× | -1.116 | 0.264 | No |

**Both seats land on the same side of the story.** Neither seat crosses the SEAT-SPLIT boundary condition (`one >= 0.65 while the other <= 0.35`); both are decisively below the paying corner and statistically indistinguishable from the no-objectives corner. This is a cleaner pooled/seat agreement than DECOY's own arm managed (DECOY's pooled verdict rested mostly on blue alone, red at p = 0.068). Here both seats independently confirm the same reading.

---

## 2. MANIPULATION-LANDED GATE

Two independent checks, adapted from the pre-registration for the reason stated there: DECOY's own gate (an engine-side event count forced to zero) proves the wrong half of this arm's claim, since this arm's engine is deliberately unchanged.

### 2a. PAYOUT LIVE — proven pre-battery in CI, confirmed live in this battery's own ledger

Pre-battery (unaffected by any live-battery contingency): `tests/match/test_objective_scoring_masked.py::test_masked_match_scores_normally_and_never_shows_objectives` drives a real match on `objective_display: masked` through the real runner to a genuine `VICTORY_DECLARED`/`vp_threshold` terminal with `vp_totals == {"player.a": 4, "player.b": 0}` — the identical terminal `test_objective_match_e2e.py`'s visible twin reaches, through the same `MatchStateFold` code path.

Live, from this battery's own ledger: **14 `OBJECTIVE_SCORED` events fired across 5 of 30 matches** (`objective.east_gate` 6 awards / 2 matches / 1 control change, `objective.north_works` 5 awards / 1 match, `objective.west_yard` 3 awards / 2 matches) — **more raw capture events than the ASYM_OBJ corner's own 2** (PR #212 §0a), on identical geometry. No match reached the 15-VP threshold (0 `vp_threshold` terminals — 29/30 ended `elimination`, 1 `abort` on a `provider_semantic_failure`, seed 5022, `malformed_json` after 3 attempts), matching ASYM_OBJ's own observed pattern (0 VP terminals in its own 30 matches) — VP victories are rare on this geometry regardless of display, because blue's uncontrolled range advantage (§6) usually ends the match by elimination first. Interestingly, 13 of 14 capture events were credited to `player.red` — the side that goes on to lose every decided match (`brawler.wins = 0`, `winners.player.blue = 29`) — the losing side still fought for and held objectives it was never told existed.

### 2b. DISPLAY SUPPRESSED — a pre-registered clause the ledger cannot literally execute, disclosed and substituted

The pre-registration's clause (a) called for "a direct string search over the ledger this arm actually ran on" against `"OBJECTIVES"`, `"vp_per_round"`, `"vp_threshold"`, `"own_vp"`, `"enemy_vp"`, `"victory_points"`, or an `"objective."` id prefix appearing in any recorded prompt. **That check cannot be executed as literally written**: `llm_completion_requested`/`_resolved`/`_failed` events in this program's event schema record only `system_prompt_length`/`user_prompt_length` (or `prompt_tokens`/`completion_tokens`) — the raw prompt/response TEXT is never persisted to the canonical ledger, by design, for every arm in this program including the corners this arm is compared against. This is disclosed here as a gap in the literal pre-registered wording, not smoothed over.

**Substitute proof, stronger than the literal clause would have been.** The literal clause would have been a *sample-based* check over one battery's worth of recorded prompts. What is available instead is an *exhaustive, structural* proof: `ModelSOPilotObservation.objectives`/`.victory_points` are set exactly once, at match construction (`MatchRunner.__init__`, `src/steel_onslaught/match/runner.py`), as a pure function of `self._arena.objective_display` — never of tick, trajectory, seed, or LLM output. `tests/match/test_objective_scoring_masked.py::test_masked_match_scores_normally_and_never_shows_objectives` asserts `observation.objectives == ()` and `observation.victory_points is None` for **every** observation across a real match that reaches a genuine VP-threshold victory (including the exact tick VP crosses the finish line) — proving there is no live match on a masked arena, on any seed, under any trajectory, that could ever render the block. Both serializers (`steel_onslaught.llm.pilot._serialize_observation`, `steel_onslaught.llm.programming._serialize_programming_observation`) gate the block on exactly these two fields (`if obs.objectives and obs.victory_points is not None:` / `if pilot.objectives and pilot.victory_points is not None:`), so the field-level guarantee is sufficient for the prompt-level claim.

**A weaker, indirect corroboration from this battery's own recorded lengths**, reported because it is available, not because it is load-bearing: `user_prompt_length` over the 422 full-observation completions (2 tiny 313-character retry-repair prompts excluded — `steel_onslaught.llm.programming._serialize_repair_observation` never carries an objectives key on any arm) reads min 7092, mean 8236.3, max 9239 — materially shorter than DECOY's own reported 9207.0-mean/8227-min for its (visible) prompts. This is consistent with the block's absence but is **not a controlled same-match-state comparison** (different terrain and card counts also move prompt length) and is reported only as a secondary sanity check, not as the manipulation-landed proof.

Every `match_started` row carries `arena_id foundry_60_asym_v1_objmask` and the single recomputed `arena_contract_hash` (30/30, checked inline by the driver on every match).

---

## 3. CONTAMINATION GATE (pre-registered)

`scripts/check_contamination_gate.py` (merged in #207), run against this lane — quoted verbatim, exit 0:

```
State root:                  .onex_state/steel_onslaught/ugate_objmask_battery
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

(The `State root` line is shown repo-relative; the tool prints an absolute path.) 30, 30, each seed once — no assembly, no discard, no amendment.

---

## 4. Secondary — utility deployment, terminal mix, health (pre-declared, NOT scored)

| Measure | MASK (this arm) | ASYM_OBJ | ASYM_NOOBJ | DECOY |
|---|---:|---:|---:|---:|
| `utility_deploy_intent` → `utility_deployed` | 39 → **39** | 72 → 72 | 36 → 36 | 40 → 40 |
| `objective_scored` | **14** | 2 | 0 | 0 |
| terminals | 29 `elimination`, 1 `abort` | 29 `elimination` | 29 `elimination` | 30 `elimination` |
| winners | blue 29/29 decided, 1 draw (abort) | blue 29/29 | blue 29/29 | blue 30/30 |
| `weapon_fired` total | 316 | 304 | 348 | 287 |
| `llm_completion_failed` | 26 / 424 requested | 18 / 380 | 23 / 421 | 28 / 382 |

Every programmed utility card that reached resolution deployed (39/39).

**O-GATE:** `play_terminal_fraction = 0.9667` (29/30 terminals on play, threshold 0.95) — **passes**. One `abort` (seed 5022, `provider_semantic_failure`, `malformed_json` after 3 bounded reprompt attempts — a live provider boundary failure, the class the semantic-retry design classifies rather than silently retries forever). Match length: min 6, median 28.5, mean 30.27, max 57 ticks. `all_replay_valid: true` for every scored match — the replay-validity hard gate held on all 29 non-aborted terminals.

---

## 5. Verdict

**DISPLAY-NECESSARY** (technical label under the pre-registered rule: **SUB-NOOBJ**, an out-of-interval reading the pre-registration explicitly declined to clamp). Between the two rival mechanisms the pre-registration named:

- **H_DISPLAY_NECESSARY is supported, decisively.** With the objectives/VP view withheld from the prompt while the payout accrued exactly as it does on the shipped scoring arena — real `OBJECTIVE_SCORED` events, 7x more of them than the paying corner recorded on the same geometry — keep-rate collapsed to statistically indistinguishable from the no-objectives corner (pooled p = 0.910) and stayed decisively below the paying corner (pooled p < 0.0001). Blue's masked rate reproduces its no-objectives rate exactly, 35/398 both ways.
- **H_HIDDEN_TRACKS is not supported at all.** There is no reading of this data — pooled, per-seat, or the raw numerator — under which the real, invisible payout moved drafting toward the paying corner. `m_pooled` sits at the SUB-NOOBJ floor rather than anywhere on the positive interval the hidden-incentive hypothesis would need.

**Read together with SO-OBJ-DECOY, the pair answers the §5 question directly.** DECOY (payout removed, display kept) found ~21% of the objectives effect survives on display alone. This arm (display removed, payout kept) finds ~0% survives on payout alone. Visible feedback — not the ground-truth incentive structure the engine actually enforces — is the necessary and (on this evidence) close to sufficient channel through which "objectives" changed this model's utility-card drafting. An LLM pilot responds to what it is told, not to what is true.

---

## 6. Limitations

- **The pre-registered manipulation-landed clause (2b) could not be executed as literally written** — the event ledger never persists raw prompt text on any arm in this program, a fact discovered during this arm's own analysis rather than anticipated in the pre-registration. The substitute (an exhaustive, code-level proof that the observation fields the serializers gate on are unconditionally empty on a masked arena, proven across a full real match including its VP-scoring tick) is logically stronger than the sample-based grep the pre-registration called for, but it is a different check than the one that was promised in advance, and that gap is recorded here rather than silently closed.
- **`m_pooled` landed in the out-of-interval SUB-NOOBJ band rather than the ordinary `<=0.35` band**, by a margin (`-0.0218`) the data cannot statistically distinguish from zero (p = 0.910 vs the corner it nominally undershoots). The pre-registration commits to reporting this qualitatively rather than clamping it, and this document does so: the qualitative reading (visible feedback is necessary; the hidden payout contributes nothing measurable) is the same whichever side of exactly zero the point estimate falls on, but a reader who wants the literal label rather than the honest one should use SUB-NOOBJ, not DISPLAY-ATTRIBUTABLE.
- **The prompt-length secondary check (§2b) is not a controlled same-match-state comparison** — unlike DECOY's own byte-identical-prompt proof (which held match state fixed and diffed the resulting prompt directly), this arm's length numbers come from a genuinely different battery with its own terrain traversal and card sequencing, so the ~970-character gap versus DECOY's reported mean is suggestive, not dispositive; the CI-level structural proof (§2b, primary) does not share this weakness.
- **This battery ran a single clean lane with zero endpoint kills** — a genuine, disclosed difference from DECOY's three-lane assembly, not something arranged; the endpoint happened not to drop a seed this run. Nothing about the criterion or the method depends on this.
- **One `abort` terminal** (seed 5022, `provider_semantic_failure`) reduces the decided-match count to 29/30 for winner/terminal reporting, but is included in full in the keep-rate denominator (its `hand_dealt`/`plan_committed` events up to the point of failure are real, recorded rounds, not synthetic).
- **The blue standoff (OMN-15119 disclosure class) is inherited unchanged and deliberately**, identical to every sibling in this family: blue's stock `qwen35/sniper_ironclad.yaml` carries `weapon.siege.artillery_mortar` (range 50) and `weapon.heavy.harpoon_gun` (range 30) against red's range-12 machine gun and range-8 shrapnel thrower. Blue won 29/29 decided matches here, consistent with every corner. All corners carry the identical loadout pairing, so the standoff is constant and cannot generate the measured difference.
- **n = 30 does not support a claim stronger than the pre-registered verdict label.** Card-level proportions are clustered within matches, so the quoted p-values are anti-conservative in the direction of overstating significance; the near-zero point estimate and the wide-enough-to-contain-zero comparisons are the honest read, not a razor-thin significant result.
- **One model, one arena, one seed set.** Qwen3.6-35B-A3B on both seats, `foundry_60_asym_v1_objmask`, seeds 5001–5030. The corners share the model, the seeds and the geometry, which is what makes the single-lever comparison clean — and equally what limits it to this configuration.

---

## Citations (all relative paths)

- This arm's ledger: `.onex_state/steel_onslaught/ugate_objmask_battery/events.sqlite3`, `.onex_state/steel_onslaught/ugate_objmask_battery/battery_raw.jsonl` (30 rows, seeds 5001–5030), `.onex_state/steel_onslaught/ugate_objmask_battery/battery_summary.json`; driver log `.onex_state/steel_onslaught/logs/objmask_battery.log`.
- Pre-registration: `contracts_data/overlays/tactical_split_overdeal_utility_asym_v1_objmask_qwen.yaml`, commit `18c3d0e7c9fc89f1d05e0ce6cab8d7d03e0dad65` (2026-07-25T19:52:49-07:00), preceding the first `match_started` at 2026-07-26T02:53:08.636315Z.
- Method gates, both run against this lane and quoted above at exit 0: `scripts/check_preregistration_timing.py`, `scripts/check_contamination_gate.py` (merged in #207).
- Arena under test: `contracts_data/arenas/foundry_60_asym_v1_objmask.yaml`; comparison arenas `contracts_data/arenas/foundry_60_asym_v1.yaml`, `contracts_data/arenas/foundry_60_asym_v1_noobj.yaml`.
- Mechanism: `src/steel_onslaught/contracts/arena.py` (`objective_display`, `SOObjectiveDisplay`), `src/steel_onslaught/match/runner.py` (`MatchRunner.__init__`'s `_observation_objectives`/`_observation_vp_threshold`, and its three `build_pilot_observation`/`ReducerPilotTick` call sites). `src/steel_onslaught/match/fold.py` is UNCHANGED by this field — the whole point of the arm. Mechanism tests: `tests/contracts/test_objmask_overlay.py`, `tests/match/test_objective_scoring_masked.py` (13 tests, green locally and in CI on this PR).
- The live-stakes complement: `docs/evidence/2026-07-25-objdecoy-asym-battery.md` (SO-OBJ-DECOY, PR #210/#212), whose fixed corners this arm reuses verbatim in §0a.
- Objectives corner (ASYM_OBJ): `docs/evidence/2026-07-23-utility-surfacing-fix-remeasure.md`, ledger `.onex_state/steel_onslaught/ugate_surfacing_fix_battery/events.sqlite3` — cited via DECOY's own recompute, not re-opened by this session.
- No-objectives corner (ASYM_NOOBJ): `docs/evidence/2026-07-25-scenobj-asym-noobj-battery.md`, ledger `.onex_state/steel_onslaught/ugate_scenobj_asym_noobj_battery_r3/events.sqlite3` — cited via DECOY's own recompute, not re-opened by this session.
- Battery driver: `scripts/run_ogate_objectives_battery.py` (non-zero exit on any skipped seed, #204) — not triggered this run (0 skipped seeds).
- No secrets, keys, or absolute paths included.
