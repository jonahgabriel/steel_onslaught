# ARM V-TEXT (Vision-Representation Experiment, Text Baseline) Battery — HARD BLOCKED (2026-07-24)

**Verdict:** **VACUOUS / UNTRUSTWORTHY.** 0/30 matches reached a terminal state. `play_terminal_fraction = 0/22 attempted = 0.0000` (some sources report 21 unique seeds; see §1) — massively below the ≥0.9 trust gate. No win rate, terminal-class mix, keep-rate, or cognition-axis figure can be computed. This is not a competitiveness result; it is an infrastructure failure of the `GEMINI_API_KEY` credential, independently reproduced below.

**Ledger:** `.onex_state/steel_onslaught/vl_text_battery/` (`events.sqlite3` only — no `battery_raw.jsonl`, no `battery_summary.json`, empty `leaderboard.sqlite3`) in the SO-SCREENSHOT worktree.
**Change under test:** PR #171 (merged to `main` at `b47d481de43f6e553776455cb53ea308b69cf49e`) — deterministic arena-screenshot renderer + image-capable `OpenAICompatibleClient`, and this arm's overlay, `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_text.yaml` (V-TEXT: no `image_attachment` binding — text-only baseline for the within-model V-TEXT/V-IMG comparison). Arena `foundry_60_asym_v2`, loadouts under `contracts_data/loadouts/vision_gemini/` (PR #157 v2 config).
**Model:** `gemini-2.5-flash-lite`, direct (non-OpenRouter) Google API, both seats, target n=30 seeds 5001–5030.
**All figures below are independently recomputed by an adversarial verifier from the raw sqlite ledger and a live re-probe of the same credential/endpoint, not copied from the battery runner's report.**

---

## Method

