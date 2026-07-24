# Vision-Representation Experiment RERUN over OpenRouter — V-TEXT vs V-IMG, n=30 Matched Seeds (2026-07-24)

**Verdict: the image attachment produces a large, clean, negative within-model effect on outcome.** Holding the model (`google/gemini-2.5-flash-lite`), arena (`foundry_60_asym_v2`), loadouts, and personas fixed, and paired on identical seeds 5001–5030:

- **V-TEXT** (no image): decided-match red (brawler) win rate **14/30 = 0.4667**, 95% Wilson CI **[0.3023, 0.6386]** — **COMPETITIVE** band (≥0.35).
- **V-IMG** (same prompt + deterministic per-tick PNG attached): decided-match red win rate **0/30 = 0.0000**, 95% Wilson CI **[0.0000, 0.1135]** — **FAILED** band (<0.10).
- **Delta: −0.4667.** Every one of red's 14 V-TEXT wins (seeds 5003, 5004, 5007, 5008, 5009, 5018, 5019, 5021, 5023, 5024, 5025, 5027, 5028, 5030) flips to a blue win under V-IMG on the **identical seed**. Zero seeds flip the other direction. This is the largest and cleanest single-lever effect measured anywhere in this program to date.
- **Cognition axis (stated rationale vocabulary) shows ZERO attribution to the image**: 0/739 red rationales and 0/739 blue rationales in V-IMG contain any visual/color/pixel vocabulary that the pure-numeric text observation could not already have produced (see §5). This is the **opposite** pattern from the spatial-representation arms (`docs/evidence/2026-07-24-spatial_r1-battery.md`), where representation clearly reached stated cognition (0/209 → 77/272) while outcome stayed flat. Here outcome moves enormously while stated cognition shows no trace of the image at all — reported separately per house convention, not blended.
- **Behavior axis (targeting-precision proxies) shows a large, consistent shift co-occurring with the outcome collapse**: red's out-of-range fire-attempt fraction rises from **0.26% (V-TEXT) to 35.70% (V-IMG)**, and red's zero-hit-probability fired-shot fraction rises from **5.24% to 38.24%** (§4). This is offered as the leading **candidate mechanism**, not a proven cause (§6).

**This is the OpenRouter unblock of PR #171's blocked gemini_text/gemini_img pair** (`docs/evidence/2026-07-24-vl_text-battery.md` / `2026-07-24-vl_img-battery.md`, both VACUOUS — 0/22 and 0/1 attempted respectively — on a shared Google AI Studio free-tier key, and `docs/evidence/2026-07-24-vl_rerun-credential-gate-blocked.md`, PR #185, which proved `GOOGLE_API_KEY`/`GEMINI_API_KEY` were the same free-tier secret and stopped rather than run a doomed battery). This document routes the **identical model** through OpenRouter's paid billing instead, producing the first trustworthy data this experiment has ever generated.

**Ledgers:** `.onex_state/steel_onslaught/vl_or_text_battery` and `.onex_state/steel_onslaught/vl_or_img_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json` each) in the SO-VISION-OR worktree.
**Change under test:** two new overlays, `contracts_data/overlays/vision_foundry_60_asym_v2_openrouter_{text,img}.yaml`, plus a new pilot registry (`contracts_data/pilots/vision_openrouter/`) and loadouts (`contracts_data/loadouts/vision_openrouter/`) — all additive, byte-for-byte mirrors of the existing `vision_gemini`/`gemini_text`/`gemini_img` surfaces except for the provider binding (OpenRouter endpoint, `google/gemini-2.5-flash-lite` paid slug, `secret://llm/openrouter`, bumped `max_tokens`/`timeout_seconds`/`retry`). No existing file is modified. Arena `foundry_60_asym_v2` untouched.
**Model:** `google/gemini-2.5-flash-lite` via OpenRouter, both seats, both arms, n=30, seeds 5001–5030 matched across arms, `all_replay_valid=true` (1/1 both players, all 60 matches across both arms).
**All figures below are independently recomputed from `battery_raw.jsonl` + `events.sqlite3` for each arm — not copied from stdout or `battery_summary.json`, which is stale after the segmented/backfilled runs described in §2.**

---

## 0. Model choice, billing, and the smoke gate (read before the results)

