# Vision-Representation Experiment RERUN over Vertex AI — V-TEXT vs V-IMG, n=30 Matched Seeds (2026-07-24)

**Verdict: the OpenRouter finding (`docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md`) replicates on a second, independent provider route — and is even larger here.** Same model (`google/gemini-2.5-flash-lite`), same arena (`foundry_60_asym_v2`), same loadouts/personas, seeds 5001–5030 matched across arms, this time via Google Cloud Vertex AI's direct OpenAI-compatible endpoint (ADC OAuth2 auth, on-demand billing against project `omnibase-465418` — no OpenRouter pass-through in the loop):

- **V-TEXT** (no image): decided-match red (brawler) win rate **16/30 = 0.5333**, 95% Wilson CI **[0.3614, 0.6977]** — **COMPETITIVE** band (≥0.35).
- **V-IMG** (same prompt + deterministic per-tick PNG attached): decided-match red win rate **0/30 = 0.0000**, 95% Wilson CI **[0.0000, 0.1135]** — **FAILED** band (<0.10).
- **Delta: −0.5333** (larger than the OpenRouter run's −0.4667). **Every one of red's 16 V-TEXT wins flips to a blue win under V-IMG on the identical seed.** Zero seeds flip the other way — the same clean, complete flip pattern as the OpenRouter replication (there: 14/14 flipped).
- **Cognition axis again shows ZERO attribution to the image**: 0/1033 red rationales and 0/1033 blue rationales in V-IMG contain any visual/color/pixel vocabulary the pure-numeric text observation could not already produce. Identical null to the OpenRouter run.
- **Behavior axis again shows a large, consistent degradation, and it is even larger here**: red's out-of-range fire fraction rises from 0.12% (V-TEXT) to 28.88% (V-IMG); red's zero-hit-probability fired fraction rises from 6.41% to **55.60%** (vs the OpenRouter run's 38.24%).
- **This is a two-provider replication of the same effect with the same model** — the collapse is not an OpenRouter-routing artifact. It reproduces via a completely independent auth mechanism (ADC OAuth2 vs OpenRouter Bearer key), a completely independent billing path (direct Google Cloud project billing vs OpenRouter pass-through), and a completely independent transport failure profile (§3 — the OpenRouter run's dominant `finish_reason="error"` signature did not occur even once on Vertex).

**Why Vertex, in addition to the already-complete OpenRouter rerun:** the OpenRouter route works and is fully reported (PR #187), but it is a third-party pass-through between this codebase and Google. Vertex AI is Google Cloud's own direct, first-party route to the identical model — the most canonical provider binding available for this experiment, and the one this session's operator specifically enabled (installing `gcloud`, configuring Application Default Credentials) once it became available. Running both closes any residual doubt that the collapse is provider-specific rather than model-specific.

**Ledgers:** `.onex_state/steel_onslaught/vl_vertex_text_battery` and `.onex_state/steel_onslaught/vl_vertex_img_battery` (`events.sqlite3`, `battery_raw.jsonl`, `battery_summary.json` each) in the SO-VISION-OR worktree.
**Change under test:** two new overlays, `contracts_data/overlays/vision_foundry_60_asym_v2_vertex_{text,img}.yaml`, a new pilot registry (`contracts_data/pilots/vision_vertex/`), new loadouts (`contracts_data/loadouts/vision_vertex/`), and one additive entry in `scripts/run_ogate_objectives_battery.py`'s `_SECRET_REF_ENV_NAMES` mapping (`secret://llm/vertex` → `VERTEX_ACCESS_TOKEN`) — no other line in that script changed. All new files are byte-for-byte mirrors of the OpenRouter/gemini_vl surfaces except for the provider binding. No existing overlay, loadout, or pilot file is modified.
**Model:** `google/gemini-2.5-flash-lite` via Vertex AI, both seats, both arms, n=30, seeds 5001–5030 matched across arms, `all_replay_valid=true` (1/1 both players, all 60 matches).
**All figures below are independently recomputed from `battery_raw.jsonl` + `events.sqlite3` for each arm.**

---

## 0. Auth, billing, and the smoke gate

**Environment (flagged as a caveat, not this document's problem to fix):** `gcloud` is installed at `~/Downloads/google-cloud-sdk/bin/gcloud` on this machine — not on the default `PATH`. Whoever reruns this must add that directory to `PATH` (or resolve `gcloud` explicitly) before invoking any Vertex-bound battery.

**Auth verified live:**
- `gcloud config list` confirms `disable_usage_reporting = True`, active config `default`.
- `~/.config/gcloud/application_default_credentials.json` exists, `type: authorized_user`.
- `gcloud auth application-default print-access-token` mints a fresh OAuth2 access token in well under 1 second — confirmed by timing during this session, consistent with a per-seed-refresh strategy costing negligible time across a ~60-match run.

**Endpoint and model, verified via two live probe calls before any battery ran:**
- `POST https://us-central1-aiplatform.googleapis.com/v1beta1/projects/omnibase-465418/locations/us-central1/endpoints/openapi/chat/completions`, `model: google/gemini-2.5-flash-lite` (the `google/` prefix is required by this endpoint — confirmed necessary via the live 200 response, not assumed). A plain text probe returned HTTP 200, `{"content": "OK"}`, and **`usage.extra_properties.google.traffic_type: "ON_DEMAND"`** — the tier-proof field this session's operator flagged as decisive: billed against project `omnibase-465418`, not a free tier.
- A second probe with a real multi-part `image_url` content part (base64 PNG data URI) plus `response_format: json_object` also returned HTTP 200 with valid JSON content (`{"colors_seen": ["blue", "darkgray"], "shape_count": 25}`) and the same `traffic_type: "ON_DEMAND"` — confirming both image acceptance and billed status together, before the battery launched.
- **Re-verified at the end of this session** (after both full batteries completed): a fresh probe call to the identical endpoint/model again returned `traffic_type: "ON_DEMAND"` — the billing tier did not change mid-run.

**Schema compatibility, checked, not assumed:** `ModelSOOpenAIChatResponse` and its nested response models (`src/steel_onslaught/llm/schemas.py`) use `extra="ignore"` (not `"forbid"`) — confirmed by direct read. Vertex's extra `usage.extra_properties` field is therefore silently ignored by parsing rather than rejected; no schema or adapter change was needed to consume Vertex responses.

**Secret wiring — the one code change this arm required:** the ADC access token is short-lived (~1hr), unlike the static API keys `_SECRET_REF_ENV_NAMES` already maps (OpenRouter, GLM, Gemini-direct). One additive dict entry, `"secret://llm/vertex": ("VERTEX_ACCESS_TOKEN",)`, was added to that mapping in `scripts/run_ogate_objectives_battery.py` — no other line in the file changed. The battery driver (an uncommitted, ephemeral per-seed shell script, matching the established P4/OpenRouter-rerun pattern) re-mints the token via `gcloud auth application-default print-access-token` and exports it fresh **immediately before every single seed's process launch** — not cached, not refreshed mid-process. Since this experiment already uses per-seed isolated invocation (one process per seed), this fully eliminates token-expiry risk across a multi-hour run with no in-process refresh logic anywhere.

**Pre-registered gate — all passed before the full battery ran:**
1. Auth resolves, token mints — confirmed above.
2. The model accepts a real multi-part image request (not a 400) — confirmed above.
3. 1-seed smoke of each arm, `all_replay_valid=true`, match terminates — V-TEXT: seed 5001, 54 ticks, `all_replay_valid=true`, 0 failed completions, 2 objective awards. V-IMG: seed 5001, 33 ticks, `all_replay_valid=true`, 0 failed completions, `image_sha256` present and matching the persisted PNG byte-for-byte (§4).

`max_tokens: 3072`, `timeout_seconds: 120`, and the bounded 429 retry (`max_attempts: 4`, `initial_backoff_seconds: 2.0`, `backoff_multiplier: 2.0`) were carried over unchanged from the OpenRouter overlays — no adjustment was made, and none was needed: `finish_reason="length"` occurred **zero times** across 5,096 resolved completions in this run (§3), same as the OpenRouter run.

---

## 1. Additivity check

`diff` of the two new overlays confirms they differ only in header comments, state-root path fields, `model_identity_id`/`display_name`, and the one added `image_attachment` block — identical pattern to the OpenRouter pair (verified there in `docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md` §1). Both arms share the identical `contracts_data/loadouts/vision_vertex/{berserker_scout_v2,sniper_ironclad}.yaml` (byte-for-byte module/budget mirrors of the OpenRouter loadouts) and pilot registry. Neither arena nor persona files were touched. The single change to `scripts/run_ogate_objectives_battery.py` is the one-line `_SECRET_REF_ENV_NAMES` addition described in §0 — no other function or line in that file was modified.

---

## 2. Raw-file provenance

Per-seed isolated invocation (one process per seed, `--n 1 --seed-base <seed-1>`, shared append-mode state root, `--fresh` only on the first seed, up to 3 attempts per seed with a 600s timeout, two parallel background drivers) — the same established pattern as the P4 and OpenRouter-rerun batteries, with the per-seed ADC token mint added per §0.

**This run was markedly cleaner than the OpenRouter rerun.** V-TEXT needed exactly 1 retry across all 30 seeds (seed 5007); V-IMG needed 2 retries (seeds 5004, 5029). **No seed exhausted its attempt budget on either arm — no backfill pass was required this time.** `battery_raw.jsonl` for both arms has exactly 30 rows, seeds 5001–5030, zero duplicates, zero gaps, verified independently.

`events.sqlite3` shows 31 distinct `match_started` values for V-TEXT (30 valid + 1 orphaned partial-match retry) and 32 for V-IMG (30 valid + 2 orphaned) — both counts self-consistent with the failure counts in §3 (1 and 2 respectively). All event-level analysis below filters to the 30 valid `match_id`s per arm; orphaned partial-match events are excluded.

---

## 3. Completion health — the OpenRouter failure mode did NOT recur

| Metric | V-TEXT (valid matches) | V-IMG (valid matches) |
|---|---:|---:|
| `llm_completion_requested` | 2990 | 2066 |
| `llm_completion_resolved` | 2990 | 2066 |
| `llm_completion_failed` (in valid matches) | 0 | 0 |
| `finish_reason` distribution (resolved) | `stop`: 2990/2990 (0 `length`) | `stop`: 2066/2066 (0 `length`) |
| max `completion_tokens` observed | 88 | 93 |
| mean `prompt_tokens` | 1033.8 | 2355.9 |
| mean `completion_tokens` | 55.2 | 57.8 |

| Metric | V-TEXT (all attempts) | V-IMG (all attempts) |
|---|---:|---:|
| `llm_completion_requested` | 3003 | 2097 |
| `llm_completion_failed` | **1** | **2** |
| Failure rate | **0.033%** | **0.095%** |
| `(finish_reason='stop', semantic_failure_code='malformed_json')` | 1 | 1 |
| `(finish_reason='stop', semantic_failure_code='action_unavailable')` | 0 | 1 |
| `(finish_reason='error', ...)` — the OpenRouter run's dominant signature | **0** | **0** |

**This is a decisive cross-provider confirmation of the hypothesis raised in the OpenRouter evidence doc §3**: the dominant OpenRouter failure signature (HTTP 200 with in-band `finish_reason="error"` and zero usage tokens — 28/31 and 9/11 of that run's failures) is an **OpenRouter/pass-through-routing artifact, not a characteristic of the underlying Google Gemini backend**. On Vertex — the same model, direct from Google, no pass-through — that exact signature occurred **zero times** across 5,100 total attempts. The only 3 failures observed here are genuine model-output validation failures (`finish_reason='stop'` with real, billed completions that failed downstream parsing/validation) — the same minor residual class the OpenRouter run also showed a handful of, at a substantially lower overall rate (0.033–0.095% here vs 0.59–0.84% there).

---

## 4. Outcome, terminal health, and match length

| Metric | V-TEXT | V-IMG |
|---|---:|---:|
| `match_started` / `match_ended` (valid) | 30 / 30 | 30 / 30 |
| Terminal-class mix | elimination 30/30 | elimination 30/30 |
| `play_terminal_fraction` | **1.0000** (gate ≥0.9 — PASS) | **1.0000** (gate ≥0.9 — PASS) |
| Winner distribution | player.blue 14, player.red 16 | player.blue 30, player.red 0 |
| **Decided-match red win rate** | **16/30 = 0.5333** | **0/30 = 0.0000** |
| 95% Wilson CI | **[0.3614, 0.6977]** | **[0.0000, 0.1135]** |
| Verdict band | **COMPETITIVE** (≥0.35) | **FAILED** (<0.10) |
| Replay validity | 1/1 both players, all 30 matches | 1/1 both players, all 30 matches |
| `mech_destroyed` (red as victim) | 14/30 | 30/30 |
| Match length: min / median / mean / max (ticks) | 28 / 45.5 / 49.83 / 83 | 11 / 27.5 / 34.43 / 143 |

Recomputed directly from `battery_raw.jsonl` and cross-checked against `events.sqlite3` (`COUNT(DISTINCT match_id) WHERE event_type='match_ended'` = 30 for both arms). V-IMG's median match length is again shorter than V-TEXT's (27.5 vs 45.5 ticks), though the max (143 ticks, seed 5017) is a notable outlier — the longest single match in either the OpenRouter or Vertex rerun.

### Seed-level pairing

| V-TEXT red wins (seed) | V-IMG outcome, same seed |
|---|---|
| 5002, 5003, 5005, 5008, 5009, 5011, 5015, 5017, 5019, 5021, 5023, 5024, 5026, 5027, 5029, 5030 | **all 16 flip to blue** |

Zero seeds flip the other direction. **Note:** the specific seeds that produce a red win differ between the OpenRouter V-TEXT run and this Vertex V-TEXT run (e.g. seed 5001 is a blue win in both, but seed 5002 is blue in OpenRouter's V-TEXT and red here) — expected, since the seed controls the deterministic match/environment RNG, not the LLM's own stochastic sampling (`temperature: 0.7` for the berserker persona). The within-provider, seed-matched V-TEXT-vs-V-IMG comparison is the valid one; cross-provider seed-for-seed comparison is not meaningful and is not attempted here.

---

## 5. Cognition axis — again, not reached (replicates the OpenRouter null)

Same method as the OpenRouter evidence doc §5 (visual/color/pixel vocabulary scan of `pilot_decision_made.rationale`, reused from `spatial_r1`'s clean-attribution approach).

| Arm | Seat | Rationales scanned | Visual-vocab hits | Fraction |
|---|---|---:|---:|---:|
| V-IMG | red | 1033 | **0** | **0.0000** |
| V-IMG | blue | 1033 | **0** | **0.0000** |
| V-TEXT (negative control) | red | 1495 | 0 | 0.0000 |
| V-TEXT (negative control) | blue | 1495 | 0 | 0.0000 |

**Identical to the OpenRouter run: zero clean-attribution vocabulary anywhere, on either arm, either seat.** The model's stated rationale gives no verbal indication it is using the image, in either provider route, even though outcome and behavior (§6) both shift dramatically. This is now a twice-replicated null, not a single-run artifact.

---

## 6. Behavior axis — replicates, and the effect is larger here

| Seat | Metric | V-TEXT | V-IMG | Δ | (OpenRouter run's Δ, for reference) |
|---|---|---:|---:|---:|---:|
| red (brawler) | fire attempts (`fired`+`rejected`) | 843 | 703 | — | — |
| red | out-of-range fraction | 1/843 = **0.12%** | 203/703 = **28.88%** | **+28.76 pp** | (+35.44 pp) |
| red | zero-hit-probability fired fraction | 54/842 = **6.41%** | 278/500 = **55.60%** | **+49.19 pp** | (+33.00 pp) |
| blue (sniper) | fire attempts | 80 | 212 | — | — |
| blue | out-of-range fraction | 0/80 = 0.00% | 0/212 = 0.00% | 0.00 pp | (0.00 pp) |
| blue | zero-hit-probability fired fraction | 0/80 = **0.00%** | 93/212 = **43.87%** | **+43.87 pp** | (+22.06 pp) |
| — | red avg decision confidence | 0.9551 | 0.9774 | +0.0223 | (+0.0255) |
| — | blue avg decision confidence | 0.7126 | 0.6086 | −0.1040 | (−0.1312) |

The same targeting-precision degradation pattern reported for the OpenRouter run reproduces here, and is **larger** on the zero-hit-probability metric for both seats (red: 55.60% vs 38.24%; blue: 43.87% vs 22.06%; blue's V-TEXT baseline is even a clean 0.00% here, vs 0.97% on OpenRouter). Mean prompt tokens again roughly double under V-IMG (1034 → 2356), consistent with the OpenRouter run's token-overhead figures (1033 → 2353) — the two hypotheses offered in the OpenRouter doc §6 (image-content-specific degradation vs. prompt-length/attention dilution) remain undistinguished by this experiment; this replication does not resolve which mechanism dominates, only that the effect itself is robust across two independent provider routes.

---

## 7. Verdict

**The OpenRouter finding replicates on Vertex AI — a second, independent, more canonical provider route for the identical model — and is even larger here.** Red's decided-match win rate collapses from 53.33% (COMPETITIVE, Wilson CI [0.361, 0.698]) to 0.00% (FAILED, Wilson CI [0.000, 0.114]) when the deterministic per-tick PNG is attached, holding model/arena/loadouts/personas/seeds fixed. Every one of red's 16 V-TEXT wins flips to a blue win under V-IMG on the matched seed; zero seeds flip the other way. `play_terminal_fraction=1.0000` on both arms.

**Cognition axis replicates a clean null** (0/2066 clean-attribution vocabulary hits across both seats, both arms combined with the OpenRouter run's 0/1478) — twice-confirmed, not a single-run artifact. **Behavior axis replicates the degradation, at a larger magnitude on the zero-hit-probability metric** — the mechanism question (image content vs. prompt-length dilution) remains open, exactly as flagged in the OpenRouter doc.

**The OpenRouter run's dominant transport failure mode (in-band `finish_reason="error"`, zero tokens) did not occur even once on Vertex** (0/5,100 attempts), confirming it as an OpenRouter/pass-through characteristic rather than a Google Gemini backend property. Vertex's own failure rate (0.033–0.095%) was an order of magnitude lower, and no seed required a backfill pass — the cleanest battery in this whole vision-representation program to date.

**This document does not supersede** `docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md` — both are independent, complete, trustworthy datasets for the same experiment via two different provider routes, and their agreement is itself the strongest evidence yet that this is a real model/representation effect, not a provider artifact.

---

## Citations (all relative paths)

- Recomputed metrics: `.onex_state/steel_onslaught/vl_vertex_text_battery/{events.sqlite3,battery_raw.jsonl}`, `.onex_state/steel_onslaught/vl_vertex_img_battery/{events.sqlite3,battery_raw.jsonl}` (30 rows each, seeds 5001–5030, zero dupes/gaps).
- New overlays: `contracts_data/overlays/vision_foundry_60_asym_v2_vertex_text.yaml`, `contracts_data/overlays/vision_foundry_60_asym_v2_vertex_img.yaml`.
- New pilot registry: `contracts_data/pilots/vision_vertex/{llm_vertex_berserker,llm_vertex_sniper}.yaml`.
- New loadouts: `contracts_data/loadouts/vision_vertex/{berserker_scout_v2,sniper_ironclad}.yaml`.
- Driver secret mapping: `scripts/run_ogate_objectives_battery.py`, `_SECRET_REF_ENV_NAMES["secret://llm/vertex"]`.
- Render/ledger-linkage spot check: `.onex_state/steel_onslaught/vision_foundry_60_asym_v2_vertex_img/renders/match.01KYB4TEYFA8AZSNRFH4QNVMDV/tick_0001_mech.red.01.png`, sha256 `1e5e08c6f81dbf7b05a11a40b0ca3f708f4fa45a0399d82e4f0ca1f1553a0b73`, matching the ledger's `image_sha256` for the same match/tick/seat exactly.
- Response schema compatibility: `src/steel_onslaught/llm/schemas.py` (`ModelSOOpenAIChatResponse` and nested response models, `extra="ignore"`).
- Sibling/companion evidence: `docs/evidence/2026-07-24-vl_openrouter_rerun-battery.md` (the OpenRouter rerun this document replicates), `docs/evidence/2026-07-24-vl_text-battery.md` / `2026-07-24-vl_img-battery.md` (the original blocked Gemini-direct attempts), `docs/evidence/2026-07-24-vl_rerun-credential-gate-blocked.md` (PR #185).
- Live Vertex evidence: two pre-battery probe calls plus one post-battery re-verification call to `https://us-central1-aiplatform.googleapis.com/v1beta1/projects/omnibase-465418/locations/us-central1/endpoints/openapi/chat/completions`, `model: google/gemini-2.5-flash-lite`, all returning `usage.extra_properties.google.traffic_type: "ON_DEMAND"`.
- No secrets, key/token values, or absolute paths included. `VERTEX_ACCESS_TOKEN` is referenced by variable name only throughout this document and the underlying battery driver; the actual OAuth2 token is never printed, logged, or committed anywhere.