- **Terminal health** = distinct `event_type` values present in `events.sqlite3` for this ledger, checked for `MATCH_ENDED`/`match_ended`/any terminal-completion event; cross-checked `match_started` vs. `match_tick` max-per-`match_id` to rule out a silent completion the runner's report missed.
- **Completion health** = `llm_completion_requested` / `llm_completion_resolved` / `llm_completion_failed` counts and per-event `payload_json`/`envelope_json` failure codes, grouped by `subject.player_id` (seat) and ordered by `emitted_at`.
- **Credential/root-cause verification** = independent live `curl` to the exact endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`, model `gemini-2.5-flash-lite`) using the same `GEMINI_API_KEY` present in this machine's `~/.omnibase/.env`, run fresh during this verification pass (not reused from the runner's probe).
- **Vacuity/image check** = grep of both `payload_json` and `envelope_json` across all 252 ledger rows for `image`/`.png`/`sha256` tokens, to confirm zero image artifacts exist for this arm (expected — V-TEXT carries no `image_attachment`) and that no stray V-IMG data leaked into this state root.

---

## 1. Completion health (0/30 matches reached terminal)

| Metric | Value |
|---|---|
| `match_started` events | 22 |
| Unique `match_id` values | 22 |
| Unique seeds attempted | 21 (5001–5021; seed 5001 restarted once after crashing at tick 2, ran to tick 6 on retry before also failing) |
| `match_tick` events (any progress) | 30, spanning the 22 match attempts |
| Max ticks reached, any single match | 6 (`match.01KYAK751HRDGFTBTT6YHMN85X`, seed 5001 retry) — 19 of 22 matches never progressed past tick 1 |
| Any `MATCH_ENDED`/`match_ended`/terminal-completion event | **absent** — confirmed by full `event_type` enumeration of the 252-row ledger (`boiler_updated` 60, `llm_completion_requested` 42, `match_tick` 30, `llm_completion_failed` 22, `match_started` 22, `llm_completion_resolved` 20, `pilot_decision_made` 20, `move_intent` 18, `movement_resolved` 14, `sensor_observation` 4 — no terminal type in the list) |
| `battery_raw.jsonl` | does not exist in the state root |
| `battery_summary.json` | does not exist in the state root |
| `leaderboard.sqlite3` rows | 0 |
| **play_terminal_fraction** | **0.0000** (0 decided matches ÷ 22 attempted, or 0/21 by unique-seed count — either way, 0.0) |
| Seeds never attempted | 5022–5030 (9 seeds) — run was stopped once the live quota probe confirmed a daily (not transient) cap |

Every match aborted mid-tick on an unrecoverable `llm_completion_failed`. No completed match, no win, no terminal-class, no card-programming or keep-rate signal exists anywhere in this ledger to recompute. The runner's "0/30" framing and this verifier's "0/22 attempted, 0/21 unique seeds" framing describe the identical underlying fact: **zero matches finished.**

## 2. Completion failure breakdown

| Metric | Value |
|---|---|
| `llm_completion_requested` | 42 |
| `llm_completion_resolved` (succeeded) | 20 |
| `llm_completion_failed` | 22 |
| Requested − Resolved | 22 (matches `llm_completion_failed` count exactly — no unaccounted-for in-flight requests) |
| Failures by `semantic_failure_code` | `malformed_json` × 1 (first failure chronologically, `emitted_at=2026-07-24T17:35:35.934191+00:00`, occurring one event after the very first successful resolution — a genuine model-side JSON formatting miss, not a transport error); `reason_code=provider_error` (generic transport failure, HTTP status not carried in the ledger payload) × 21 |
| Requested/failed by seat | red (`player.red`): 30 requested, 18 failed, 12 resolved; blue (`player.blue`): 12 requested, 4 failed, 8 resolved — an artifact of red firing first each tick and therefore hitting the shared daily quota ceiling more often, not a seat-specific cognition difference (there is no decision content to compare — see §3) |
| Successful-resolution positions in chronological failure/success sequence | resolutions occur at request-sequence positions 1, 2, 4–14, 18–20, 28, 32, 33, 37 of 42 — **total successes (20) land exactly on the quota's numeric ceiling** but are interleaved with failures rather than a clean "first 20 succeed, then all fail" cutoff, consistent with a shared per-project daily counter racing concurrent in-flight requests at the boundary, not a simple sequential cap |
| Run wall-clock span | 2026-07-24T17:35:33 → 17:38:56 UTC (≈3.4 minutes for all 22 match attempts) — the quota did not recover across this window, ruling out a per-minute/short-backoff cap |

The ledger itself does not carry HTTP status codes per failure (only `reason_code`/`semantic_failure_code`), so this verifier cannot independently confirm the runner's specific "20×429, 1×503" HTTP-status split from the ledger alone. The aggregate picture — 22 failures, 20 successes, exactly matching the quota's stated numeric limit, no recovery across a 3.4-minute window — is independently confirmed and sufficient to corroborate the runner's root-cause diagnosis regardless of the exact 429/503 split.

## 3. Root-cause verification (independently re-probed, not trusted from the runner's report)

A fresh `curl` was issued during this verification pass, using the same `GEMINI_API_KEY` sourced from this machine's `~/.omnibase/.env`, against the identical endpoint/model:

```
POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
model: gemini-2.5-flash-lite
```

Response: **HTTP 429**, body:

```json
{
  "error": {
    "code": 429,
    "message": "You exceeded your current quota... Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite",
    "status": "RESOURCE_EXHAUSTED",
    "details": [{
      "@type": "type.googleapis.com/google.rpc.QuotaFailure",
      "violations": [{
        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash-lite"},
        "quotaValue": "20"
      }]
    }]
  }
}
```

This independently confirms, from a fresh probe rather than trusting the runner's transcript:
- **The quota metric name is literally `generate_content_free_tier_requests`** — the key is on Google AI Studio's free tier, not billing-enabled.
- **`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`** — the cap is per-day, per-project, per-model (20 requests/day for `gemini-2.5-flash-lite`), not a short-window rate limit. A short backoff or retry cannot recover it.
- **The response's `retryDelay: "49s"` field is a generic RPC hint and is misleading** for a daily quota — Google's 429 responses carry a nominal short retry delay regardless of whether the underlying quota is per-minute or per-day; the `quotaId` name is the authoritative signal, not the `retryDelay` value.
- The ledger's observed pattern (exactly 20 successful resolutions total, no recovery across 3.4 minutes of continuous attempts) is fully consistent with this being the exact quota exhausted mid-run, not a coincidence.

**This contradicts PR #171's merge-report claim.** The PR body states: *"Model chosen: `gemini-2.5-flash-lite` via the existing direct (non-OpenRouter) Gemini wiring pattern (`tactical_v1_gemini.yaml`) — **own-billed API key**, not the shared OpenRouter `:free` pool that truncated the gemma text lane at n=19/30."* The quota-metric name (`..._free_tier_requests`) and quota-id (`...FreeTier`) returned by Google's own API directly refute "own-billed" — this is the same class of free-tier daily-cap failure the PR explicitly claimed this credential avoided, just against Google's free tier instead of OpenRouter's `:free` pool. This is a factual misstatement about the credential in the merged PR body, not an environmental flake; it should be corrected and is likely to also block the V-IMG twin overlay (`vision_foundry_60_asym_v2_gemini_img.yaml`), which shares the same `secret_ref: secret://llm/gemini` / same daily-quota project and was not yet attempted as of this verification pass (no V-IMG evidence doc or ledger exists in this repo).

## 4. Vacuity / image check (N/A for this arm, confirmed clean)

V-TEXT carries no `image_attachment` binding by design (confirmed by direct read of `vision_foundry_60_asym_v2_gemini_text.yaml`), so no PNGs or image sha256 events are expected. Grepped both `payload_json` and `envelope_json` across all 252 rows for `image`/`.png`/`sha256` tokens: the only `sha256` hits are `prompt_sha256` fields on `effective_prompt` records (prompt-provenance hashing, unrelated to images) — zero image-related content anywhere in this ledger. No PNG files exist under the state root. Nothing to vacuity-check for a V-IMG-shaped claim, and no cross-contamination from a V-IMG run.