**Model:** `google/gemini-2.5-flash-lite` via OpenRouter — deliberately the **same model** the original blocked experiment specified (`vision_foundry_60_asym_v2_gemini_text.yaml`/`..._img.yaml`, PR #171), so this is the closest possible rerun of the original design, not a new experiment. Verified live via `GET https://openrouter.ai/api/v1/models` this session: `google/gemini-2.5-flash-lite` has `input_modalities: [text, image, file, audio, video]` and non-zero pricing (`$0.10/M` prompt tokens, `$0.40/M` completion tokens) — the paid slug, not `google/gemini-2.5-flash-lite:free`. Candidates considered and rejected: `openai/gpt-4o-mini` (also paid+vision, but switching models would have broken the "same model, different provider" design goal that makes this a clean rerun rather than a new experiment).

**Billing confirmed live, not assumed:**
- `GET https://openrouter.ai/api/v1/credits` at session start: `{"total_credits": 100, "total_usage": 55.8}` — a paid account with ~44 credits available, not a free/zero-balance account.
- A direct multi-part smoke call (real PNG from a prior render, base64 data-URI `image_url` content part, `response_format: json_object`) returned HTTP 200 with a coherent description of the image (`"Dark gray rectangles and squares are scattered across a grid with a blue dot in the lower left."`) and a non-zero, billed cost (`"cost": 0.0001403, "is_byok": false`) — confirming both image acceptance and real (non-free) billing before any battery was launched.
- End-of-session credits: `{"total_credits": 100, "total_usage": 56.80}` — this experiment's total incremental cost (both smoke tests + both full n=30 batteries + backfills) was **≈$1.00**.

**Pre-registered gate (per task brief) — all three passed before the full battery ran:**
1. `OPEN_ROUTER_API_KEY` resolves and the account has credit — confirmed above.
2. The model accepts the image part and returns a coherent (non-400) response — confirmed above, plus a second smoke call with `response_format: json_object` + image, also HTTP 200 with valid JSON content.
3. A 1-seed smoke of each arm end-to-end, `all_replay_valid=true`, match terminates — V-TEXT: seed 5001, 76 ticks, `all_replay_valid=true`, 0 failed completions. V-IMG: seed 5001 (rerun after one image-arm smoke hit the failure mode documented in §2 mid-match), 11 ticks, `all_replay_valid=true`, 0 failed completions.

`max_tokens` was set to **3072** (up from the original blocked overlay's 2048) as a proactive safety margin against CoT-budget truncation, since these overlays are new and had never been run to completion. **This did not materialize as a risk**: `finish_reason=length` occurred **zero times** across 5,571 total resolved completions in both arms combined (§3) — max observed `completion_tokens` was 87 (V-TEXT) / 120 (V-IMG), both far under budget.

---

## 1. Additivity check

`diff` of the two overlays confirms they are identical except: header comments, state-root path fields, `model_identity_id`/`display_name`, and the one added `llm.providers[0].image_attachment: {enabled: true, arena_size: 60, render_output_dir: ...}` block. `timeout_seconds: 120.0`, `max_tokens: 3072`, and `retry: {max_attempts: 4, initial_backoff_seconds: 2.0, backoff_multiplier: 2.0}` are byte-identical between the two arms. Both arms share the identical `contracts_data/loadouts/vision_openrouter/{berserker_scout_v2,sniper_ironclad}.yaml` (byte-for-byte module/budget mirrors of the pre-existing `vision_gemini` loadouts) and pilot registry. Neither arena nor persona files were touched. This is the same additivity guarantee the original `gemini_text`/`gemini_img` pair carried (verified in `docs/evidence/2026-07-24-vl_img-battery.md` §5) — confirmed independently here for the new OpenRouter pair.

---

## 2. Raw-file provenance (segmented battery — orphaned partial-match retries, by design)

Unlike the P4 battery's clean single-pass run, this battery hit a real, reproducible transport-level failure mode (§3) at a rate that required **per-seed isolated invocation with bounded retry**: one process per seed (`--n 1 --seed-base <seed-1>`), shared append-mode state root, `--fresh` only on the very first seed, up to 3 attempts per seed with a 600s timeout, run as two parallel background drivers (one per arm). This is the same per-seed-isolation pattern the P4 battery established, sized up (3 attempts vs P4's 2, 600s vs P4's 420s) because this arm runs over a real network hop (OpenRouter) rather than a local model, and because the discovered failure mode (§3) has a non-trivial per-call rate.

**First pass (30 seeds, 3 attempts each):**
- V-TEXT: 24/30 seeds succeeded; 6 exhausted all 3 attempts (5018, 5019, 5022, 5023, 5026, 5028).
- V-IMG: 29/30 seeds succeeded; 1 exhausted (5015).

**Backfill pass** (same 7 missing seeds, up to 5 attempts, same append-mode state roots, no `--fresh`): **all 7 succeeded on backfill attempt 1.** Final state: **both arms have exactly 30 rows, seeds 5001–5030, zero duplicates, zero gaps** — independently verified (`len(set(seeds))==30`, `min=5001`, `max=5030` for both `battery_raw.jsonl` files).

**Consequence for `events.sqlite3`:** because `failure_policy: raise` applies to this non-card-mode `LLMPilot.decide` archetype (any completion failure aborts the whole in-progress match, not just the tick — no bounded reprompt budget exists at this call site, unlike the card-mode O-GATE battery's per-tick reprompt), every failed attempt leaves an **orphaned partial-match** in the ledger (a `match_started` event and however many ticks it reached, but no `match_ended`/`battery_raw.jsonl` row). `events.sqlite3` therefore contains 61 distinct `match_started` values for V-TEXT (30 valid + 31 orphaned) and 41 for V-IMG (30 valid + 11 orphaned) — both counts self-consistent with the failure counts in §3 (31 and 11 respectively: one orphaned partial match per failure, exactly, confirming no failure was silently dropped or double-counted). **All event-level analysis in this document (§3–§5) filters to the 30 valid `match_id`s per arm from `battery_raw.jsonl` — orphaned partial-match events are excluded**, matching the established convention from the P2/P3 crash-and-resume batteries.

---

## 3. Completion health and the discovered failure mode

| Metric | V-TEXT (valid matches only) | V-IMG (valid matches only) |
|---|---:|---:|
| `llm_completion_requested` | 2730 | 1478 |
| `llm_completion_resolved` | 2730 | 1478 |
| `llm_completion_failed` (in valid matches) | 0 | 0 |
| `finish_reason` distribution (resolved) | `stop`: 2730/2730 (0 `length`) | `stop`: 1478/1478 (0 `length`) |
| max `completion_tokens` observed | 87 | 120 |
| mean `prompt_tokens` | 1033.0 | 2352.7 |
| mean `completion_tokens` | 56.0 | 57.4 |

Zero completion failures occur **within the 30 valid matches of either arm** — every failure that occurred landed in an orphaned, discarded partial-match attempt that was then retried from tick 1 (per §2's `failure_policy: raise` mechanics). Counting **all** attempts (valid + orphaned, i.e. every call made across the whole segmented run):

| Metric | V-TEXT (all attempts) | V-IMG (all attempts) |
|---|---:|---:|
| `llm_completion_requested` | 3707 | 1864 |
| `llm_completion_failed` | 31 | 11 |
| Failure rate | 0.836% | 0.590% |
| `(finish_reason='error', semantic_failure_code='malformed_json')` | 28 | 9 |
| `(finish_reason='stop', semantic_failure_code='malformed_json')` | 2 | 2 |
| `(finish_reason='stop', semantic_failure_code='invalid_action_parameters')` | 1 | 0 |

**The dominant failure signature (28/31 V-TEXT, 9/11 V-IMG — ~90%/82% of all failures) is `finish_reason: "error"` with `prompt_tokens: 0, completion_tokens: 0`.** This is **not** the named "CoT-budget truncation" class from the task brief (that would show `finish_reason: "length"` with `completion_tokens` near the `max_tokens` ceiling — observed **zero times** in 5,571 resolved completions across both arms). It is a **different, previously undocumented failure class for this codebase**: OpenRouter/the underlying Google backend occasionally returns an HTTP 200 response whose `choices[0].finish_reason` is the literal string `"error"` with zero usage tokens — a soft, in-band failure signal rather than an HTTP-level error. `OpenAICompatibleClient.complete()` (`src/steel_onslaught/llm/client_http.py`) only retries `TimeoutError` and `LlmTransportError` around the transport call; a 200-status response with an in-band `finish_reason="error"` is not classified as retryable at that layer, so it flows through to `_parse_response` (`pilot.py`) which then raises `LlmSemanticError("malformed_json")` — a label that describes the symptom (empty/unparseable content), not the root cause (an upstream provider hiccup surfaced in-band, not out-of-band). This mislabeling is a genuine, reportable finding, not this document's editorializing: **no code change was made to correct the classification** — that would be provider-adapter work beyond this task's scope — and the per-seed isolation + bounded retry (§2) is the correct, already-authorized way to absorb it. A residual 5/42 total failures (2 V-TEXT, 2 V-IMG "stop/malformed_json" + 1 V-TEXT "stop/invalid_action_parameters") are genuine model-output mistakes with real completions, distinct from the transport-layer class.

**This failure mode occurs on both arms, at a similar rate, and is not image-specific** (0.84% V-TEXT vs 0.59% V-IMG, same order of magnitude, no image content in the 28 V-TEXT `error` failures since V-TEXT never attaches one) — it is an OpenRouter/upstream-routing characteristic of this model at this volume, not an artifact of the image attachment.

---

## 4. Outcome, terminal health, and match length

| Metric | V-TEXT | V-IMG |
|---|---:|---:|
| `match_started` / `match_ended` (valid) | 30 / 30 | 30 / 30 |
| Terminal-class mix | elimination 30/30 | elimination 30/30 |
| `play_terminal_fraction` | **1.0000** (gate ≥0.9 — PASS) | **1.0000** (gate ≥0.9 — PASS) |
| Winner distribution | player.blue 16, player.red 14 | player.blue 30, player.red 0 |
| **Decided-match red win rate** | **14/30 = 0.4667** | **0/30 = 0.0000** |
| 95% Wilson CI | **[0.3023, 0.6386]** | **[0.0000, 0.1135]** |
| Verdict band | **COMPETITIVE** (≥0.35) | **FAILED** (<0.10) |
| Replay validity | 1/1 both players, all 30 matches | 1/1 both players, all 30 matches |
| `mech_destroyed` (red as victim) | 16/30 | 30/30 |
| Match length: min / median / mean / max (ticks) | 11 / 45.0 / 45.50 / 86 | 8 / 20.5 / 24.63 / 72 |

Recomputed directly from `battery_raw.jsonl` (30 rows each, seeds 5001–5030) and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id) WHERE event_type='match_ended'` = 30 for both arms, all `winner_player_id`/`terminal_class` values matching the raw rows exactly). V-IMG matches run **less than half as long** on median (20.5 vs 45.0 ticks) — consistent with blue closing out fights faster once red's targeting degrades (§5), not with slower/stalled matches.

### Seed-level pairing (the actual point of this experiment)

| V-TEXT red wins (seed) | V-IMG outcome, same seed |
|---|---|
| 5003, 5004, 5007, 5008, 5009, 5018, 5019, 5021, 5023, 5024, 5025, 5027, 5028, 5030 | **all 14 flip to blue** |

Zero seeds flip the other direction (no seed where blue won under V-TEXT and red won under V-IMG). This is a paired, within-model, matched-seed design — the flip is not a sampling artifact of comparing two different seed sets; it is the same seed, same model, same arena, same loadouts, with the ONLY difference being one added image content-part on every LLM call.

---

## 5. Cognition axis — stated rationale vocabulary (NOT reached, reported separately from outcome)

**Method** (reused from `docs/evidence/2026-07-24-spatial_r1-battery.md` §"Axis 2", adapted): the plain-text observation serialized by `_serialize_observation` (`src/steel_onslaught/llm/pilot.py`) is **purely numeric/symbolic** — `x,y` coordinates, boolean `has_line_of_sight_to_enemy`, a `blocked_directions` list, percentages, weapon stat blocks. It contains **zero** color, shape, or pixel vocabulary in either arm (confirmed by direct read of the serialization function). This makes any such vocabulary in a V-IMG rationale a clean-attribution signal that could only have come from the attached PNG — the same logic the spatial arms used for cover/LOS vocabulary against the berserker persona's doctrine text.

Regex scan (case-insensitive) of all `pilot_decision_made.rationale` text for: `gray, grey, blue dot, red dot, black, white square, rectangle, square, grid, pixel, image shows, the image, picture, screenshot, render, dark gray, color, colour, i see, visible in, shown in the, depicted`.

| Arm | Seat | Rationales scanned | Visual-vocab hits | Fraction |
|---|---|---:|---:|---:|
| V-IMG | red | 739 | **0** | **0.0000** |
| V-IMG | blue | 739 | **0** | **0.0000** |
| V-TEXT (negative control) | red | 1365 | 0 | 0.0000 |
| V-TEXT (negative control) | blue | 1365 | 1 | 0.0007 |

The single V-TEXT "hit" (`"...so I will wait for a clearer picture."`) is an idiomatic false positive ("clearer picture" as a figure of speech, not a visual reference), manually inspected — confirming the vocabulary list is not systematically over-triggering. **V-IMG shows literally zero clean-attribution vocabulary across 1,478 rationales, from either seat.** A manual read of 15 randomly sampled V-IMG rationales (seed 42) confirms this: every sample is phrased identically to V-TEXT's style — `"enemy is within range and sensor confidence is high"`, `"too far for effective engagement"` — with no reference to the image, colors, shapes, or the arena render at all.

**This is the mirror image of the spatial-representation arms' cognition finding.** In `spatial_r1`, the representation reached stated cognition (0/209 → 77/272 clean-attribution cover/LOS mentions) while outcome stayed flat (0/30 red wins, unchanged). Here, outcome moves enormously (46.67% → 0.00%) while stated cognition shows **no measurable trace of the image at all**. These are reported as two independent, non-blended findings per house convention — the model's own stated rationale gives no indication it is using the image, even though its behavior (§6) and its match outcomes (§4) are dramatically different when the image is present.

---

## 6. Behavior axis — targeting-precision proxies (candidate mechanism, not proven)

**Method** (reused from `spatial_r1` §"Axis 2.2/2.3"): out-of-range fire-attempt fraction = `weapon_fire_rejected{reason=target_out_of_range}` ÷ (`weapon_fired` + `weapon_fire_rejected`) per seat; zero-hit-probability fired-shot fraction = `weapon_fired{hit_probability=0.0}` ÷ `weapon_fired` per seat. Both reconstructed from `events.sqlite3`, filtered to the 30 valid match_ids per arm.

| Seat | Metric | V-TEXT | V-IMG | Δ |
|---|---|---:|---:|---:|
| red (brawler) | fire attempts (`fired`+`rejected`) | 784 | 423 | — |
| red | out-of-range fraction | 2/784 = **0.26%** | 151/423 = **35.70%** | **+35.44 pp** |
| red | zero-hit-probability fired fraction | 41/782 = **5.24%** | 104/272 = **38.24%** | **+33.00 pp** |
| blue (sniper) | fire attempts | 103 | 165 | — |
| blue | out-of-range fraction | 0/103 = 0.00% | 0/165 = 0.00% | 0.00 pp |
| blue | zero-hit-probability fired fraction | 1/103 = 0.97% | 38/165 = 23.03% | +22.06 pp |
| — | red avg decision confidence | 0.9464 | 0.9719 | +0.0255 |
| — | blue avg decision confidence | 0.7072 | 0.5760 | −0.1312 |

**This is a large, consistent, and mechanically legible degradation in targeting precision for both seats when the image is attached, far outsized for red (whose win rate collapses) but present for blue too (whose win rate does not collapse, since blue was already favored).** Red's out-of-range fire-attempt rate jumps from effectively zero (2/784) to over a third of all fire attempts (151/423); its zero-hit-probability shot rate jumps similarly (5.2% → 38.2%). This co-occurs with, and is offered as the leading **candidate mechanism** for, the outcome collapse in §4 — firing at targets that are mechanically out of range or have zero probability of hitting directly wastes actions and heat/pressure that a competitive brawler needs to close distance and land kills.

**This is a hypothesis, not a proven causal claim.** Two competing (not mutually exclusive) explanations are offered, and this single experiment cannot distinguish between them:
1. **Image-content-specific degradation**: the model partially bases targeting on a visually-inferred read of the render (distances/positions) that is less precise than the exact numeric fields already present in the same-content text prompt, actively worsening decisions that would otherwise be correct from text alone.
2. **Prompt-length/attention dilution**: mean `prompt_tokens` more than doubles under V-IMG (1033 → 2353, driven by ~1300 tokens of image encoding overhead per call — §3), and a longer, denser prompt could degrade a "lite"/fast model's attention to the precise numeric fields it needs for range/hit-probability judgments, independent of what the image actually depicts.

Distinguishing these would require a token-length-matched control (e.g. a same-token-count filler/dummy image or padding text) that this experiment does not include — flagged as the natural next step, not attempted here.

---

## 7. Verdict

**The image attachment produces a large, negative, within-model effect on outcome** — red's decided-match win rate collapses from 46.67% (COMPETITIVE band, Wilson CI [0.302, 0.639]) to 0.00% (FAILED band, Wilson CI [0.000, 0.114]) when an identical deterministic per-tick PNG is attached to an otherwise-identical prompt, holding model/arena/loadouts/personas/seeds fixed. Every one of red's 14 V-TEXT wins flips to a blue win under V-IMG on the matched seed; zero seeds flip the other way. `play_terminal_fraction=1.0000` on both arms clears the trust gate with room to spare — this is not a vacuous or undertrusted result on either side.

**Cognition and behavior axes are reported separately, per house convention, and point in different directions.** Stated rationale vocabulary shows **zero** evidence the image reaches the model's articulated reasoning (0/1478 clean-attribution hits across both seats) — the opposite of the spatial-representation arms, where representation clearly reached stated cognition without moving outcome. But mechanical targeting-precision proxies (out-of-range fire fraction, zero-hit-probability fired fraction) show a large, consistent degradation for both seats when the image is attached, offered as the leading (not proven) candidate mechanism for the outcome collapse.

**A genuine, previously undocumented failure mode was found and worked around, not fixed**: OpenRouter/the underlying Google backend occasionally (~0.6–0.8% of calls) returns HTTP 200 with an in-band `finish_reason="error"` and zero usage tokens, which this codebase's transport-retry classification does not currently treat as retryable, surfacing instead as a match-ending `LlmSemanticError("malformed_json")` under this pilot archetype's `failure_policy: raise`. This is distinct from the named "CoT-budget truncation" class (`finish_reason="length"`), which occurred **zero times** in 5,571 resolved completions. Per-seed isolated invocation with bounded retry (established P4 pattern, sized to 3+5 attempts here) fully absorbed this and produced a clean, complete n=30-per-arm, zero-gap, zero-duplicate dataset on both arms — no code change to the retry classification was made, as that would be unrequested provider-adapter work beyond this task's scope.

**This document supersedes nothing** — it is the first trustworthy data this experiment has produced; `docs/evidence/2026-07-24-vl_text-battery.md`, `2026-07-24-vl_img-battery.md`, and `2026-07-24-vl_rerun-credential-gate-blocked.md` remain accurate records of the credential-blocked attempts that preceded it.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/vl_or_text_battery/{events.sqlite3,battery_raw.jsonl}`, `.onex_state/steel_onslaught/vl_or_img_battery/{events.sqlite3,battery_raw.jsonl}` (30 rows each, seeds 5001–5030, zero dupes/gaps).
- New overlays: `contracts_data/overlays/vision_foundry_60_asym_v2_openrouter_text.yaml`, `contracts_data/overlays/vision_foundry_60_asym_v2_openrouter_img.yaml`.
- New pilot registry: `contracts_data/pilots/vision_openrouter/{llm_openrouter_berserker,llm_openrouter_sniper}.yaml`.
- New loadouts: `contracts_data/loadouts/vision_openrouter/{berserker_scout_v2,sniper_ironclad}.yaml`.
- Render/ledger-linkage spot check: `.onex_state/steel_onslaught/vision_foundry_60_asym_v2_openrouter_img/renders/match.01KYB0YYXKECKYJTFN71C40EW9/tick_0027_mech.red.01.png`, sha256 `6b85e8b6f1b5a222eda51ca103ab050085866db6344277f8856f6ac3d1e4e68c`, matching the ledger's `image_sha256` for the same match/tick/seat exactly.
- Render determinism unit suite: `uv run pytest tests/llm/test_render_determinism.py` — 9/9 passed, this session.
- Transport/retry classification: `src/steel_onslaught/llm/client_http.py` (`OpenAICompatibleClient.complete`), `src/steel_onslaught/llm/pilot.py` (`LLMPilot.decide`, `_parse_response`, `_serialize_observation`).
- Prior blocked attempts: `docs/evidence/2026-07-24-vl_text-battery.md` (PR #176), `docs/evidence/2026-07-24-vl_img-battery.md` (PR #178), `docs/evidence/2026-07-24-vl_rerun-credential-gate-blocked.md` (PR #185).
- Cognition/behavior method precedent: `docs/evidence/2026-07-24-spatial_r1-battery.md`.
- Merge commit for the original vision pilot code: `b47d481de43f6e553776455cb53ea308b69cf49e` (PR #171, `main`).
- Live OpenRouter evidence: `GET https://openrouter.ai/api/v1/models` (model modality/pricing, this session), `GET https://openrouter.ai/api/v1/credits` (billing, before/after this session's usage).
- No secrets, key values, or absolute paths included. `OPEN_ROUTER_API_KEY` is referenced by variable name only throughout this document and the underlying battery driver.
