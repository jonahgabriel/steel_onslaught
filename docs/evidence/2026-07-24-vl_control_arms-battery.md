# Vision-Representation Control Arms — Blank Image vs. Text Padding, n=30 Matched Seeds (2026-07-24)

**Verdict: hypothesis (A) — image-content-specific degradation — is REFUTED. Hypothesis (B) — generic, modality-agnostic prompt-length dilution — is also REFUTED as originally framed. The data point to a third mechanism: the collapse is specific to the image/multi-part message CHANNEL, not to what the image depicts and not to token count in the abstract.**

This document follows up PR #187 (`docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md`), which found V-IMG's red (brawler) win rate collapses from V-TEXT's 46.67% to 0.00% when an identical deterministic per-tick PNG is attached to the prompt, but left two competing explanations undistinguished: (A) the image content actively misleads spatial reasoning, or (B) the ~2.3x prompt-token increase from the image is a generic length/attention-dilution effect that any equivalent-cost payload would cause.

Two control arms were run, both matched-seed (5001–5030) against V-TEXT and V-IMG:

- **V-IMG-BLANK**: identical to V-IMG except the attached PNG is a flat mid-grey image of the **same pixel dimensions** and PNG encoding, carrying **zero** observation-dependent content (no grid, no cells, no shapes). Isolates image *presence* from image *content*.
- **V-TEXT-PADDED**: identical to V-TEXT (no image at all) except the persona's system prompt carries a deterministic, clearly-marked, semantically inert filler block calibrated to match V-IMG's mean `prompt_tokens` overhead. Isolates prompt *length* from image *presence*.

**Results:**