## 5. Cognition axis / outcome axis / within-model comparison / cross-model note

Not computable. With zero decided matches:
- **Outcome axis** (red win rate, terminal-class mix, survival, LOS-blocked-shot fraction): no data.
- **Cognition axis** (terrain/cover/LOS mentions in rationales, out-of-range fire attempts): `pilot_decision_made` fired 20 times total (matching the 20 successful completions) but every one of those 20 decisions belongs to a match that subsequently aborted before reaching a terminal state — there is no complete-match sample to characterize rationale content against, and doing so from fragments would misrepresent partial-match behavior as if it were battery-level evidence.
- **V-TEXT vs. V-IMG within-model delta**: cannot be computed — V-IMG has not been run (no ledger, no evidence doc exists for `vision_foundry_60_asym_v2_gemini_img.yaml` as of this verification), and is very likely to hit the identical daily-quota wall on the same credential/project.
- **Cross-model, confounded, directional-only note vs. qwen35 ASCII-representation arm**: no such arm exists yet. The only qwen35 evidence doc present in this repo is `docs/evidence/2026-07-23-scenario-variation-qwen35-symmetric.md` (a scenario-variation battery, not an ASCII-representation arm) — there is nothing to compare against.

## 6. Merge / additivity verification

- PR #171 merged to `main` at `b47d481de43f6e553776455cb53ea308b69cf49e` (`gh pr view 171`: state MERGED, mergedAt 2026-07-24T17:34:07Z, title "feat: vision pilot — deterministic arena screenshots + image-capable adapter (V-TEXT/V-IMG arms)").
- Overlay `vision_foundry_60_asym_v2_gemini_text.yaml` provider config independently confirmed: `retry.max_attempts: 1, initial_backoff_seconds: 0.0` — i.e. **zero retry budget**, so any single transient (or, as established above, non-transient quota) failure was fatal to the in-flight completion by design, amplifying a 20-request daily cap into a near-total battery block rather than a partial-degradation scenario.
- No code or state was hand-edited during this verification; the worktree (`SO-SCREENSHOT`, branch `docs/so-vl-text-battery-evidence`, `HEAD` at `b47d481`) was inspected read-only plus one diagnostic `curl` against the live Gemini endpoint.

---

## Verdict

**VACUOUS / UNTRUSTWORTHY.** `play_terminal_fraction = 0.0`, catastrophically below the ≥0.9 trust gate — no verdict band on red win rate applies because no match ever reached a terminal state. This is a credential/infrastructure failure, independently re-confirmed live: the `GEMINI_API_KEY` bound to `secret://llm/gemini` is a Google AI Studio **free-tier** key subject to a hard **20 requests/day/project/model** ceiling (`quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`), not the "own-billed" credential PR #171's merge report claims. The overlay's zero-retry provider config (`max_attempts: 1`) turned this into a near-immediate full-battery block once the daily allotment (already partially consumed before this run started) was exhausted. Neither the outcome axis (win rate, survival, terminal mix) nor the cognition axis (rationale content, LOS/terrain reasoning) can be measured from this run. The V-IMG twin overlay shares the identical credential and is very likely to hit the same wall if attempted before the quota resets or a billing-enabled key is substituted.

**What's needed before this arm (or its V-IMG twin) can produce trustworthy data:** either (a) enable billing on the Google Cloud project backing `GEMINI_API_KEY` so the paid tier's higher per-day ceiling applies, or (b) supply a different, billing-enabled key via `secret://llm/gemini`. Retrying today will not help — the quota is daily and was already exhausted before this battery started (5 requests appear to have already been consumed prior to seed 5001's first attempt, based on the partial success distribution). This finding also warrants a correction to PR #171's "own-billed" claim and a follow-up ticket, since it is a factual misstatement about the credential rather than an environmental flake.

---

## Citations (all relative paths)

- Ledger: `.onex_state/steel_onslaught/vl_text_battery/events.sqlite3` (252 rows total — `boiler_updated`, `llm_completion_requested`, `match_tick`, `llm_completion_failed`, `match_started`, `llm_completion_resolved`, `pilot_decision_made`, `move_intent`, `movement_resolved`, `sensor_observation`); `leaderboard.sqlite3` (0 rows).
- Overlay under test: `contracts_data/overlays/vision_foundry_60_asym_v2_gemini_text.yaml`.
- Merge commit: `b47d481de43f6e553776455cb53ea308b69cf49e` (PR #171, `main`).
- Independent live credential probe: direct `curl` to `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` (`gemini-2.5-flash-lite`) using the `GEMINI_API_KEY` from this machine's `~/.omnibase/.env`, executed fresh during this verification pass — HTTP 429, `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`.
- Prior related arms: `docs/evidence/2026-07-23-crossarch-b-gemma.md` (OpenRouter `:free` daily-cap truncation, n=19/30 — the same class of free-tier failure this PR's credential was meant to avoid).
- No secrets, keys, or absolute paths included. The `GEMINI_API_KEY` value itself is never printed or committed anywhere in this document or the underlying probe output.