| Arm | Red win rate | 95% Wilson CI | Mean `prompt_tokens` |
|---|---:|---:|---:|
| V-TEXT (PR #187) | 14/30 = 0.4667 | [0.3023, 0.6386] | 1033.0 |
| V-IMG (PR #187) | 0/30 = 0.0000 | [0.0000, 0.1135] | 2352.7 |
| **V-IMG-BLANK** | **0/30 = 0.0000** | **[0.0000, 0.1135]** | **2349.4** |
| **V-TEXT-PADDED** | **29/30 = 0.9667** | **[0.8333, 0.9941]** | **2354.3** |

- **V-IMG-BLANK is statistically indistinguishable from V-IMG.** Matched-seed comparison: **zero flips in either direction across all 30 seeds** (blue wins all 30 in both arms), sign-test p=1.0. A content-free image of matched pixel dimensions reproduces V-IMG's collapse **exactly**, seed-for-seed. This decisively refutes hypothesis (A): the model is not being misled by what the image depicts, because there is nothing task-relevant in it to be misled by.
- **V-TEXT-PADDED does not reproduce V-IMG's pattern at all — it moves in the opposite direction, further than V-TEXT's own baseline.** Red wins 29/30 (96.67%), higher than V-TEXT's 46.67%. Matched-seed vs. V-IMG and vs. V-IMG-BLANK: 29/30 flip from blue to red, sign-test p=3.7e-09. This refutes a naive reading of hypothesis (B): the SAME token count, delivered as pure text with no image, does not produce the SAME degradation — it produces a different, larger, opposite-direction effect via a distinct, identified mechanism (§6): the padded blue/sniper persona all but stops firing (0.76% of its actions vs. V-TEXT blue's 7.6%), which is not what V-IMG's red-side targeting-precision collapse looks like at all.
- **Token-cost matching was verified empirically, not assumed** (§3): V-IMG-BLANK's mean `prompt_tokens` (2349.4) and V-TEXT-PADDED's (2354.3) both land within 8 tokens of V-IMG's 2352.7 — a materially tighter match than needed to make the comparison meaningful.
- Both control arms required substantially more total match attempts than PR #187's originals to reach n=30 valid matches, due to elevated soft-failure rates (§2); V-TEXT-PADDED's elevated rate is itself a directly relevant finding (§6): the padding measurably degrades the model's JSON-schema compliance for the seat whose critical formatting instruction it was appended after.

**Ledgers:** `.onex_state/steel_onslaught/vl_or_blank_battery` and `.onex_state/steel_onslaught/vl_or_padded_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json` each) in the SO-VISION-CTRL worktree. V-TEXT/V-IMG baselines re-read from `.onex_state/steel_onslaught/vl_or_{text,img}_battery` in the SO-VISION-OR worktree (read-only, PR #187's own ledgers — not re-run).
**Change under test:** one new overlay field (`ModelSOLlmImageAttachmentBinding.render_mode`, default `"arena_render"`, new value `"blank"`) plus `render_blank_png()` (`src/steel_onslaught/llm/render.py`) and the branch in `LLMPilot._render_image_attachment` that selects it (`src/steel_onslaught/llm/pilot.py`) — additive, zero behavior change on any existing overlay (verified: `render_mode` defaults preserve V-TEXT/V-IMG byte-for-byte, `tests/llm/test_render_determinism.py` + `tests/llm/test_llm_pilot.py` full suite green, 194/194). Two new overlays (`vision_foundry_60_asym_v2_openrouter_{blank,padded}.yaml`), two new personas (`berserker_padded.yaml`, `sniper_padded.yaml`), two new pilots, two new loadouts — all additive, mirroring the existing `vision_openrouter` surfaces. No existing overlay, pilot, loadout, or persona file is modified.
**Model:** `google/gemini-2.5-flash-lite` via OpenRouter, both seats, both new arms, n=30, seeds 5001–5030 matched across all four arms (V-TEXT, V-IMG, V-IMG-BLANK, V-TEXT-PADDED), `all_replay_valid=true` on both new arms.
**All figures below are independently recomputed from `battery_raw.jsonl` + `events.sqlite3` for each arm.** The recomputation methodology was validated by first reproducing PR #187's own published V-TEXT/V-IMG figures byte-for-byte from its raw ledgers (win rate, Wilson CI, tick distribution, `prompt_tokens` distribution, behavior-axis fractions, vocab-axis counts, and the 14/0-flip sign test p=1.22e-04 all matched exactly) before applying the same script to the two new arms.

---

## 0. Design and why these two arms, not one

Two arms were chosen deliberately to separate three variables that are confounded in the original V-TEXT/V-IMG pair: image **presence**, image **content**, and prompt **length**.

- V-IMG-BLANK holds presence and length approximately constant (same message structure: a two-part `[text, image_url]` content array, same token cost) while zeroing content. If it reproduces V-IMG, content is not the driver.
- V-TEXT-PADDED holds length approximately constant while zeroing presence (no image content-part at all — a single-string message, the same wire shape as V-TEXT). If it reproduces V-IMG, length alone (independent of modality) is the driver.

Both were run rather than just one because they test different, non-nested claims: V-IMG-BLANK alone cannot rule out "any image, regardless of content, triggers some multi-modal-specific degradation" vs. "the token cost alone, delivered through any channel, would do it" — only the text arm can address the second reading. Running both, matched-seed against each other and against both originals, gives four pairwise comparisons that jointly triangulate the answer (§4).

---

## 1. Additivity and platform-non-negotiable checks

`render_blank_png()` (`src/steel_onslaught/llm/render.py`) shares the exact canvas-size formula (`arena_size * 12px` square) and PNG encoding parameters (`optimize=True, compress_level=6`) as `render_observation_png`, differing only in content: a single flat mid-grey (128,128,128) fill, no grid, no cells, no shapes, no enemy ring. `ModelSOLlmImageAttachmentBinding.render_mode` is a new field with default `"arena_render"`; every pre-existing overlay omits it and is unaffected (`tests/contracts/test_application_overlay.py`'s existing round-trip tests pass unmodified). `vision_foundry_60_asym_v2_openrouter_blank.yaml` is byte-identical to `..._img.yaml` except header comments, state-root paths, `model_identity_id`/`display_name`, and the one added `render_mode: blank` line — confirmed by direct diff.

`vision_foundry_60_asym_v2_openrouter_padded.yaml` is byte-identical to `..._text.yaml` except header comments, state-root paths, `model_identity_id`/`display_name` — it declares **no** `image_attachment` at all, identical wire shape to V-TEXT. The prompt-length delta comes entirely from the `berserker_padded`/`sniper_padded` personas (`contracts_data/pilots/personas/`), each of which is its base persona's `doctrine` string **verbatim** (loaded from the real YAML and diffed programmatically at generation time, not retyped by hand) plus one deterministic filler block appended — confirmed by direct string-prefix check (`padded.system_prompt.startswith(base.doctrine)` — true for both personas).

New unit tests: `tests/llm/test_render_determinism.py` gained 6 tests for `render_blank_png` (determinism, dimension match, single-flat-color, content divergence from the real render, no metadata chunks, positive-arena_size validation). `tests/llm/test_llm_pilot.py` gained 2 tests for the `render_mode` toggle (default preserved, blank mode attaches a distinct same-shape image with the same neutral note). Full suite: `uv run pytest tests/llm/test_render_determinism.py tests/llm/test_llm_pilot.py tests/contracts/test_application_overlay.py tests/llm/test_client_http.py tests/llm/test_effect.py` — **194/194 passed**. Broader regression: `uv run pytest tests/ -q -m unit` (excluding integration/frontend, which require a running dev server unrelated to this change) — **1987/1987 passed**.

---

## 2. Raw-file provenance (elevated soft-failure rate, both arms — a real, reported process finding)

Both arms used the established per-seed isolated-invocation pattern (one process per seed, shared append-mode state root, bounded retry), but needed far more total attempts than PR #187's originals. This section reports that honestly rather than hiding it behind the final n=30.

| Metric | V-IMG-BLANK | V-TEXT-PADDED | (PR #187 V-TEXT for scale) |
|---|---:|---:|---:|
| Distinct `match_started` (all attempts) | 69 | 317 | 61 |
| Distinct `match_ended` (successful matches) | 30 | 33 (30 canonical + 3 duplicate, §2a) | 30 |
| `llm_completion_requested` (all attempts) | 2095 | 12195 | 3707 |
| `llm_completion_failed` (all attempts) | 39 | 284 | 31 |
| Per-call failure rate | 1.86% | 2.33% | 0.836% |

Both rates are **2–3x PR #187's own documented V-TEXT rate** (0.836%), run on the same day, same model, same provider — most plausibly explained by backend load (both arms were run with several concurrent per-seed worker processes against the same OpenRouter account to keep wall-clock time reasonable; no `provider_error`/transport-retry-exhaustion reason codes were observed on either arm — confirmed by direct query — ruling out 429 rate-limiting as the mechanism; every failure is the same semantic-layer class PR #187 already documented). This is **not attributed to the arm designs themselves** for V-IMG-BLANK, whose failure-signature mix (`malformed_json`/`finish_reason=error,0-tokens`: 26/39; `action_unavailable`: 12/39; `invalid_action_parameters`: 1/39) is qualitatively the same shape as PR #187's own V-TEXT/V-IMG mix, just at a higher rate.

**V-TEXT-PADDED's failure composition is qualitatively different and is a directly relevant finding, not noise:** of 284 failures, **176 (62%) are `invalid_action_parameters`**, versus PR #187's V-TEXT baseline of 1 occurrence in 3707 attempts (0.027%) and V-IMG-BLANK's 1 in 2095. All 176 are attributed to `player.blue` (the sniper_padded seat) — **zero from red** (confirmed by direct query of `subject_json`/`semantic_failure_code` pairs across every failure event in the ledger, not a sample). A live in-process capture of one such failure (§6) shows the model producing a well-formed but schema-violating `{"action": "remain", "action_params": {"direction": "hold_position"}}` — REMAIN accepts no params in this codebase's contract, and the model has hallucinated one. This is the same class PR #187 documented once (§3 of that document) at a vanishingly low base rate; here it recurs at a rate roughly 60x higher, specific to the padded persona.

### 2a. Duplicate seeds from parallel workers (surplus data, not corruption)

To keep wall-clock time reasonable given §2's elevated failure rate, multiple per-seed worker processes ran concurrently against the same state root (safe: `battery_raw.jsonl` appends are per-line and well under `PIPE_BUF`; `events.sqlite3` is WAL-mode with distinct `match_id`s per attempt). Three seeds (5010, 5012, 5017) were independently completed by two different concurrent workers before either observed the other's write — both are genuinely independent, fully-valid completed matches for the same seed value (different `match_id`s, and in seed 5010's case, different outcomes: one run had blue win, the other red — direct evidence that outcome varies under re-sampling even holding the game-RNG seed fixed, since only the LLM's own sampling differs between the two runs). The canonical, first-written row per seed is used for every figure in this document; the 3 extras are recorded but excluded from analysis (`dropped_duplicate_seed_rows` in the raw summary). `battery_raw.jsonl` for V-TEXT-PADDED therefore has 33 rows for 30 distinct seeds; V-IMG-BLANK has exactly 30 rows, zero duplicates.

---

## 3. Token-cost matching — verified empirically, not assumed

This was the single most important design detail per the task brief, and it was measured, not asserted.

**Calibration (V-TEXT-PADDED):** live single-call probes against the real `openrouter_vl` provider binding (same model, same client code path) with varying filler-character counts established a stable marginal rate of **~5.06 characters per provider-reported token**, consistent across both personas (berserker: 757→2079 tokens for 0→6708 filler chars; sniper: 899→2216 tokens for the same 6708-char filler) — confirming the marginal token cost of the filler block is persona-independent. 6,708 characters was selected to add ≈1,317–1,322 tokens per call, matching V-IMG's measured overhead (2352.7 − 1033.0 = 1319.7 tokens) to within 5 tokens at calibration time.

**Verified against the full battery data (not the calibration probes):**

| Arm | Mean `prompt_tokens` | n (resolved completions) | stdev | Delta from V-IMG's 2352.7 |
|---|---:|---:|---:|---:|
| V-IMG (PR #187) | 2352.7 | 1478 | 83.1 | — |
| **V-IMG-BLANK** | **2349.4** | 1196 | 82.3 | **−3.3** |
| **V-TEXT-PADDED** | **2354.3** | 2906 | 84.4 | **+1.6** |

Both control arms land within **8 tokens** of V-IMG's mean, with matching standard deviations (82–84 across all three image/padded arms, vs. V-TEXT's 85.3) — the per-call token *variance* comes from the underlying observation text (which varies tick-to-tick), and both the image attachment and the filler block contribute a near-constant additive overhead on top of it, exactly as intended. **The image-token-cost-is-resolution-based assumption (not content-based) is empirically confirmed**: V-IMG-BLANK's flat grey canvas costs statistically indistinguishable tokens from V-IMG's real, detailed arena render (2349.4 vs. 2352.7, well within noise) — Gemini's image tokenization is evidently driven by pixel dimensions, not pixel content, for this resolution.

---

## 4. Outcome, terminal health, and match length

| Metric | V-IMG-BLANK | V-TEXT-PADDED |
|---|---:|---:|
| `match_started` / `match_ended` (valid, canonical) | 30 / 30 | 30 / 30 |
| Terminal-class mix | elimination 30/30 | elimination 30/30 |
| `play_terminal_fraction` | **1.0000** (gate ≥0.9 — PASS) | **1.0000** (gate ≥0.9 — PASS) |
| Winner distribution | player.blue 30, player.red 0 | player.red 29, player.blue 1 |
| **Decided-match red win rate** | **0/30 = 0.0000** | **29/30 = 0.9667** |
| 95% Wilson CI | **[0.0000, 0.1135]** | **[0.8333, 0.9941]** |
| Verdict band | **FAILED** (<0.10) | far above **COMPETITIVE** (≥0.35) |
| Replay validity | 1/1 both players, all 30 matches | 1/1 both players, all 30 matches |
| Match length: min / median / mean / max (ticks) | 10 / 18.0 / 19.93 / 39 | 33 / 48.0 / 48.47 / 90 |

V-IMG-BLANK's matches are, if anything, **shorter** than V-IMG's (median 18.0 vs. 20.5 ticks) — consistent with the same fast-collapse pattern, not a slower/different failure mode. V-TEXT-PADDED's matches run **longer** than V-TEXT's (median 48.0 vs. 45.0) despite ending in red's near-total domination — consistent with §6's finding that blue spends most of the match moving/remaining rather than fighting, drawing matches out rather than shortening them, until red eventually closes and eliminates blue.

### 4a. Matched-seed pairing — all six pairwise comparisons

| Comparison | Common seeds | Flips A→B | Flips B→A | Sign-test p |
|---|---:|---:|---:|---:|
| V-TEXT → V-IMG (PR #187, reproduced) | 30 | 14 | 0 | 1.22e-04 |
| V-TEXT → V-IMG-BLANK | 30 | 14 | 0 | 1.22e-04 |
| **V-IMG → V-IMG-BLANK** | 30 | **0** | **0** | **1.0** |
| V-TEXT → V-TEXT-PADDED | 30 | 0 | 15 | 6.10e-05 |
| V-IMG → V-TEXT-PADDED | 30 | 0 | 29 | 3.73e-09 |
| V-IMG-BLANK → V-TEXT-PADDED | 30 | 0 | 29 | 3.73e-09 |

"Flips A→B" counts seeds where red won under arm A and lost under arm B, on the identical seed; "Flips B→A" the reverse.

The **V-IMG vs. V-IMG-BLANK row is the load-bearing result of this document**: on every one of the 30 matched seeds, the outcome under V-IMG-BLANK is identical to the outcome under V-IMG (blue wins all 30 in both). This is not merely "a similar win rate" — it is bit-for-bit identical per-seed agreement, the strongest form of evidence this experiment design can produce. A content-free image cannot mislead the model about anything, since it depicts nothing; the collapse persists anyway.

The bottom three rows show V-TEXT-PADDED diverging sharply from **both** image arms in the opposite direction from V-TEXT itself — it is not "V-TEXT with worse targeting," it is a distinctly different failure mode (§6).

---

## 5. Cognition axis — stated rationale vocabulary (method reused from `spatial_r1` / PR #187 §5)

Same regex scan for clean-attribution visual/color/pixel vocabulary the model's purely-numeric text observation could not have produced on its own.

| Arm | Seat | Rationales scanned | Visual-vocab hits | Fraction |
|---|---|---:|---:|---:|
| V-IMG-BLANK | red | 598 | 0 | 0.0000 |
| V-IMG-BLANK | blue | 598 | 0 | 0.0000 |
| V-TEXT-PADDED | red | 1453 | 0 | 0.0000 |
| V-TEXT-PADDED | blue | 1453 | 1 | 0.0007 |

Consistent with PR #187: essentially zero clean-attribution visual vocabulary in every arm, image or not, padded or not (the single V-TEXT-PADDED blue hit is presumed the same idiomatic false positive class PR #187 manually inspected and dismissed — not re-inspected here since the rate is unchanged from that document's own negative-control baseline). This axis contributes nothing new; it is reported for completeness and consistency with the program's convention of always running it.

---

## 6. Behavior axis — the two arms fail in mechanistically different ways

**V-IMG-BLANK reproduces V-IMG's red-side targeting-precision collapse quantitatively, not just at the outcome level:**

| Seat | Metric | V-IMG (PR #187) | V-IMG-BLANK |
|---|---|---:|---:|
| red | out-of-range fire fraction | 35.70% | **25.19%** |
| red | zero-hit-probability fired fraction | 38.24% | **19.80%** |
| blue | out-of-range fire fraction | 0.00% | 0.00% |
| blue | zero-hit-probability fired fraction | 23.03% | **16.34%** |

Red's targeting precision is degraded in V-IMG-BLANK relative to V-TEXT's near-zero baseline (0.26% out-of-range, 5.24% zero-hit — PR #187 §6) by roughly the same large margin V-IMG showed, just somewhat smaller in magnitude (consistent with the shorter matches giving red fewer opportunities to accumulate bad shots before the match ends). **This is the same mechanism, reproduced without any image content at all** — direct behavioral confirmation of the outcome-level finding in §4.

**V-TEXT-PADDED shows an entirely different, seat-specific effect: blue's near-total cessation of firing, not degraded targeting when it does fire.**

| Arm | Seat | Actions: move / remain / fire_weapon / switch_mode | Fire share of all actions |
|---|---|---|---:|
| V-TEXT (PR #187) | blue | 397 / 862 / 104 / 2 | 7.6% |
| **V-TEXT-PADDED** | **blue** | **775 / 662 / 11 / 5** | **0.76%** |
| V-TEXT (PR #187) | red | 552 / 0 / 784 / 29 | 57.9% |
| V-TEXT-PADDED | red | 773 / 6 / 661 / 13 | 47.6% |

Blue (sniper_padded) fires roughly **10x less often, proportionally**, than its own unpadded V-TEXT baseline — not "fires and misses more," but overwhelmingly chooses `remain`/`move` instead of ever attempting to fire. This is corroborated by the raw fire-attempt count in the earlier win-rate table's underlying data: blue's total fire attempts across all 30 matches falls to essentially nothing (11 `fire_weapon` decisions total, vs. V-TEXT's 104 and V-IMG's 165). Red, largely unaffected, plays its normal aggressive game against an opponent that rarely shoots back, producing the 96.67% win rate.

A live in-process capture (monkey-patched `LLMPilot._parse_response` to log the raw response text immediately before an `invalid_action_parameters` exception) reproduced one instance of the failure mode driving blue's elevated abort rate (§2):

```
finish_reason: stop, prompt_tokens: 2431
RAW TEXT: '{"action": "remain", "action_params": {"direction": "hold_position"},
"confidence": 0.9, "rationale": "Enemy is too close for optimal sniper range,
and sensor confidence is mixed; wait for better positioning or clearer
targeting data."}'
```

This is a coherent, well-reasoned decision to remain — the model's *judgment* is intact — but it hallucinates a `direction` parameter that the `remain` action's contract does not accept (`ModelSOEmptyPayload` requires an empty dict). All 176 occurrences of this exact failure class across the whole battery are attributed to blue exclusively (§2), never red — consistent with the padded sniper persona specifically, not a model-wide degradation. A plausible (not proven) contributing factor: `sniper.yaml`'s doctrine ends with an explicit "reply with ONLY the required JSON object... never wrap the JSON in prose" instruction, and the padding filler is appended **after** that instruction in `sniper_padded.yaml`, maximizing textual distance between the critical formatting constraint and the model's actual response — no comparable end-of-doctrine formatting instruction exists in `berserker.yaml`, which may explain why zero of the 176 failures are attributed to red.

**Methodological caveat (stated plainly, not resolved by this document):** because `failure_policy: raise` discards the whole match on any single completion failure, and blue's `invalid_action_parameters` failures are attributed specifically to `remain` decisions (not `fire_weapon`), there is a possible selection effect: matches that survive to completion may be disproportionately drawn from trajectories where blue's `remain`-heavy pattern happened not to trigger the schema violation. Whether this selection effect amplifies, dampens, or is orthogonal to blue's already-observed low fire-rate cannot be determined from this data alone — the surviving-match fire-share (0.76%) is far more extreme than would be needed to merely avoid the failure trigger, which argues against the selection effect being the primary driver, but this is inference, not proof.

---

## 7. Verdict — hypothesis (A) vs (B) vs the data

**Hypothesis (A), image-content-specific degradation, is refuted.** V-IMG-BLANK carries zero task-relevant visual information — a single flat color, nothing the model could read a position, distance, or shape from — and its per-seed outcomes are **identical** to V-IMG's (0 flips across 30 matched seeds, sign-test p=1.0), with the same targeting-precision degradation pattern reproduced quantitatively (§6). Whatever is happening, it does not require the image to depict anything.

**Hypothesis (B), as originally framed ("any equivalent-token-cost payload would cause the same degradation, regardless of channel"), is also refuted.** V-TEXT-PADDED matches V-IMG's token cost to within 2 tokens (§3) but produces a completely different outcome — not a milder version of V-IMG's collapse, but the opposite direction entirely (96.67% red win vs. V-IMG's 0%), via a distinct, seat-specific mechanism (blue's near-total fire suppression, §6) that bears no resemblance to V-IMG's red-side targeting-precision collapse.

**What the data support instead: the degradation is specific to the image/multi-part-message channel, independent of both content and raw token count.** V-IMG and V-IMG-BLANK share a wire-format property V-TEXT-PADDED does not — both send the user turn as a two-part `[text, image_url]` content array rather than a single string, regardless of what the image_url payload actually encodes. This experiment cannot distinguish between (i) a vision-specific tokenization/attention pathway that degrades numeric reasoning whenever it is engaged at all, content notwithstanding, or (ii) some other property of multi-part message structuring on this provider/model that a single long string does not share. Both remain open, but the content-vs-length axis originally posed by PR #187 §6 is now resolved: **it is neither.**

**A secondary, independently important finding**: prompt padding, at least in the position and persona tested here, produces its own large, real, seat-specific effect — degraded JSON-schema compliance and a near-total behavioral collapse in the persona whose critical formatting instruction was pushed furthest from the model's point of decision. This is evidence that prompt length *can* matter, just not in the way, or through the mechanism, that would explain V-IMG's original result.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/vl_or_blank_battery/{events.sqlite3,battery_raw.jsonl}`, `.onex_state/steel_onslaught/vl_or_padded_battery/{events.sqlite3,battery_raw.jsonl}` (30 canonical rows each, seeds 5001–5030; padded has 3 additional surplus rows, §2a).
- V-TEXT/V-IMG baselines (unmodified, re-read only): `.onex_state/steel_onslaught/vl_or_{text,img}_battery` in the SO-VISION-OR worktree; `docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md` (PR #187).
- New source: `src/steel_onslaught/llm/render.py` (`render_blank_png`), `src/steel_onslaught/contracts/application.py` (`ModelSOLlmImageAttachmentBinding.render_mode`), `src/steel_onslaught/llm/pilot.py` (`_render_image_attachment` branch).
- New overlays: `contracts_data/overlays/vision_foundry_60_asym_v2_openrouter_{blank,padded}.yaml`.
- New personas: `contracts_data/pilots/personas/{berserker,sniper}_padded.yaml`.
- New pilots: `contracts_data/pilots/vision_openrouter/llm_openrouter_{berserker,sniper}_padded.yaml`.
- New loadouts: `contracts_data/loadouts/vision_openrouter/{berserker_scout_v2,sniper_ironclad}_padded.yaml`.
- New tests: `tests/llm/test_render_determinism.py` (6 new), `tests/llm/test_llm_pilot.py` (2 new). Full targeted suite 194/194 passed; broader unit suite 1987/1987 passed.
- Render/ledger-linkage spot check: `.onex_state/steel_onslaught/vision_foundry_60_asym_v2_openrouter_blank/renders/match.01KYB5YZM7ZEWA6F1PWFD73DDB/tick_0003_mech.red.01.png`, sha256 `5b54b7297fce4aefb1150b9e765c8b578f83a6394d90bc8723530d70e592ef84`, matching the ledger's `image_sha256` for the same match/tick/seat exactly.
- Sanitization: `python3 scripts/check_sanitization.py --all` — clean, no secrets/absolute paths.
- Prior document: `docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md` (PR #187) — this document does not supersede it; it resolves the hypothesis (A)/(B) question that document's §6 left open.
